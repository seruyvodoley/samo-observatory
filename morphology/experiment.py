"""Finite isolated heritable lines, atomic recorder, reproducible random state."""
import argparse, copy, json, random, sqlite3, time
from pathlib import Path
from .development import founder,develop,mutate,digest,VERSION

def state_tuple(x):return tuple(state_tuple(v) if isinstance(v,list) else v for v in x)
def run(db_path,computational,seeds=range(8),steps=100):
 db=sqlite3.connect(db_path);db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA max_page_count=25600')
 db.execute('CREATE TABLE IF NOT EXISTS lines (id TEXT PRIMARY KEY,state TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS events (line TEXT,n INTEGER,payload TEXT,PRIMARY KEY(line,n))')
 protocol=json.loads(Path('protocols/morphogenesis-v1.json').read_text());results=[]
 identity=digest(dict(protocol=protocol,computational=computational,source=[Path('morphology/development.py').read_text(),Path(__file__).read_text()]))
 for selection in protocol['selection']:
  for mode in protocol['representations']:
   for seed in seeds:
    lid=f'{selection}/{mode}/{seed}';row=db.execute('SELECT state FROM lines WHERE id=?',(lid,)).fetchone()
    rng=random.Random(seed)
    state=json.loads(row[0]) if row else dict(n=0,genome=founder(),id=lid+'/founder',rng=rng.getstate(),seen=[],accepted=0,neutral=0,rejected=0,cpu=0.,fuel=0)
    if row and state.get('experiment_identity')!=identity:raise ValueError('source/protocol/input mismatch')
    state['experiment_identity']=identity
    rng.setstate(state_tuple(state['rng']))
    while state['n']<steps:
     t=time.process_time();parent=copy.deepcopy(state['genome']);before=develop(computational,parent)
     child,operator=(parent,'fixed') if mode=='fixed' else mutate(parent,rng,'parameter' if mode=='parameter' else 'generative')
     # Structural ablation permits topology edits but freezes parameter-only changes.
     if mode=='structural' and operator=='parameter':child=parent
     after=develop(computational,child);changed=digest(child)!=digest(parent);phenotype=after['phenotype_hash']!=before['phenotype_hash']
     accept=changed and (selection=='neutral' or (selection=='cost' and after['fuel']<=before['fuel']) or (selection=='novelty' and after['phenotype_hash'] not in state['seen']))
     eid=f'{lid}/{state["n"]+1}'
     event=dict(id=eid,parent_id=state['id'],parent_genome=parent,morphology_genome=child,computational_hash=digest(computational),parent_hash=digest(parent),morphology_hash=digest(child),phenotype_hash=after['phenotype_hash'],interpreter=VERSION,operator=operator,genotype_changed=changed,phenotype_changed=phenotype,accepted=accept,reason='accepted' if accept else 'unchanged_or_selection',truncated=after['truncated'],fuel=after['fuel'],rng_before=state['rng'])
     state['n']+=1;state['rng']=rng.getstate();state['fuel']+=after['fuel']+before['fuel'];state['cpu']+=time.process_time()-t
     if accept:state['genome']=child;state['id']=eid;state['accepted']+=1;state['neutral']+=int(not phenotype)
     else:state['rejected']+=1
     state['seen']=list(dict.fromkeys(state['seen']+[after['phenotype_hash']]))
     with db:
      db.execute('INSERT INTO events VALUES(?,?,?)',(lid,state['n'],json.dumps(event,separators=(',',':'))))
      db.execute('INSERT OR REPLACE INTO lines VALUES(?,?)',(lid,json.dumps(state,separators=(',',':'))))
    results.append(dict(line=lid,attempts=state['n'],accepted=state['accepted'],neutral=state['neutral'],rejected=state['rejected'],unique_proposals=len(state['seen']),cpu_seconds=state['cpu'],fuel=state['fuel']))
 db.close();return results

def export(db_path,computational,target):
 db=sqlite3.connect(db_path);events=[json.loads(x[0]) for x in db.execute('SELECT payload FROM events ORDER BY line,n')]
 # Include actual siblings from a retained parent, never synthesize genealogy for presentation.
 families={}
 for e in events:
  if e['genotype_changed']:families.setdefault(e['parent_id'],[]).append(e)
 siblings=next((es[:2] for es in families.values() if len({e['phenotype_hash'] for e in es})>1),[])
 samples=[]
 for lid,raw in db.execute('SELECT id,state FROM lines ORDER BY id'):
  s=json.loads(raw)
  if lid.startswith('neutral/generative'):
   samples.append(dict(id=s['id'],morphology_genome=s['genome'],**develop(computational,s['genome'])))
 for e in siblings:
  samples.append(dict(id=e['id'],parent=e['parent_id'],accepted=e['accepted'],morphology_genome=e['morphology_genome'],**develop(computational,e['morphology_genome'])))
 data=dict(schema=1,status='isolated experiment; not production organisms',interpreter=VERSION,computational_genome=computational,computational_hash=digest(computational),samples=samples,siblings=[e['id'] for e in siblings],events=len(events))
 Path(target).write_text(json.dumps(data,separators=(',',':')));db.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--db',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 computational=json.loads(Path(a.input).read_text())
 results=run(a.db,computational);export(a.db,computational,a.output)
 Path(a.output+'.metrics.json').write_text(json.dumps(results,indent=2))
