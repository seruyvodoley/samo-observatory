"""Frozen diagnostic populations -> fresh external confirmation. No selection feedback."""
import json,secrets,hashlib
from pathlib import Path
from samo.ecology_v4 import trials
from samo.evaluator_v4 import evaluate
from samo.evaluator import evaluate as evaluate_v2
from samo.genome_v4 import digest
p=Path('output/core-v4');runs=json.loads((p/'comparison-budgeted.json').read_text());assert len(runs)==60
seed=secrets.randbits(128);task=[(f'{i}-{ident}',f,values) for i in range(16) for ident,f,values in trials(seed,i)]
manifest=dict(seed_commitment=hashlib.sha256(str(seed).encode()).hexdigest(),task_hash=digest(task),populations_hash=digest([r['population'] for r in runs]),criterion='all 128 predictions per family match, final frozen genotype',status='committed before assessment')
(p/'confirmation-manifest.json').write_text(json.dumps(manifest));out=[]
for run in runs:
 forms=[]
 for g in run['population']:
  result=(evaluate_v2 if run['mode']=='v2' else evaluate)(g['genome'],task,'confirm-v4-acceptance-1',deterministic=True);forms.append(dict(genome_hash=digest(g['genome']),result=result))
 out.append(dict(seed=run['seed'],mode=run['mode'],forms=forms))
(p/'confirmation.json').write_text(json.dumps(out));(p/'confirmation-tasks.json').write_text(json.dumps(task));manifest['status']='complete; tasks now disclosed, no longer a closed set';(p/'confirmation-manifest.json').write_text(json.dumps(manifest))
