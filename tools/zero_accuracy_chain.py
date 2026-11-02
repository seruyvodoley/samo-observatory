import json,random,collections,hashlib
from pathlib import Path
from samo.genome import digest,apply_edits,ancestor
from samo.vm import execute,Meter
p=Path('output/zero-audit');r=json.loads((p/'recorder.json').read_text());out={'step':r['state']['step'],'events':len(r['events']),'checks':0,'mismatches':[],'emissions':[]}
for e in r['events']:
 for v in e['evaluations']+([{'result':e['result']}] if 'result'in e else []):
  z=v['result'];rows=z['rows'];out['checks']+=1
  if z['total']!=len(rows) or z['accuracy']!=sum(x['correct'] for x in rows)/max(1,len(rows)):out['mismatches'].append(e['index'])
  for x in rows:
   assert x['correct']==(x['prediction'] is not None and x['prediction']==x['target'])
   assert x['commitment']==digest(dict(task_id=x['task_id'],index=x['index'],prediction=x['prediction'],prefix_hash=digest(x['prefix'])))
for name in ['public','vps']:
 x=json.loads((p/(name+'.json')).read_text());raw={e['index']:e for e in r['events']};matches=0
 for e in x['events']:
  if e['index'] not in raw:continue
  z=raw[e['index']];assert e['accuracy']==z.get('result',{}).get('accuracy');assert e.get('delta')==z.get('delta');assert e['accepted']==z['accepted'];matches+=1
 out[name+'_overlap_verified']=matches
for g in r['state']['population']:
 _,em,_=execute(g['genome']['search'],(),g['genome']['memory'],g['genome']['dialect'],random.Random(123),Meter(512,deadline=float('inf')))
 edits=[em[i:i+4] for i in range(0,len(em)-3,4)];out['emissions'].append(dict(id=g['id'],emitted=len(em),edits=len(edits),zero_value=sum(a[3]==0 for a in edits),sample=edits[:5]))
(p/'chain.json').write_text(json.dumps(out,indent=2));print(out)
