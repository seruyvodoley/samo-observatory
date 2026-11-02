"""Independent observer only. Never advances or modifies the v4 scientific checkpoint."""
import json,sys,os,re
from morphology.observer_v5 import verified_snapshot
from pathlib import Path
from collections import Counter
from morphology.runtime_v5 import Recorder,public_snapshot,unpack,atomic_json,public_form
from samo.genome_v4 import digest,validate

r=Recorder(sys.argv[1],readonly=True)
path=Path(sys.argv[3]);a=json.loads(path.read_text()) if path.exists() else dict(last=-1,gaps=[],bins=[],milestones=[],folded=dict(bins=0,root=digest([]),counts={}),counts={},current={})
p=verified_snapshot(r,a.setdefault('verification',{}))
forms={x['id']:x for x in p['population']};history=[];search_observations={};public_events={x['index']:x for x in p['events']}
for n,blob,h in r.db.execute('SELECT n,payload,hash FROM events ORDER BY n'):
 outer=unpack(blob)
 if digest(outer)!=h:raise ValueError('event checksum')
 e=outer['computational']
 traits={x['id']:{k:x[k] for k in ('morphology_genome','morphology_hash','phenotype_hash','interpreter')} for x in outer['morphology']}
 public_events[n]['morphology']=[{k:x[k] for k in ('id','parent','morphology_changed','morphology_effect','computational_effect','phenotype_changed','morphology_hash','phenotype_hash')} for x in outer['morphology']]
 projected=public_events[n];projected['family']='balanced';projected['family_accuracy']=e.get('result',{}).get('families',{});projected['evaluation_status']=e.get('result',{}).get('status');projected['training_predictions']=e.get('result',{}).get('total',0)
 if not e.get('external',True) and e.get('parent_ids'):
  parent=next((v for v in e['evaluations'] if v['id']==e['parent_ids'][0]),None)
  if parent:search_observations[parent['genome_hash']]=not bool(e.get('search_error'))
 for item in e['lifecycle']:
  if item['kind']=='founder':
   x=item['organism'];forms[x['id']]=dict(x,hash=digest(x['genome']))
 candidate=e.get('candidate')
 if candidate:
  validate(candidate['genome']);x=dict(candidate,hash=digest(candidate['genome']),accepted=e['accepted'],_trait=traits[candidate['id']]);history.append(x);history=history[-80:];forms[x['id']]=x
  while len(forms)>128:forms.pop(next(iter(forms)))
 if n<=a['last']:continue
 if n>a['last']+1:a['gaps'].append([a['last']+1,n-1])
 counts=dict(attempts=1,candidates=int('result' in e),accepted=int(e.get('accepted',False)),sterile=int(e.get('status')=='search_failure'),zero_accuracy=int('result' in e and e['result']['accuracy']==0),nonzero_delta=int(e.get('delta',0)!=0),recolonizations=int(e['kind']=='recolonization'),deaths=sum(x['kind']=='death' for x in e['lifecycle']))
 if 'result' in e:counts.update(accuracy_sum=e['result']['accuracy'],mae_sum=e['result']['mae'],prediction_failures=e['result']['failures'])
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
active=[search_observations[x['hash']] for x in p['population'] if x['hash'] in search_observations]
p['telemetry']['active_search_observations']=dict(population=len(p['population']),tested=len(active),last_success=sum(active),unknown=len(p['population'])-len(active),scope='last retained endogenous execution of each active genotype in its own memory and dialect context')
p['exporter_hash']=digest(Path(__file__).read_text());p['history']=[dict(public_form(x,x['_trait']),accepted=x['accepted']) for x in history[-80:]];p['snapshot_id']=r.db.execute('SELECT hash FROM checkpoint').fetchone()[0];p['long_term']={k:v for k,v in a.items() if k!='verification'}
# Both files stay bounded; old raw information is explicitly absent, not silently complete.
atomic_json(path,a)
while len(json.dumps(p))>3_800_000 and p['history']:p['history'].pop(0)
p['history_scope']=dict(retained=len(p['history']),raw_attempts=len(p['events']),complete=False)
# Public ids have a distinct namespace from retained v4 history; raw recorder ids remain unchanged for paired replay.
def namespace(x):
 if isinstance(x,str) and re.fullmatch(r'v4-e[0-9]+-n[0-9]+',x):return 'v5-'+x[3:]
 if isinstance(x,list):return [namespace(v) for v in x]
 if isinstance(x,dict):return {k:namespace(v) for k,v in x.items()}
 return x
p=namespace(p);p['identity_namespace']='v5 public birth ids alias the immutable computational v4 birth ids inside protocol v5'
atomic_json(sys.argv[2],p);r.close()
