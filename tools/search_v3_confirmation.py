import json,random,secrets,hashlib
from pathlib import Path
from samo.evaluator import evaluate
from samo.genome import digest
x=json.loads(Path('output/search-v3/results.json').read_text());seed=secrets.randbits(128)
p=Path('.private/search-v3-confirmation-seed.json');p.write_text(json.dumps({'seed':seed}));p.chmod(0o600)
manifest=dict(seed_commitment=hashlib.sha256(str(seed).encode()).hexdigest(),genome_commitment=digest([r['population'] for r in x]),criterion='all 1280 predictions correct per family; frozen final genotypes; no tuning after confirmation',families=['constant','arithmetic','periodic'],tasks_per_family=64,horizon=20,range='full 16-bit',status='committed before evaluations')
Path('output/search-v3/confirmation-manifest.json').write_text(json.dumps(manifest,indent=2))
rng=random.Random(seed);task=[]
for f in manifest['families']:
 for n in range(64):
  a,b=rng.randrange(65536),rng.randrange(1,65536);period=[rng.randrange(65536) for _ in range(rng.randrange(2,6))]
  values=[a if f=='constant' else (a+b*i)%65536 if f=='arithmetic' else period[i%len(period)] for i in range(32)];task.append((f+'-'+str(n),f,values))
out=[]
for r in x:
 forms=[]
 for g in r['population']:
  z=evaluate(g,task,'confirmation-v3-1',deterministic=True);forms.append(dict(hash=digest(g),families=z['families'],failures=z['failures'],fuel=z['fuel']))
 out.append(dict(seed=r['seed'],arm='legacy-abi' if r['arm']=='v2' else r['arm'],forms=forms))
Path('output/search-v3/confirmation.json').write_text(json.dumps(out,indent=2));Path('output/search-v3/confirmation-tasks.json').write_text(json.dumps(task));manifest['status']='complete; tasks now disclosed, cannot reuse as closed confirmation';Path('output/search-v3/confirmation-manifest.json').write_text(json.dumps(manifest,indent=2))
