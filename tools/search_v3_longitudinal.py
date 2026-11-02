"""Preregistered CPU checkpoints; separate retention; no production access."""
import copy,json,math,random,time,secrets,os
from pathlib import Path
from samo.search_v3 import founder,reproduce
from samo.genome import digest
from samo.evaluator import evaluate
P=Path('output/search-v3-longitudinal');P.mkdir(exist_ok=True,parents=True)
def tasks(rng,n=2):
 out=[]
 for family in ('constant','arithmetic','periodic'):
  for k in range(n):
   a,b=rng.randrange(65536),rng.randrange(1,65536);p=[rng.randrange(65536) for _ in range(rng.randrange(2,6))]
   values=[a if family=='constant' else (a+b*i)%65536 if family=='arithmetic' else p[i%len(p)] for i in range(32)];out.append((family+str(k),family,values))
 return out

def measured(g,t):
 r=evaluate(g,t,'train',deterministic=True);rows=r['rows'];zero=sum(x['target']/65535 for x in rows)/len(rows);last=sum(abs(x['prefix'][-1]-x['target'])/65535 for x in rows)/len(rows)
 # Signed advantage against both baseline losses: zero cannot improve by range bias alone.
 r['score']=r['accuracy']+.25*(min(zero,last)-r['mae']);return r

def confirm(pop):
 t=tasks(random.Random(secrets.randbits(128)),32)
 return {'tasks':t,'genomes':[digest(g) for g in pop],'scores':[evaluate(g,t,'confirmation',deterministic=True)['families'] for g in pop]}
for seed in range(24):
 if seed%4!=int(os.environ.get("SAMO_SHARD","0")):continue
 for arm in ('gp','meta0','meta20','meta100','frozen20'):
  path=P/(str(seed)+'-'+arm+'.json')
  if path.exists():continue
  rng=random.Random(seed);pop=[founder() for _ in range(4)];fuel=0;external_words=0;events=[];snapshots=[];start=time.process_time();failed=None
  try:
   for budget in (1,3,10,12):
    phase_start=time.process_time()
    while time.process_time()-start<budget and fuel<3000000:
     i=rng.randrange(4);source=copy.deepcopy(pop[i]);prob={'gp':1,'meta0':0,'meta20':.2,'meta100':1,'frozen20':.2}[arm]
     c,info=reproduce(source,rng,external_probability=prob,search_operator=founder()['search'] if arm=='frozen20' else None);fuel+=info['search_fuel'];external_words+=5*int(info['external']);e=dict(index=len(events),external=info['external'],failure=info['failure'],birth=False)
     if c is not None:
      t=tasks(rng,1);a=measured(c,t);b=measured(pop[i],t);fuel+=a['fuel']+b['fuel'];delta=a['score']-b['score'];changed=digest(c)!=digest(pop[i]);duplicate=any(digest(c)==digest(g) for g in pop);accept=rng.random()<math.exp(min(0,delta/.08));e.update(delta=delta,genotype_changed=changed,behavior_changed=a['behavior_hash']!=b['behavior_hash'],accepted=accept,regression=delta<0,duplicate=duplicate)
      if accept and changed and not duplicate:pop[i]=c;e['birth']=True
     events.append(e)
    frozen=copy.deepcopy(pop);cpu=time.process_time()-start
    # Confirmation expense excluded from acquisition CPU and fuel, recorded separately.
    cs=time.process_time();confirmation=confirm(frozen);confirm_cpu=time.process_time()-cs;start+=confirm_cpu
    snapshots.append(dict(budget=budget,phase='retention' if budget==12 else 'acquisition',cpu=cpu,fuel=fuel,external_words=external_words,population=frozen,confirmation_cpu=confirm_cpu,confirmation=confirmation))
  except Exception as exc:failed=repr(exc)
  path.write_text(json.dumps(dict(seed=seed,arm=arm,snapshots=snapshots,events=events,failure=failed)))
  print(seed,arm,len(events),failed,flush=True)
