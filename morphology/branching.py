"""Two independent inherited branches from one actual recorded founder; finite neutral drift."""
import json,random,time
from pathlib import Path
from .development import founder,mutate,develop,digest

def append_branches(path,computational,archive):
 data=json.loads(Path(path).read_text());root=founder();events=[dict(id='fork/root',parents=[],morphology_genome=root,**develop(computational,root))];samples=[]
 for seed in (100,101,0,1,2,3,4,5,6,7):
  rng=random.Random(seed);g=root;parent='fork/root'
  for n in range(100):
   rng_before=rng.getstate();child,op=mutate(g,rng);result=develop(computational,child);changed=digest(g)!=digest(child);eid=f'fork/{seed}/{n+1}'
   e=dict(id=eid,parents=[parent],morphology_genome=child,operator=op,accepted=changed,rng_before=rng_before,**result);events.append(e)
   if changed:g=child;parent=eid
  samples.append(dict(id=parent,parent=next(e['parents'][0] for e in events if e['id']==parent),accepted=True,morphology_genome=g,**develop(computational,g)))
 by_id={e['id']:e for e in events}
 pair=next((e for e in events[1:] if e.get('accepted') and e['phenotype_hash']!=by_id[e['parents'][0]]['phenotype_hash']),None)
 if pair:
  for e in [by_id[pair['parents'][0]],pair]:
   samples.append(dict(id=e['id'],parent=e['parents'][0] if e['parents'] else None,accepted=True,morphology_genome=e['morphology_genome'],**develop(computational,e['morphology_genome'])))
  data['mutation_pair']=[pair['parents'][0],pair['id']]
 data['samples']+=samples;data['fork_root']='fork/root';data['fork_descendants']=[x['id'] for x in samples]
 Path(archive).write_text(json.dumps(events,separators=(',',':')));Path(path).write_text(json.dumps(data,separators=(',',':')))
