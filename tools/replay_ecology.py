"""Regenerate a consistent private archive copy; never print seeds or raw private tasks."""
import sys
from samo.ecology import initial, advance
from samo.ecology_runtime import Recorder
from samo.genome import digest

r=Recorder(sys.argv[1],readonly=True)
target=r.load()
rows=dict(r.db.execute('SELECT n,hash FROM events'))
row=r.db.execute('SELECT payload FROM retention WHERE id=1').fetchone()
import json
retention=json.loads(row[0]) if row else dict(pruned_records=0,root=digest([]),through=-1)
state=initial(target['seed'],target['size']);root=digest([]);matched=0
for i in range(target['step']):
    state,event=advance(state)
    if i<=retention['through']: root=digest([root,i,digest(event)])
    if i in rows:
        if rows[i]!=digest(event): raise ValueError('event replay mismatch at '+str(i))
        matched+=1
if digest(state)!=digest(target) or root!=retention['root']: raise ValueError('checkpoint/retention replay mismatch')
print(json.dumps(dict(steps=state['step'],retained_events_reproduced=matched,checkpoint='exact',thinned_root='exact',source='matching archived runtime')))
r.close()
