"""Offline exploratory audit. No production writes or protocol changes."""
import copy,json,random,collections,time,types
from pathlib import Path
from unittest.mock import patch
from samo import ecology,genome
from samo.evaluator import evaluate,tasks
from samo.vm import ins,execute,Meter
OUT=Path('output/zero-audit');OUT.mkdir(exist_ok=True)
def metrics(r):
 rows=r['rows'];return dict(exact=r['accuracy'],normalized_absolute_error=r['mae'],bit_accuracy=sum(0 if x['prediction'] is None else 1-bin(x['prediction']^x['target']).count('1')/16 for x in rows)/max(1,len(rows)),failures=r['failures'],predictions=len(rows),fuel=r['fuel'])
def score(r):
 m=metrics(r);return .5*m['exact']+.25*(1-m['normalized_absolute_error'])+.25*m['bit_accuracy']
def panel(g,seed):
 return {f:metrics(evaluate(g,tasks(seed,(f,),3),'diagnostic',deterministic=True)) for f in ('constant','arithmetic','periodic','recurrence','switch','random')}
def controls():
 result={}
 codes={'last':[ins('HIST')],'linear':[ins('HIST'),ins('HIST'),ins('HIST',1),ins('SUB'),ins('ADD')],**{f'period{p}':[ins('HIST',p-1)] for p in range(2,6)}}
 for name,code in codes.items():
  g=genome.ancestor();g['modules']=[code];g['router']=[ins('CONST',0)];result[name]=panel(g,734819)
 assert result['last']['constant']['exact']==1
 assert result['linear']['arithmetic']['exact']==1
 # Fixed period controls test representability, never seeded into evolving populations.
 periodic={}
 for p in range(2,6):
  g=genome.ancestor();g['modules']=[codes[f'period{p}']];g['router']=[ins('CONST')]
  seq=[(i%p)*31+7 for i in range(24)]
  periodic[str(p)]=metrics(evaluate(g,[('fixed-period','periodic',seq)],'diagnostic',deterministic=True));assert periodic[str(p)]['exact']==1
 return dict(panel=result,fixed_period=periodic)
def snapshot(name):
 x=json.loads((OUT/(name+'.json')).read_text());e=[v for v in x['events'] if v.get('status')=='candidate'];pop=[]
 for p in x['population']:
  code=sum(p['genome']['modules']+p['genome']['dialect']+[p['genome']['router'],p['genome']['search']],[]);counts=collections.Counter(map(tuple,code));pop.append(dict(id=p['id'],instructions=len(code),const_fraction=sum(i[0]==0 for i in code)/len(code),const_minus1724=counts[(0,-1724)],probe=panel(p['genome'],734819)))
 return dict(step=x['step'],generated_at=x['generated_at'],window=len(e),zero_exact=sum(v.get('accuracy')==0 for v in e),zero_delta=sum(v.get('delta')==0 for v in e),accepted=sum(v['accepted'] for v in e),unchanged=sum(not v.get('changes') for v in e),population=pop)
# Register fixed exploratory design before any comparison results are computed.
design=dict(status='exploratory pilot, not confirmatory',protocol='samo-ecology-v3-candidate-1',seeds=[31,47,83,109,151],fuel_ceiling=80000,arms=['v2','zero_noop','dense_only','v3'],selection='.5 exact + .25 (1-normalized absolute error) + .25 bit accuracy',zero_edit='skip code insertion/replacement with value=0; deletion and memory/architecture edits unchanged',holdout_seed=988172,stopping='stop after first complete step reaching fuel ceiling; record overshoot; equal charged VM fuel target, actual totals and CPU reported',limits='No monotonicity, no elite restoration, unchanged offspring search VM, no diagnostic controls seeded into population.')
(OUT/'v3-design.json').write_text(json.dumps(design,indent=2))
base_apply=genome.apply_edits

def zero_apply(g,emitted,condition='samo'):
 filtered=[]
 for i in range(0,len(emitted)-3,4):
  target,pos,kind,value=emitted[i:i+4]
  if value==0 and target%6 in (0,1,2,4) and kind%3!=1:continue
  filtered.extend((target,pos,kind,value))
 return base_apply(g,filtered,condition)

def run(arm,seed):
 source=Path(ecology.__file__).read_text();dense=arm in ('dense_only','v3')
 if dense:source=source.replace("scores[item['id']]=result['accuracy']","scores[item['id']]=score(result)").replace("delta=result['accuracy']-scores[incumbent['id']]","delta=score(result)-scores[incumbent['id']]")
 module=types.ModuleType('samo.audit_variant');module.__package__='samo';module.__file__=ecology.__file__;exec(compile(source,module.__file__,'exec'),module.__dict__);module.score=score
 s=module.initial(seed);events=[];start=time.process_time()
 with patch.object(genome,'apply_edits',zero_apply if arm in ('zero_noop','v3') else base_apply):
  while s['fuel']<design['fuel_ceiling']:
   s,e=module.advance(s);events.append(dict(accepted=e['accepted'],delta=e.get('delta'),accuracy=e.get('result',{}).get('accuracy'),changes=e.get('changes'),status=e['status']))
 cpu=time.process_time()-start
 return dict(arm=arm,seed=seed,fuel=s['fuel'],overshoot=s['fuel']-design['fuel_ceiling'],steps=s['step'],cpu_seconds=cpu,events=events,holdout=[panel(p['genome'],design['holdout_seed']) for p in s['population']],population=s['population'])
result=dict(snapshots={n:snapshot(n) for n in ('public','vps')},controls=controls(),zero_decode=genome.apply_edits(genome.ancestor(),[0,0,0,0])[0]['modules'][0][0],runs=[])
for seed in design['seeds']:
 for arm in design['arms']:
  r=run(arm,seed);result['runs'].append(r);(OUT/'diagnostics.json').write_text(json.dumps(result,indent=2));print(arm,seed,r['steps'],r['fuel'],flush=True)
