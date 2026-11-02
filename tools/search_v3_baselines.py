import json,random
from pathlib import Path
from samo.genome import ancestor,predict
from samo.search_v3 import founder
p=Path('output/search-v3');tasks=json.loads((p/'confirmation-tasks.json').read_text());rng=random.Random(71267);out={}
for name in ('zero','last','linear','random','ancestor','founder'):
 groups={}
 for _,f,values in tasks:
  rows=groups.setdefault(f,[])
  for i in range(12,len(values)):
   h=values[:i];pred=0 if name=='zero' else h[-1] if name=='last' else (2*h[-1]-h[-2])%65536 if name=='linear' else rng.randrange(65536) if name=='random' else predict(ancestor() if name=='ancestor' else founder(),h,wall_seconds=None)[0]
   t=values[i];rows.append((pred,t))
 out[name]={f:dict(exact=sum(a==b for a,b in rows)/len(rows),normalized_error=sum(abs(a-b)/65535 if a is not None else 1 for a,b in rows)/len(rows),bit_accuracy=sum(1-bin(a^b).count('1')/16 if a is not None else 0 for a,b in rows)/len(rows)) for f,rows in groups.items()}
(p/'baselines.json').write_text(json.dumps(out,indent=2))
