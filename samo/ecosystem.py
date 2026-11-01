"""Experimental bounded population ecology. Not yet wired to production supervision."""
import copy
import hashlib
import json
import os
import random
import tempfile
from pathlib import Path

from .evaluator import FAMILIES, evaluate, task_stream
from .genome import ancestor, digest, recombine, reproduce, validate

PROTOCOL = 'samo-ecosystem-v1'
MAX_POPULATION = 8
MAX_EVENTS = 12_000
MAX_ARCHIVE_GENOMES = 512


def _event(state, kind, **data):
    item = {'index': state['event_index'], 'kind': kind, **data}
    state['event_index'] += 1
    item['id'] = digest(item)
    state['events'].append(item)
    if len(state['events']) > MAX_EVENTS:
        raise RuntimeError('ecology event cap reached; halt without pruning')
    return item


def create(seed, population_size=4):
    if type(population_size) is not int or not 2 <= population_size <= MAX_POPULATION:
        raise ValueError('population size')
    rng = random.Random(seed)
    founder = ancestor()
    pop = []
    for i in range(population_size):
        genome, _, _, status = reproduce(founder, rng)
        pop.append({'id': f'e0-i{i}', 'parent_ids': [], 'genome': genome if status == 'ok' else copy.deepcopy(founder),
                    'birth': 0, 'alive': True, 'last_accuracy': 0.0,
                    'sterile_attempts': 0, 'lineage': f'founder-{i}'})
    state = {'protocol': PROTOCOL, 'seed': seed, 'rng': rng.getstate(), 'step': 0,
             'episode': 0, 'task_index': 0, 'event_index': 0, 'population': pop,
             'archive': [copy.deepcopy(x['genome']) for x in pop], 'events': []}
    _event(state, 'ecosystem_initialized', population=len(pop), seed_commitment=
           hashlib.sha256(str(seed).encode()).hexdigest())
    return state


def _rng(state):
    rng = random.Random()
    rng.setstate(_tuples(state['rng']))
    return rng


def _tuples(v):
    return tuple(_tuples(x) if isinstance(x, list) else x for x in v)


def step(state, fuel_per_prediction=128):
    """Advance one competitive reproduction attempt; caller supplies external resource limits."""
    if state['protocol'] != PROTOCOL:
        raise ValueError('protocol')
    rng = _rng(state)
    alive = [x for x in state['population'] if x['alive']]
    if not alive:
        state['episode'] += 1
        # Recolonization is an explicit new episode; preserve all events and dead lineage records.
        source = min(state['archive'], key=lambda g: digest(g)) if state['archive'] else ancestor()
        if not state['archive']:
            source = ancestor()
        new = copy.deepcopy(source)
        _event(state, 'recolonization', episode=state['episode'], source='diversity_archive' if state['archive'] else 'registered_ancestor',
               source_hash=digest(new))
        identifier = f"e{state['episode']}-i{state['step']}"
        alive = [{'id': identifier, 'parent_ids': [], 'genome': new, 'birth': state['step'],
                  'alive': True, 'last_accuracy': 0.0, 'sterile_attempts': 0,
                  'lineage': f'episode-{state["episode"]}'}]
        state['population'].append(alive[0])
    family = FAMILIES[state['task_index'] % len(FAMILIES)]
    task_seed, task_list = task_stream(state['seed'], state['task_index'], (family,), repeats=1)
    scores = {}
    for organism in alive:
        result = evaluate(organism['genome'], task_list, 'train', fuel_limit=fuel_per_prediction, raw=False)
        organism['last_accuracy'] = result['accuracy']
        scores[organism['id']] = result['accuracy']
    # Bounded tournament: performance and behavioral/genotypic diversity both remain visible.
    parent = max(alive, key=lambda x: (x['last_accuracy'] + rng.random() * 0.05, rng.random()))
    second = rng.choice(alive)
    child, mutations, cost, status = reproduce(parent['genome'], rng, 'samo')
    if child is not None:
        child, recombined = recombine(child, second['genome'], rng)
        score = evaluate(child, task_list, 'train', fuel_limit=fuel_per_prediction, raw=False)
        offspring = {'id': f"e{state['episode']}-i{state['step']+1}",
                     'parent_ids': [parent['id'], second['id']], 'genome': child,
                     'birth': state['step']+1, 'alive': True, 'last_accuracy': score['accuracy'],
                     'sterile_attempts': 0, 'lineage': parent['lineage']}
        if not any(digest(child) == digest(g) for g in state['archive']):
            if len(state['archive']) >= MAX_ARCHIVE_GENOMES:
                raise RuntimeError('diversity archive cap reached; halt and explicitly segment before continuing')
            state['archive'].append(copy.deepcopy(child))
        incumbent = min(alive, key=lambda x: (x['last_accuracy'], x['birth']))
        # Competition affects survival; no guarantee of monotonic fitness.
        survive = score['accuracy'] >= incumbent['last_accuracy'] or rng.random() < 0.25
        if survive:
            incumbent['alive'] = False
            state['population'].remove(incumbent)
            state['population'].append(offspring)
        _event(state, 'reproduction_attempt', organism=parent['id'], parents=offspring['parent_ids'],
               child_hash=digest(child), mutation=mutations, recombination=recombined,
               score=score['accuracy'], accepted=survive, task_index=state['task_index'],
               task_seed=task_seed, family=family, fuel=cost + score['fuel'])
    else:
        parent['sterile_attempts'] += 1
        if parent['sterile_attempts'] >= 3:
            parent['alive'] = False
            state['population'].remove(parent)
        _event(state, 'organism_sterile', organism=parent['id'], failure=status,
               task_index=state['task_index'], task_seed=task_seed, family=family)
    state['step'] += 1
    state['task_index'] += 1
    state['rng'] = rng.getstate()
    if len(json.dumps(state, separators=(',', ':'))) > 48_000_000:
        raise RuntimeError('checkpoint ceiling reached; halt without deleting history')
    return state


def save(state, path):
    """Atomic private checkpoint; external filesystem quota remains mandatory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.eco-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, separators=(',', ':'))
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def load(path):
    state = json.loads(Path(path).read_text())
    if state.get('protocol') != PROTOCOL or len(state.get('events', [])) > MAX_EVENTS:
        raise ValueError('invalid ecosystem checkpoint')
    for organism in state.get('population', []):
        validate(organism['genome'])
    return state
