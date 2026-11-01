"""Population protocol v2. Pure deterministic step; trusted recorder owns durable state."""
import copy
import math
import random
import json
from pathlib import Path
from .evaluator import FAMILIES, task_stream, evaluate
from .genome import ancestor, reproduce, recombine, digest, validate
from .engine import state_tuple

PROTOCOL = 'samo-ecology-v2'
PROTOCOL_HASH = digest(json.loads((Path(__file__).resolve().parents[1]/'protocols/ecology-v2.json').read_text()))

def initial(seed, size=4):
    if not 2 <= size <= 8: raise ValueError('population limit')
    return dict(protocol=PROTOCOL, protocol_hash=PROTOCOL_HASH, seed=seed, size=size, rng=random.Random(seed).getstate(),
                step=0, episode=-1, population=[], reservoir=[], next_id=0,
                fuel=0, attempts=0, deaths=0, births=0, recolonizations=0,
                episodes=[], episode_retention=dict(pruned=0,root=digest([])))

def organism(s, genome, parents, source):
    validate(genome)
    ident=f"e{s['episode']}-n{s['next_id']}"
    s['next_id']+=1
    return dict(id=ident, genome=genome, parents=parents, source=source, born=s['step'])

def measure(g, task):
    result=evaluate(g, task, 'train', fuel_limit=4096, raw=True, deterministic=True)
    result.pop('cpu_seconds', None)  # deterministic scientific record; OS cost is external
    return result

def advance(previous):
    s=copy.deepcopy(previous)
    if s['protocol']!=PROTOCOL: raise ValueError('protocol')
    rng=random.Random(); rng.setstate(state_tuple(s['rng']))
    e=dict(index=s['step'], episode=s['episode'], kind='attempt', lifecycle=[], evaluations=[])
    if not s['population']:
        if s['episodes']:
            s['episodes'][-1].update(ended_at=s['step'],reason='extinction')
        s['episode']+=1
        s['recolonizations']+=int(s['episode']>0)
        e['episode']=s['episode']; e['kind']='founding' if s['episode']==0 else 'recolonization'
        for _ in range(s['size']):
            # Registered external colonization; no ranking by historical fitness.
            if s['reservoir'] and rng.random()<0.5:
                donor=rng.choice(s['reservoir']); g=copy.deepcopy(donor['genome'])
                source=dict(kind='diversity', id=donor['id'], hash=digest(g))
            else:
                base=ancestor(); g,_,cost,status=reproduce(base,rng,wall_seconds=None)
                s['fuel']+=cost
                if g is None: g=base
                source=dict(kind='registered_generator', hash=digest(base))
            item=organism(s,g,[],source); s['population'].append(item)
            e['lifecycle'].append(dict(kind='founder', organism=copy.deepcopy(item)))
        s['episodes'].append(dict(episode=s['episode'],started_at=s['step'],ended_at=None,
                                 reason='active',sources=[dict(id=x['id'],source=x['source']) for x in s['population']]))
        if len(s['episodes'])>64:
            removed=s['episodes'].pop(0)
            retention=s['episode_retention'];retention['root']=digest([retention['root'],removed]);retention['pruned']+=1
    family=FAMILIES[s['step']%len(FAMILIES)]
    task_seed,task=task_stream(s['seed'],s['step'],(family,),1)
    e.update(task_index=s['step'],task_seed=task_seed,family=family,task_hash=digest(task))
    pop=s['population']; scores={}
    for item in pop:
        result=measure(item['genome'],task); scores[item['id']]=result['accuracy']
        e['evaluations'].append(dict(id=item['id'],genome_hash=digest(item['genome']),result=result))
        s['fuel']+=result['fuel']
    parent=max(rng.sample(pop,min(2,len(pop))), key=lambda x:scores[x['id']])
    mates=[x for x in pop if x['id']!=parent['id']]
    mate=rng.choice(mates) if mates else None
    child,changes,cost,status=reproduce(parent['genome'],rng,wall_seconds=None)
    s['fuel']+=cost; s['attempts']+=1
    e.update(parent_ids=[parent['id']],operator_hash=digest(parent['genome']['search']),search_fuel=cost)
    if child is None:
        pop.remove(parent); s['deaths']+=1
        e['lifecycle'].append(dict(kind='death',id=parent['id'],reason=status))
        e.update(accepted=False,status='sterile')
    else:
        if mate and rng.random()<0.35:
            child,cross=recombine(child,mate['genome'],rng)
            e['parent_ids'].append(mate['id'])
        changes=[k for k in ('modules','router','search','dialect','memory') if child[k]!=parent['genome'][k]]
        result=measure(child,task); s['fuel']+=result['fuel']
        candidate=organism(s,child,e['parent_ids'],dict(kind='reproduction'))
        incumbent=rng.choice(pop)
        delta=result['accuracy']-scores[incumbent['id']]
        accepted=len(pop)<s['size'] or rng.random()<math.exp(min(0,delta/0.08))
        e.update(candidate=candidate,result=result,changes=changes,accepted=accepted,status='candidate',delta=delta)
        if accepted:
            if len(pop)>=s['size']:
                pop.remove(incumbent); s['deaths']+=1
                e['lifecycle'].append(dict(kind='death',id=incumbent['id'],reason='competition'))
            pop.append(candidate); s['births']+=1
            if not any(digest(x['genome'])==digest(child) for x in s['reservoir']):
                if len(s['reservoir'])==32:
                    evicted=s['reservoir'].pop(0)
                    e['lifecycle'].append(dict(kind='diversity_eviction',id=evicted['id'],hash=digest(evicted['genome'])))
                s['reservoir'].append(copy.deepcopy(candidate))
    s['step']+=1; s['rng']=rng.getstate()
    e['fuel_total']=s['fuel']; e['population_ids']=[x['id'] for x in pop]
    e['state_hash']=digest(s)
    return s,e
