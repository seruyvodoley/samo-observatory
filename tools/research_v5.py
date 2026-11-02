"""Registered paired computational-path and heritability validation, no aesthetic selection."""
import copy,gzip,json,time
from pathlib import Path
from morphology.ecology_v5 import initial,advance,PROTOCOL_HASH
from samo.ecology_v4 import advance as baseline
from morphology.development import digest
out=Path('output/morphology-v5');out.mkdir(exist_ok=True)
plan=json.loads(Path('protocols/v5-acceptance.json').read_text());rows=[]
with gzip.open(out/'paired-events.jsonl.gz','wt') as raw:
 for seed in plan['seeds']:
  s=initial(seed);control=copy.deepcopy(s['core']);t=time.process_time();counts=dict(births=0,morphology_changes=0,morphology_effects=0,neutral=0,truncated=0);shapes=set()
  for _ in range(plan['steps_per_seed']):
   s,e=advance(s);control,ce=baseline(control);assert s['core']==control;assert e['computational']==ce
   for r in e['morphology']:
    counts['births']+=1;counts['morphology_changes']+=r['morphology_changed'];counts['morphology_effects']+=r['morphology_effect'];counts['neutral']+=r['morphology_changed'] and not r['morphology_effect'];counts['truncated']+=r['truncated'];shapes.add(r['phenotype_hash'])
   raw.write(json.dumps(dict(seed=seed,event=e),separators=(',',':'))+'\n')
  rows.append(dict(seed=seed,steps=plan['steps_per_seed'],**counts,distinct_observed_phenotypes=len(shapes),morphology_fuel=s['morphology_fuel'],cpu_paired_seconds=time.process_time()-t,final_state_hash=digest(s),computational_state_hash=digest(control),protocol_hash=PROTOCOL_HASH))
  (out/f'final-seed-{seed}.json').write_text(json.dumps(s,separators=(',',':')))
(out/'paired-summary.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows))
