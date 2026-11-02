"""Durable, bounded v6 recorder with deterministic checkpoint validation/export."""
from __future__ import annotations
import argparse, hashlib, json, os, secrets, socket, sqlite3, time, zlib
from functools import lru_cache
from pathlib import Path
from samo.genome_v4 import canonical, digest, validate
from samo.engine import now
from .ecology_v6 import (ARMS, PROTOCOL, PROTOCOL_HASH, advance, initial,
                         public_metrics)
from .development_v2 import VERSION, develop_v2, validate as validate_morphology

RECENT = 1024
DB_LIMIT = 64_000_000

@lru_cache(maxsize=1)
def source_hash():
    base = Path(__file__).resolve().parents[1]
    files = [p for p in (base/'samo').glob('*.py') if not p.name.startswith('._')] + [base/'morphology'/x for x in ('development.py','development_v2.py','ecology_v6.py','runtime_v6.py')] + [base/'protocols/ecology-v6-morphology.json']
    return digest({str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)})

def unpack(blob):
    d=zlib.decompressobj(); raw=d.decompress(blob, 2_000_000)
    if not d.eof or d.unused_data: raise ValueError('compressed event limit')
    return json.loads(raw)

class Recorder:
    def __init__(self, path, readonly=False):
        self.path=Path(path)
        if readonly:
            src=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True); self.db=sqlite3.connect(':memory:')
            try: src.backup(self.db,pages=64,sleep=.01)
            finally: src.close()
            self.db.execute('BEGIN'); return
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o640); os.close(fd)
        self.db=sqlite3.connect(path); self.db.execute('PRAGMA journal_mode=DELETE'); self.db.execute('PRAGMA synchronous=FULL'); self.db.execute('PRAGMA max_page_count=16384')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY,payload BLOB,hash TEXT,source TEXT);
        CREATE TABLE IF NOT EXISTS events(n INTEGER PRIMARY KEY,payload BLOB,hash TEXT);
        CREATE TABLE IF NOT EXISTS retention(id INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS metadata(id INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS protocol(id INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS interventions(id INTEGER PRIMARY KEY,payload TEXT);''')

    def load(self):
        row=self.db.execute('SELECT payload,hash,source FROM checkpoint WHERE id=1').fetchone()
        if not row:return None
        state=unpack(row[0])
        if digest(state)!=row[1] or row[2]!=source_hash(): raise ValueError('checkpoint hash/source mismatch')
        if state['protocol']!=PROTOCOL or state['protocol_hash']!=PROTOCOL_HASH or state['arm'] not in ARMS: raise ValueError('protocol mismatch')
        if set(state['traits'])!={x['id'] for x in state['core']['population']}: raise ValueError('active trait identity mismatch')
        for item in state['core']['population']:
            validate(item['genome']); trait=state['traits'][item['id']]; validate_morphology(trait['morphology_genome'])
            result=develop_v2(item['genome'],trait['morphology_genome'])
            if result['morphology_hash']!=trait['morphology_hash'] or result['phenotype_hash']!=trait['phenotype_hash']: raise ValueError('phenotype integrity mismatch')
        return state

    def initialize(self, seed, size=4, mode='meta', arm='neutral'):
        if self.load() is not None:return
        if self.db.execute('select count(*) from events').fetchone()[0]: raise ValueError('events exist without checkpoint')
        state=initial(seed,size,mode,arm)
        with self.db:
            self.db.execute('insert into checkpoint values(1,?,?,?)',(zlib.compress(canonical(state)),digest(state),source_hash()))
            self.db.execute('insert into protocol values(1,?)',(json.dumps({'protocol':PROTOCOL,'hash':PROTOCOL_HASH,'arm':arm,'registered':now()}),))

    def commit(self,state,event):
        if self.path.stat().st_size*2+4_000_000>DB_LIMIT: raise RuntimeError('database safety ceiling')
        raw=canonical(event)
        if len(raw)>2_000_000: raise ValueError('event size ceiling')
        with self.db:
            self.db.execute('insert or replace into checkpoint values(1,?,?,?)',(zlib.compress(canonical(state)),digest(state),source_hash()))
            self.db.execute('insert into events values(?,?,?)',(event['index'],zlib.compress(raw),digest(event)))
            fs=os.statvfs(self.path.parent); used=1-fs.f_bavail/max(1,fs.f_blocks)
            self.db.execute('insert or replace into metadata values(1,?)',(json.dumps({'observed_at':now(),'environment':os.environ.get('SAMO_ENV','local'),'storage_fraction':used,'status':'storage_warning' if used>=.8 else 'running'}),))
            if state['core']['step']>RECENT:
                rows=self.db.execute('select n,hash from events where n<? order by n',(state['core']['step']-RECENT,)).fetchall()
                prior=self.db.execute('select payload from retention where id=1').fetchone()
                acc=json.loads(prior[0]) if prior else {'pruned_records':0,'root':digest([]),'through':-1}
                for n,h in rows:
                    acc={'root':digest([acc['root'],n,h]),'through':n,'pruned_records':acc['pruned_records']+1}
                self.db.execute('insert or replace into retention values(1,?)',(json.dumps(acc),))
                self.db.execute('delete from events where n<?',(state['core']['step']-RECENT,))

    def close(self): self.db.close()

def _public_event(event):
    comp=event['computational']
    rows=[]
    for item in comp.get('evaluations',[]):
        res=item['result']
        for r in res['rows']:
            if r['commitment']!=digest({'task_id':r['task_id'],'index':r['index'],'prediction':r['prediction'],'prefix_hash':digest(r['prefix'])}): raise ValueError('trial commitment')
            if r['correct']!=(r['prediction'] is not None and r['prediction']==r['target']): raise ValueError('trial score')
    result=comp.get('result',{})
    result_summary={k:result[k] for k in ('status','accuracy','bit_accuracy','mae','total','fuel') if k in result}
    return {'index':event['index'],'episode':event['episode'],'arm':event['arm'],
            'kind':comp.get('kind','attempt'),'family':comp.get('family','unknown'),
            'family_accuracy':comp.get('family_accuracy'), 'accepted':comp.get('accepted',False),
            'accuracy':comp.get('result',{}).get('accuracy'), 'changes':comp.get('changes',[]),
            'lifecycle':[{k:v for k,v in x.items() if k!='organism'} | ({'id':x['organism']['id'],'source':x['organism'].get('source')} if 'organism' in x else {}) for x in comp.get('lifecycle',[])],
            'computational':{k:comp[k] for k in ('kind','status','accepted','changes','parent_ids','fuel_total','delta','birth','genotype_changed','behavior_changed','duplicate','external','search_error','meta_fuel','meta_scores','family') if k in comp} | {'result_summary':result_summary},
            'morphology_births':[{k:v for k,v in row.items() if k not in ('genotype','phenotype')} for row in event['morphology_births']],
            'active_unique_forms':event['population_unique_phenotypes'],'active_niches':event['population_occupied_niches'],
            'archive_size':event['archive_size'],'morphology_fuel_total':event['morphology_fuel_total'],'cpu_ns':event['cpu_ns']}

def snapshot(recorder):
    s=recorder.load()
    if s is None: raise ValueError('no checkpoint')
    events=[]
    for n,blob,h in recorder.db.execute('select n,payload,hash from events order by n'):
        ev=unpack(blob)
        if ev['index']!=n or digest(ev)!=h: raise ValueError('event integrity')
        events.append(_public_event(ev))
    retention=recorder.db.execute('select payload from retention where id=1').fetchone()
    metadata=recorder.db.execute('select payload from metadata where id=1').fetchone()
    interventions=[json.loads(x[0]) for x in recorder.db.execute('select payload from interventions order by id')]
    def form(org, morph):
        payload=canonical(morph['phenotype']).decode()
        h=digest(org['genome'])
        return {'id':org['id'],'parents':org['parents'],'source':org['source'],'born':org['born'],
                'hash':h,'genome':org['genome'],'accepted':True,
                'identity_hash':digest([h,morph['morphology_hash'],morph['interpreter']]),
                'origin':morph.get('origin'),
                'morphology':{'morphology_genome':morph['morphology_genome'],'morphology_hash':morph['morphology_hash'],
                              'phenotype_hash':morph['phenotype_hash'],
                              'phenotype_payload':payload,'phenotype_payload_hash':digest(morph['phenotype']),
                              'descriptor':morph['descriptor'],'niche':morph['niche'],'interpreter':morph['interpreter'],
                              'origin':morph.get('origin'),
                              'development_fuel':morph['development_fuel'],'truncated':morph['truncated']}}
    pop=[form(org,s['traits'][org['id']]) for org in s['core']['population']]
    historical=[]
    for _n,blob,_h in recorder.db.execute('select n,payload,hash from events order by n'):
        saved=unpack(blob); comp=saved['computational']; morphs={x['id']:x for x in saved['morphology_births']}
        organisms=[x['organism'] for x in comp.get('lifecycle',[]) if x.get('kind')=='founder']
        candidate=comp.get('candidate')
        if candidate is not None and comp.get('accepted'):organisms.append(candidate)
        for org in organisms:
            if org['id'] in morphs:
                row=morphs[org['id']]
                tr={'morphology_genome':row['genotype'],'morphology_hash':row['morphology_hash'],
                    'phenotype_hash':row['phenotype_hash'],'phenotype':row['phenotype'],
                    'descriptor':row['descriptor'],'niche':row['niche'],'interpreter':row['interpreter'],
                    'development_fuel':row['development_fuel'],'truncated':row['truncated'],'origin':row['origin']}
                historical.append(form(org,tr))
        candidate=comp.get('candidate')
        if candidate is not None and comp.get('accepted') and candidate['id'] in morphs:
            row=morphs[candidate['id']]
            tr={'morphology_genome':row['genotype'],'morphology_hash':row['morphology_hash'],
                'phenotype_hash':row['phenotype_hash'],'phenotype':row['phenotype'],
                'descriptor':row['descriptor'],'niche':row['niche'],'interpreter':row['interpreter'],
                'development_fuel':row['development_fuel'],'truncated':row['truncated'],'origin':row['origin']}
            historical.append(form(candidate,tr))
    historical=historical[-32:]
    accuracy=[row['accuracy'] for row in events if isinstance(row.get('accuracy'),(int,float))]
    telemetry=public_metrics(s)
    telemetry.update({'unique_genomes':len({digest(x['genome']) for x in s['core']['population']}),
        'genotype_changes':s['core']['genotype_changes'],'behavior_changes':s['core']['behavior_changes'],
        'search_errors':s['core']['search_errors'],'stagnant_attempts':s['core']['stagnant_attempts'],
        'morphology_effects':s['morphology_effects'],
        'morphology_neutral':s['morphology_neutral'],'independent_accuracy':None,
        'capabilities_status':'not independently assessed'})
    data={'schema':1,'protocol':PROTOCOL,'protocol_hash':PROTOCOL_HASH,'arm':s['arm'],'generated_at':now(),
            'observation':json.loads(metadata[0]) if metadata else {},'step':s['core']['step'],'episode':s['core']['episode'],
            'attempts':s['core']['attempts'],'births':s['core']['births'],'deaths':s['core']['deaths'],
            'recolonizations':s['core']['recolonizations'],'fuel':s['core']['fuel']+s['morphology_fuel'],
            'computational_fuel':s['core']['fuel'],'morphology_fuel':s['morphology_fuel'],
            'episode_retention':s['core']['episode_retention'],
            'episodes':s['core']['episodes'],
            'population':pop,'history':historical,'events':events,
            'retention':json.loads(retention[0]) if retention else {'pruned_records':0,'root':digest([]),'through':-1},
            'telemetry':telemetry,'infrastructure':{'checked_at':now(),'organism':'not independently checked','detail':'This static snapshot does not include the systemd restart counter.','technical_restarts':None},
            'interventions':interventions,'morphology':public_metrics(s),'computational':{'protocol':'samo-ecology-v4','training_accuracy_latest':accuracy[-1] if accuracy else None,
            'independent_accuracy':None,'capability_status':'not_independently_assessed'},
            'long_term':None,'claims':['Morphology diversity is not evidence of improved prediction.','Archived morphology descriptors never supply living genotypes.']}
    data['snapshot_id']=digest(data); data['published_at']=data['generated_at']
    return data

def export_file(path,data):
    raw=canonical(data)
    if len(raw)>4_000_000:raise ValueError('snapshot public size limit')
    target=Path(path);tmp=target.with_suffix('.tmp')
    with open(tmp,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.chmod(tmp,0o644);os.replace(tmp,target)

def notify(s):
    target=os.environ.get('NOTIFY_SOCKET')
    if target:
        if target.startswith('@'):target='\0'+target[1:]
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as c:c.connect(target);c.sendall(s.encode())

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('run','export','audit'));p.add_argument('--db',required=True);p.add_argument('--output');p.add_argument('--seed',type=int,default=0);p.add_argument('--arm',choices=ARMS,default='neutral');p.add_argument('--steps',type=int,default=0);p.add_argument('--pause',type=float,default=1)
    a=p.parse_args();r=Recorder(a.db,readonly=a.mode!='run')
    try:
        if a.mode=='run':
            r.initialize(a.seed,arm=a.arm);notify('READY=1');ticks=0
            while not a.steps or ticks<a.steps:
                fs=os.statvfs(Path(a.db).parent)
                used=1-fs.f_bavail/max(1,fs.f_blocks)
                if used>=.90:
                    notify('WATCHDOG=1\nSTATUS=storage critical; evolution paused without pruning')
                    time.sleep(5)
                    continue
                s=r.load();s,e=advance(s);r.commit(s,e);ticks+=1
                notify(f'WATCHDOG=1\nSTATUS=episode {s["core"]["episode"]}, step {s["core"]["step"]}, disk {used:.1%}')
                if a.pause:time.sleep(max(0,a.pause))
        elif a.mode=='export':
            if not a.output:raise ValueError('--output required')
            export_file(a.output,snapshot(r))
        else:
            s=r.load(); print(json.dumps({'checkpoint':'valid','step':s['core']['step'],'protocol':PROTOCOL,'events':len(snapshot(r)['events'])}))
    finally:r.close()
if __name__=='__main__':main()
