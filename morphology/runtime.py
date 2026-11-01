"""Bounded, transactional experimental co-evolution recorder. Never used by production v4."""
import argparse,json,sqlite3,time
from pathlib import Path
from .ecology import initial,advance,PROTOCOL
from .development import digest

def source_hash():
 paths=sorted(Path(__file__).parent.glob('*.py'))+sorted(Path('samo').glob('*.py'))+sorted(Path('protocols').glob('*.json'))
 return digest([(str(p),p.read_bytes().hex()) for p in paths])
class Recorder:
 def __init__(self,path,seed=0):
  self.db=sqlite3.connect(path);self.db.execute('PRAGMA synchronous=FULL');self.db.execute('PRAGMA journal_mode=DELETE');self.db.execute('PRAGMA max_page_count=20000')
  self.db.execute('CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT,hash TEXT,source TEXT)')
  self.db.execute('CREATE TABLE IF NOT EXISTS events (n INTEGER PRIMARY KEY,payload TEXT,hash TEXT)')
  self.source=source_hash();r=self.db.execute('SELECT payload,hash,source FROM checkpoint').fetchone()
  if r:
   self.state=json.loads(r[0])
   if digest(self.state)!=r[1] or r[2]!=self.source:raise ValueError('checkpoint integrity/source mismatch')
  else:
   self.state=dict(ecology=initial(seed),retention=dict(pruned=0,root=digest([])))
   with self.db:self.save(self.state)
 def save(self,s):self.db.execute('INSERT OR REPLACE INTO checkpoint VALUES(1,?,?,?)',(json.dumps(s,separators=(',',':')),digest(s),self.source))
 def step(self):
  nxt,e=advance(self.state['ecology']);s=dict(ecology=nxt,retention=dict(self.state['retention']));n=nxt['core']['step']
  with self.db:
   self.db.execute('INSERT INTO events VALUES(?,?,?)',(n,json.dumps(e,separators=(',',':')),digest(e)))
   old=self.db.execute('SELECT n,hash FROM events ORDER BY n').fetchall()[:-1024]
   for num,h in old:s['retention']['root']=digest([s['retention']['root'],num,h]);s['retention']['pruned']+=1;self.db.execute('DELETE FROM events WHERE n=?',(num,))
   self.save(s)
  self.state=s;return e
 def close(self):self.db.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--steps',type=int,default=100);p.add_argument('--seed',type=int,default=0);a=p.parse_args();r=Recorder(a.db,a.seed)
 for _ in range(a.steps):r.step()
 print(json.dumps(dict(protocol=PROTOCOL,step=r.state['ecology']['core']['step'],traits=len(r.state['ecology']['traits']),retention=r.state['retention'])))
 r.close()
