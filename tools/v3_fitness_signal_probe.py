"""Paired signal diagnostic, not evidence for superior evolution."""
import random,json
from pathlib import Path
from samo.search_v3 import founder,reproduce
from samo.evaluator import evaluate
rows=[]
for seed in range(24):
 rng=random.Random(830000+seed);g=founder()
 for attempt in range(64):
  c,info=reproduce(g,rng,external_probability=.2)
  if c is None:continue
  tasks=[]
  for f in ['constant','arithmetic']:
   a,b=rng.randrange(65536),rng.randrange(1,65536);tasks.append((f,f,[a if f=='constant' else (a+b*i)%65536 for i in range(32)]))
  x=evaluate(c,tasks,'signal diagnostic',deterministic=True);y=evaluate(g,tasks,'signal diagnostic',deterministic=True)
  exact=x['accuracy']-y['accuracy'];dense=exact+.25*(y['mae']-x['mae']);rows.append(dict(seed=seed,exact_delta=exact,dense_delta=dense,failures=x['failures']))
  # Unconditional walk is diagnostic only; it is not an evolutionary selection arm.
  g=c
summary=dict(n=len(rows),seeds=24,zero_exact=sum(x['exact_delta']==0 for x in rows),zero_dense=sum(x['dense_delta']==0 for x in rows),interpretation='paired local signal resolution only; no guarantee of useful selection')
Path('output/search-v3-longitudinal/signal-probe.txt').write_text(json.dumps(dict(summary=summary,rows=rows)));print(summary)
