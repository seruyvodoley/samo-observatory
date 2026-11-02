"""Fixed registered step pilot; reports actual cost, not equal-compute superiority."""
import json,time
from pathlib import Path
from samo.ecology_v4 import initial,advance,trials,measure
from samo.ecology import initial as old_initial,advance as old_advance
P=Path('output/core-v4');out=[]
for seed in range(12):
 for mode in ('random','gp','one_step','meta','v2'):
  start=time.process_time();s=old_initial(seed) if mode=='v2' else initial(seed,mode=mode);counts=dict(births=0,neutral=0,search_errors=0,meta_fuel=0)
  while time.process_time()-start<2 and s['fuel']<100000:
   s,e=(old_advance(s) if mode=='v2' else advance(s));counts['births']+=int(e.get('birth',False));counts['neutral']+=e.get('delta')==0;counts['search_errors']+=bool(e.get('search_error'));counts['meta_fuel']+=e.get('meta_fuel',0)
  cpu=time.process_time()-start
  out.append(dict(seed=seed,mode=mode,cpu=cpu,fuel=s['fuel'],counts=counts,population=s['population'],probe=[{k:r for k,r in measure(g['genome'],trials(987677,seed)).items() if k!='rows'} for g in s['population']]))
  (P/'comparison-budgeted.json').write_text(json.dumps(out));print(seed,mode,round(cpu,3),flush=True)
