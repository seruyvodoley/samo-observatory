import json,time
from pathlib import Path
from samo.ecology import initial,advance
from samo.evaluator import tasks,evaluate
out=[]
for seed in range(24):
 s=initial(seed);start=time.process_time();events=[]
 while time.process_time()-start<.5 and s['fuel']<200000:
  s,e=advance(s);events.append(dict(accepted=e['accepted'],changes=e.get('changes'),status=e['status']))
 cpu=time.process_time()-start
 out.append(dict(seed=seed,cpu=cpu,fuel=s['fuel'],events=events,holdout=[{f:evaluate(p['genome'],tasks(91730001+seed,(f,),2),'independent exploratory',deterministic=True)['accuracy'] for f in ('constant','arithmetic','periodic','random')} for p in s['population']]))
 Path('output/search-v3/original-v2.json').write_text(json.dumps(out))
