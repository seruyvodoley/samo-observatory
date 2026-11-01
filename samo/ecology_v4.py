"""Versioned population engine. Environment persists; individual forms may die."""
import copy,json,math,random
from pathlib import Path
from .genome_v4 import digest,validate,recombine
from .search_v4 import founder,reproduce
from .evaluator_v4 import evaluate
from .engine import state_tuple
PROTOCOL='samo-ecology-v4'
PROTOCOL_HASH=digest(json.loads((Path(__file__).resolve().parents[1]/'protocols/ecology-v4.json').read_text()))

def initial(seed,size=4,mode='meta'):
 if not 2<=size<=8 or mode not in ('meta','one_step','gp','random'):raise ValueError('configuration')
 return dict(protocol=PROTOCOL,protocol_hash=PROTOCOL_HASH,seed=seed,size=size,mode=mode,rng=random.Random(seed).getstate(),step=0,episode=-1,population=[],reservoir=[],next_id=0,fuel=0,attempts=0,deaths=0,births=0,recolonizations=0,episodes=[],episode_retention=dict(pruned=0,root=digest([])),genotype_changes=0,behavior_changes=0,search_errors=0,stagnant_attempts=0,last_change=None)

def trials(seed,step):
 rng=random.Random(int(digest([seed,step,'train-v4']),16));out=[]
 for f in ('constant','arithmetic','periodic','recurrence'):
  a,b=rng.randrange(65536),rng.randrange(1,65536);p=[rng.randrange(65536) for _ in range(rng.randrange(2,6))];v=[a,b]
  for i in range(2,20):v.append((v[-1]+v[-2])&65535)
  seq=[a if f=='constant' else (a+b*i)&65535 if f=='arithmetic' else p[i%len(p)] if f=='periodic' else v[i] for i in range(20)]
  out.append((f,f,seq))
 return out

def measure(g,t):
 r=evaluate(g,t,'train',fuel_limit=4096,deterministic=True);r.pop('cpu_seconds',None);rows=r['rows']
 bits=sum(0 if x['prediction'] is None else 1-bin(x['prediction']^x['target']).count('1')/16 for x in rows)/max(1,len(rows))
 baseline=min(sum(x['target']/65535 for x in rows),sum(abs(x['prefix'][-1]-x['target'])/65535 for x in rows))/max(1,len(rows))
 r.update(bit_accuracy=bits,selection_score=.5*r['accuracy']+.25*bits+.25*(baseline-r['mae']) if r['status']=='ok' else -1)
 return r

def spawn(s,g,parents,source):
 validate(g);i=dict(id=f"v4-e{s['episode']}-n{s['next_id']}",genome=g,parents=parents,source=source,born=s['step'],failures=0,unchanged=0);s['next_id']+=1;return i

def advance(previous):
 s=copy.deepcopy(previous)
 if s['protocol']!=PROTOCOL or s['protocol_hash']!=PROTOCOL_HASH:raise ValueError('protocol')
 rng=random.Random();rng.setstate(state_tuple(s['rng']));e=dict(index=s['step'],episode=s['episode'],kind='attempt',lifecycle=[],evaluations=[],accepted=False,status='attempt',changes=[],genotype_changed=False,behavior_changed=False,birth=False)
 pop=s['population']
 if not pop:
  if s['episodes']:s['episodes'][-1].update(ended_at=s['step'],reason='extinction')
  s['episode']+=1;s['recolonizations']+=int(s['episode']>0);e.update(episode=s['episode'],kind='founding' if s['episode']==0 else 'recolonization')
  base=founder();seen=set()
  for _ in range(256):
   g,info=reproduce(base,rng,external_probability=1);s['fuel']+=info['search_fuel']
   if g is None or digest(g) in seen:continue
   seen.add(digest(g));item=spawn(s,g,[],dict(kind='registered_generator'));pop.append(item);e['lifecycle'].append(dict(kind='founder',organism=copy.deepcopy(item)))
   if len(pop)==s['size']:break
  if len(pop)!=s['size']:raise RuntimeError('generator diversity budget exhausted')
  s['episodes'].append(dict(episode=s['episode'],started_at=s['step'],ended_at=None,reason='active',sources=[dict(id=x['id'],source=x['source']) for x in pop]))
  if len(s['episodes'])>64:
   old=s['episodes'].pop(0);s['episode_retention']['root']=digest([s['episode_retention']['root'],old]);s['episode_retention']['pruned']+=1
 t=trials(s['seed'],s['step']);scores={}
 def assess(g,ident,role):
  r=measure(g,t);s['fuel']+=r['fuel'];e['evaluations'].append(dict(id=ident,genome_hash=digest(g),role=role,result=r));return r
 for x in pop:scores[x['id']]=assess(x['genome'],x['id'],'population')
 parent=max(rng.sample(pop,min(2,len(pop))),key=lambda x:scores[x['id']]['selection_score']);source=founder() if s['mode']=='random' else parent['genome'];old=scores[parent['id']]
 child,info=reproduce(source,rng,external_probability=1 if s['mode'] in ('gp','random') else .2);s['fuel']+=info['search_fuel'];s['attempts']+=1
 e.update(parent_ids=[] if s['mode']=='random' else [parent['id']],operator_hash=digest(source['search']),search_fuel=info['search_fuel'],external=info['external'],search_error=info['failure'],meta_fuel=0)
 if info['failure'] or child is None:
  parent['failures']+=1;s['search_errors']+=1;e['status']='search_failure'
 else:
  parent['failures']=0
  if s['mode']!='random' and len(pop)>1 and rng.random()<.15:
   mate=rng.choice([x for x in pop if x['id']!=parent['id']]);child,_=recombine(child,mate['genome'],rng);e['parent_ids'].append(mate['id'])
  changed=digest(child)!=digest(parent['genome']);duplicate=any(digest(child)==digest(x['genome']) for x in pop);e.update(genotype_changed=changed,duplicate=duplicate,status='candidate',changes=[k for k in ('modules','router','search','dialect','memory') if child[k]!=parent['genome'][k]])
  if changed:s['genotype_changes']+=1;parent['unchanged']=0
  else:parent['unchanged']+=1;s['stagnant_attempts']+=1
  result=assess(child,'candidate','candidate');behavior=result['behavior_hash']!=old['behavior_hash'];e['behavior_changed']=behavior;s['behavior_changes']+=int(behavior)
  bonus=0
  if s['mode']=='meta' and child['search']!=parent['genome']['search']:
   # Matched two-offspring probes; every execution is included in the same fuel ledger.
   gains=[];before=s['fuel'];probe_seed=rng.randrange(2**63)
   operator_carrier=copy.deepcopy(parent['genome']);operator_carrier['search']=copy.deepcopy(child['search'])
   for g in (parent['genome'],operator_carrier):
    productive=[];prng=random.Random(probe_seed)
    for _ in range(2):
     c,inf=reproduce(g,prng,external_probability=0);s['fuel']+=inf['search_fuel']
     productive.append(-1 if c is None or inf['failure'] else assess(c,'meta-probe','meta')['selection_score'])
    gains.append(sum(productive)/2)
   bonus=.1*(gains[1]-gains[0]);e['meta_fuel']=s['fuel']-before;e['meta_scores']=gains
  incumbent=rng.choice(pop);delta=result['selection_score']-scores[incumbent['id']]['selection_score']+bonus
  accepted=changed and not duplicate and rng.random()<math.exp(min(0,delta/.08));e.update(result=result,delta=delta,accepted=accepted)
  if accepted:
   pop.remove(incumbent);s['deaths']+=1;e['lifecycle'].append(dict(kind='death',id=incumbent['id'],reason='competition'))
   item=spawn(s,child,e['parent_ids'],dict(kind='random_search' if s['mode']=='random' else 'reproduction'));pop.append(item);e.update(candidate=copy.deepcopy(item),birth=True);s['births']+=1;s['last_change']=s['step']
 if parent in pop and (parent['failures']>=3 or parent['unchanged']>=32):
  pop.remove(parent);s['deaths']+=1;e['lifecycle'].append(dict(kind='death',id=parent['id'],reason='search_failure' if parent['failures']>=3 else 'stagnation_policy'))
 s['step']+=1;s['rng']=rng.getstate();e.update(fuel_total=s['fuel'],population_ids=[x['id'] for x in pop],state_hash=digest(s));return s,e
