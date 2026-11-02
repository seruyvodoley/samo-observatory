"""Isolated exploratory comparisons. No production reads/writes."""
import copy,json,random,time,statistics
from pathlib import Path
from samo.search_v3 import founder,reproduce,edit
from samo.genome import digest,reproduce as old_reproduce,ancestor
from samo.evaluator import tasks,evaluate
from samo.vm import ins
OUT=Path('output/search-v3');OUT.mkdir(parents=True,exist_ok=True)
def metric(r):
 rows=r['rows'];return dict(exact=r['accuracy'],error=r['mae'],bits=sum(0 if x['prediction'] is None else 1-bin(x['prediction']^x['target']).count('1')/16 for x in rows)/max(1,len(rows)),fuel=r['fuel'],failures=r['failures'])
def quality(m):return .5*m['exact']+.25*(1-m['error'])+.25*m['bits']
def probe(g,seed):return {f:metric(evaluate(g,tasks(seed,(f,),2),'independent exploratory',deterministic=True)) for f in ('constant','arithmetic','periodic','random')}
runs=[]
for seed in range(24):
 for arm in ('random','gp','meta','v2'):
  rng=random.Random(seed);base=founder();pop=[copy.deepcopy(base) for _ in range(4)];fuel=0;events=[];start=time.process_time()
  while time.process_time()-start<.5 and fuel<200000:
   parent=rng.randrange(4);source=base if arm=='random' else pop[parent]
   if arm=='v2':child,_,cost,status=old_reproduce(source,rng,wall_seconds=None);info=dict(search_fuel=cost,failure=status)
   else:child,info=reproduce(source,rng,arm)
   fuel+=info['search_fuel'];e=dict(attempt=len(events),**info,birth=False)
   if child is not None:
    changed=digest(child)!=digest(source);duplicate=any(digest(child)==digest(p) for p in pop);e.update(genotype_changed=changed,duplicate=duplicate)
    # Same task prefixes for both candidate and incumbent. Not a closed test.
    task=tasks(seed*100000+len(events),('constant','arithmetic','periodic'),1)
    incumbent=rng.randrange(4);a=evaluate(child,task,'train',deterministic=True);b=evaluate(pop[incumbent],task,'train',deterministic=True);fuel+=a['fuel']+b['fuel']
    ma,mb=metric(a),metric(b);delta=(ma['exact']-mb['exact']) if arm=='v2' else quality(ma)-quality(mb)
    accepted=rng.random()<__import__('math').exp(min(0,delta/.08));e.update(accepted=accepted,behavior_changed=a['behavior_hash']!=b['behavior_hash'],delta=delta)
    if changed and not duplicate and accepted:pop[incumbent]=child;e['birth']=True
    assert not(e['birth'] and (not changed or duplicate))
   events.append(e)
  cpu=time.process_time()-start
  # Final candidates frozen before independent task evaluation.
  final=copy.deepcopy(pop);holdout=[probe(g,91730001+seed) for g in final]
  # Continued mutations assess retention, without restoring a best ancestor.
  for _ in range(20):
   i=rng.randrange(4);c,_=reproduce(pop[i],rng,'meta' if arm=='meta' else 'gp')
   if c is not None and digest(c)!=digest(pop[i]):pop[i]=c
  retention=[probe(g,92730001+seed) for g in pop]
  runs.append(dict(seed=seed,arm=arm,cpu=cpu,fuel=fuel,events=events,population=final,holdout=holdout,retention=retention))
  (OUT/'results.json').write_text(json.dumps(runs));print(seed,arm,len(events),flush=True)
controls={}
for name,code in [('zero',[ins('CONST')]),('last',[ins('HIST')]),('linear',[ins('HIST'),ins('HIST'),ins('HIST',1),ins('SUB'),ins('ADD')])]:
 g=founder();g['modules']=[code];controls[name]=probe(g,91730001)
controls['ancestor']=probe(ancestor(),91730001)
(OUT/'controls.json').write_text(json.dumps(controls,indent=2))
