"""Independent observer only. Never advances or modifies the v2 scientific checkpoint."""
import json,sys,os
from pathlib import Path
from collections import Counter
from samo.ecology_runtime import Recorder,public_snapshot,unpack,atomic_json
from samo.genome import digest,validate

r=Recorder(sys.argv[1],readonly=True);p=public_snapshot(r)
path=Path(sys.argv[3]);a=json.loads(path.read_text()) if path.exists() else dict(last=-1,gaps=[],bins=[],milestones=[],folded=dict(bins=0,root=digest([]),counts={}),counts={},current={})
forms={x['id']:x for x in p['population']};history=[]
for n,blob,h in r.db.execute('SELECT n,payload,hash FROM events ORDER BY n'):
 e=unpack(blob)
 if digest(e)!=h:raise ValueError('event checksum')
 for item in e['lifecycle']:
  if item['kind']=='founder':
   x=item['organism'];forms[x['id']]=dict(x,hash=digest(x['genome']))
 candidate=e.get('candidate')
 if candidate:
  validate(candidate['genome']);x=dict(candidate,hash=digest(candidate['genome']),accepted=e['accepted']);history.append(x);history=history[-80:];forms[x['id']]=x
  while len(forms)>128:forms.pop(next(iter(forms)))
 if n<=a['last']:continue
 if n>a['last']+1:a['gaps'].append([a['last']+1,n-1])
 counts=dict(attempts=1,candidates=int(candidate is not None),accepted=int(e.get('accepted',False)),sterile=int(e.get('status')=='sterile'),zero_accuracy=int(candidate is not None and e['result']['accuracy']==0),nonzero_delta=int(e.get('delta',0)!=0),recolonizations=int(e['kind']=='recolonization'),deaths=sum(x['kind']=='death' for x in e['lifecycle']))
 if candidate:counts.update(accuracy_sum=e['result']['accuracy'],mae_sum=e['result']['mae'],prediction_failures=e['result']['failures'])
 for k,v in counts.items():a['counts'][k]=a['counts'].get(k,0)+v;a['current'][k]=a['current'].get(k,0)+v
 if candidate and any(k in e.get('changes',[]) for k in ['modules','memory','search','dialect']):
  parent=forms.get(e['parent_ids'][0]);shape=lambda g:dict(modules=len(g['modules']),instructions=sum(len(x) for x in g['modules']),memory=len(g['memory']),search=len(g['search']),dialect=sum(map(len,g['dialect'])))
  before=shape(parent['genome']) if parent else None;after=shape(candidate['genome'])
  a['milestones'].append(dict(step=n,id=candidate['id'],parents=e['parent_ids'],hash=digest(candidate['genome']),changes=e['changes'],before=before,after=after,loss=before is not None and any(after[k]<before[k] for k in after),accepted=e['accepted'],accuracy=e['result']['accuracy'],behavior_hash=e['result']['behavior_hash']))
  a['milestones']=a['milestones'][-64:]
 if (n+1)%1000==0:
  a['bins'].append(dict(through=n,counts=a['current']));a['current']={}
  if len(a['bins'])>256:
   old=a['bins'].pop(0);a['folded']['bins']+=1;a['folded']['root']=digest([a['folded']['root'],old])
   for k,v in old['counts'].items():a['folded']['counts'][k]=a['folded']['counts'].get(k,0)+v
 a['last']=n
 a['gaps']=a['gaps'][-64:]
p['history']=history[-80:];p['snapshot_id']=r.db.execute('SELECT hash FROM checkpoint').fetchone()[0];p['long_term']=a
# Both files stay bounded; old raw information is explicitly absent, not silently complete.
atomic_json(path,a)
while len(json.dumps(p))>3_800_000 and p['history']:p['history'].pop(0)
p['history_scope']=dict(retained=len(p['history']),raw_attempts=len(p['events']),complete=False)
atomic_json(sys.argv[2],p);r.close()
