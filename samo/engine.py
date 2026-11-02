"""Autonomous local experiment; no clock-based generations and no web dependency."""
import copy
import json
import math
import platform
import random
import resource
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from .archive import Archive
from .evaluator import evaluate, tasks, TRANSFER, VERSION
from .genome import ancestor, canonical, digest, reproduce

PROTOCOL_PATH = Path(__file__).resolve().parents[1] / 'protocols/pilot-v1.json'
CONDITIONS = ('fixed', 'random', 'gp', 'meta', 'samo')


def now():
    return datetime.now(timezone.utc).isoformat()


def source_hash():
    # Finder/AppleDouble sidecars are metadata, not Python sources. Exclude
    # them explicitly so packaging on macOS and Linux hashes the same code.
    return digest({p.name: p.read_text() for p in sorted(Path(__file__).parent.glob('*.py'))
                   if not p.name.startswith('._')})


def state_tuple(value):
    return tuple(state_tuple(x) if isinstance(x, list) else x for x in value)


def compact(result):
    return {k: v for k, v in result.items() if k != 'rows'}


def run_experiment(archive, seed, condition, private_seed, attempts=60, fuel_ceiling=1_500_000,
                   resume_id=None, protocol_path=None, checkpoint_steps=None):
    if condition not in CONDITIONS or not 1 <= attempts <= 10_000_000 or not 1000 <= fuel_ceiling <= 1_000_000_000_000:
        raise ValueError('invalid run parameters')
    protocol = json.loads(Path(protocol_path or PROTOCOL_PATH).read_text())
    run_id = digest({'seed': seed, 'condition': condition, 'protocol': digest(protocol),
                     'secret_commitment': digest(private_seed), 'attempts': attempts,
                     'ceiling': fuel_ceiling, 'source': source_hash()})[:20]
    rng = random.Random(seed)
    train_tasks = tasks(private_seed)
    validation_tasks = tasks(private_seed ^ 0x71F5A61)
    g = ancestor()
    t0, cpu0 = time.monotonic(), time.process_time()
    start_ordinal = 1
    run = {'id': run_id, 'seed': seed, 'condition': condition, 'protocol_id': protocol['id'],
           'protocol_hash': digest(protocol), 'source_hash': source_hash(),
           'environment': {'python': platform.python_version(), 'platform': platform.platform()},
           'started_at': now(), 'observed_at': now(), 'status': 'running',
           'fuel_ceiling': fuel_ceiling, 'attempt_limit': attempts, 'fuel': 0,
           'active_id': None, 'active_hash': digest(g), 'best_accuracy': 0,
           'attempts': 0, 'accepted': 0, 'regressions': 0, 'secret_commitment': digest(private_seed),
           'rng_state': rng.getstate(), 'latest_score': None, 'best_hash': None,
           'protocol': protocol, 'os_isolation': 'not_accepted_local_only'}
    if resume_id:
        matching = [r for r in archive.all('runs') if r['id'] == resume_id]
        if not matching:
            raise ValueError('run not found')
        run = matching[0]
        run_id = run['id']
        protocol = run['protocol']
        if run['source_hash'] != source_hash() or run['secret_commitment'] != digest(private_seed):
            raise ValueError('source or private seed differs; continuation requires intervention/new run')
        if run['status'] not in ('interrupted', 'running'):
            raise ValueError('only interrupted/running run may resume; no resurrection')
        rng.setstate(state_tuple(run['rng_state']))
        g = archive.artifact(run['active_hash'])
        start_ordinal = run['attempts'] + 1
        current = run['latest_score']
        run['status'] = 'running'
        attempts, fuel_ceiling = run['attempt_limit'], run['fuel_ceiling']
    else:
        if any(r['id'] == run_id for r in archive.all('runs')):
            raise ValueError('duplicate run: use a fresh archive or resume interrupted run')
        archive.run(run)
        initial = evaluate(g, train_tasks, 'train', fuel_limit=fuel_ceiling)
        current = compact(initial)
        run['fuel'] += initial['fuel']
        run['best_accuracy'] = initial['accuracy']
        run['best_hash'] = digest(g)
        run['latest_score'] = current
        event, ev = make_event(run, 0, g, None, [], initial, True, 'ancestor', 0, rng.getstate(), digest(g['search']))
        run['active_id'] = event['id']
        archive.record(run, event, g, ev)
    try:
        for ordinal in range(start_ordinal, attempts + 1):
            if time.monotonic() - t0 + run.get('wall_seconds', 0) >= protocol['budget']['max_seconds']:
                run['status'] = 'wall_limit'
                break
            if run['fuel'] + 512 >= fuel_ceiling:
                run['status'] = 'fuel_limit'
                break
            before_rng = rng.getstate()
            operator_hash = digest(ancestor()['search'] if condition in ('gp', 'random') else g['search'])
            child, changes, search_cost, reproduction_status = reproduce(g, rng, condition)
            run['fuel'] += search_cost
            run['attempts'] = ordinal
            if child is None:
                run['status'] = 'sterile'
                failed = {'accuracy': 0, 'mae': 1, 'fuel': 0, 'total': 0, 'failures': 1,
                          'status': reproduction_status, 'rows': [], 'families': {},
                          'behavior_hash': digest([]), 'cpu_seconds': 0}
                event, ev = make_event(run, ordinal, g, run['active_id'], [], failed,
                                       False, reproduction_status, search_cost, before_rng, operator_hash)
                run['rng_state'] = rng.getstate()
                archive.record(run, event, g, ev)
                break
            result = evaluate(child, train_tasks, 'train', fuel_limit=fuel_ceiling - run['fuel'])
            run['fuel'] += result['fuel']
            # Training is the sole performance feedback. No validation/confirmation selection.
            delta = result['accuracy'] - current['accuracy']
            accepted = condition == 'fixed' or rng.random() < math.exp(min(0, delta / 0.08))
            if result['status'] == 'budget':
                accepted = False
                run['status'] = 'fuel_limit'
            event, ev = make_event(run, ordinal, child, (run['id'] + ':0') if condition == 'random' else run['active_id'], changes, result,
                                   accepted, 'candidate', search_cost, before_rng, operator_hash)
            if accepted:
                run['accepted'] += 1
                run['regressions'] += int(delta < 0)
                g, current = child, compact(result)
                run['active_id'], run['active_hash'] = event['id'], digest(g)
                run['latest_score'] = current
            if result['accuracy'] > run['best_accuracy']:
                run['best_accuracy'], run['best_hash'] = result['accuracy'], digest(child)
            run['rng_state'] = rng.getstate()
            run['observed_at'] = now()
            archive.record(run, event, child, ev)
            if run['status'] != 'running':
                break
            if checkpoint_steps and ordinal - start_ordinal + 1 >= checkpoint_steps and ordinal < attempts:
                run['status'] = 'interrupted'
                return run
        if run['status'] == 'running':
            run['status'] = 'completed'
        # Sealed external evaluation after search. Its separately measured fuel is reported
        # and never silently counted as part of the organism's search ceiling.
        run['validation'] = compact(evaluate(g, validation_tasks, 'validation'))
        for split, seed_offset, families in [('confirm', 0x41A93BCD, None), ('transfer', 0xAF17123, TRANSFER)]:
            ts = tasks(private_seed ^ seed_offset, families) if families else tasks(private_seed ^ seed_offset)
            result = evaluate(g, ts, split)
            evidence_id = digest([run_id, split, digest(g)])[:24]
            evidence = {'id': evidence_id, 'run_id': run_id, 'snapshot_hash': digest(g),
                        'protocol_hash': run['protocol_hash'], 'split': split,
                        'evaluator_version': VERSION, 'result': result}
            archive.check_capacity(len(canonical(evidence)))
            with archive.db:
                archive.db.execute('INSERT INTO evidence VALUES(?,?,?)',
                                   (evidence_id, run_id, zlib.compress(canonical(evidence), 6)))
            run[split] = {**compact(result), 'evidence_id': evidence_id}
        ts = tasks(private_seed ^ 0x41A93BCD)
        run['baselines'] = {name: compact(evaluate(g, ts, 'confirm', baseline=name))
                            for name in ('last', 'expert')}
    except KeyboardInterrupt:
        run = next(r for r in archive.all('runs') if r['id'] == run_id)
        run['status'] = 'interrupted'
    except Exception:
        run['status'] = 'failed'
        raise
    finally:
        run['observed_at'] = now()
        run['cpu_seconds'] = run.get('cpu_seconds', 0) + time.process_time() - cpu0
        run['wall_seconds'] = run.get('wall_seconds', 0) + time.monotonic() - t0
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        run['peak_rss_bytes'] = rss if platform.system() == 'Darwin' else rss * 1024
        archive.run(run)
    return run


def make_event(run, ordinal, g, parent, changes, result, accepted, status, search_cost, rng_state, operator_hash):
    event_id = f"{run['id']}:{ordinal}"
    evidence_id = digest([event_id, 'train', digest(g)])[:24]
    event = {'id': event_id, 'run_id': run['id'], 'ordinal': ordinal,
             'generation': (1 if ordinal > 0 else 0) if run['condition'] == 'random' else run['accepted'] + int(accepted and ordinal > 0),
             'parent_ids': [parent] if parent else [], 'observed_at': now(),
             'snapshot_hash': digest(g), 'runtime_hash': digest(g['dialect']),
             'search_hash': digest(g['search']), 'memory_hash': digest(g['memory']),
             'operator_hash': operator_hash, 'changes': changes, 'accepted': accepted,
             'status': status, 'search_fuel': search_cost, 'score': compact(result),
             'evidence_id': evidence_id, 'rng_before': rng_state,
             'protocol_hash': run['protocol_hash']}
    ev = {'id': evidence_id, 'run_id': run['id'], 'snapshot_hash': digest(g),
          'protocol_hash': run['protocol_hash'], 'evaluator_version': VERSION,
          'split': 'train', 'result': result}
    return event, ev
