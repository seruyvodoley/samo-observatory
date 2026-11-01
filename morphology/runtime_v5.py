"""Transactional bounded recorder, deterministic recovery and read-only public export."""
import argparse
import json
import os
import secrets
import socket
import sqlite3
import time
import zlib
from pathlib import Path
from morphology.ecology_v5 import initial, advance, PROTOCOL, PROTOCOL_HASH
from morphology.development import develop,validate as validate_morphology
from samo.genome_v4 import canonical, digest, validate
from samo.engine import now
import hashlib

def source_hash():
    base=Path(__file__).resolve().parents[1]
    paths=list((base/'samo').glob('*.py'))+[base/'morphology'/name for name in ('development.py','ecology_v5.py','runtime_v5.py')]+[base/'protocols'/'ecology-v5-morphology.json']
    return digest({str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if not p.name.startswith('.')})

RECENT=1024

def unpack(blob):
    inflater=zlib.decompressobj(); raw=inflater.decompress(blob,2_000_000)
    if not inflater.eof or inflater.unused_data: raise ValueError('compressed record size')
    return json.loads(raw)

class Recorder:
    def __init__(self,path,readonly=False):
        self.path=Path(path)
        if readonly:
            source=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
            self.db=sqlite3.connect(':memory:')
            try: source.backup(self.db,pages=64,sleep=0.01)
            finally: source.close()
            self.db.execute('BEGIN'); return
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o640); os.close(fd)
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=DELETE'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA max_page_count=16384')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY, payload BLOB, hash TEXT, source TEXT);
        CREATE TABLE IF NOT EXISTS events(n INTEGER PRIMARY KEY,payload BLOB,hash TEXT);
        CREATE TABLE IF NOT EXISTS retention(id INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS metadata(id INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS interventions(id INTEGER PRIMARY KEY,payload TEXT);''')

    def load(self):
        row=self.db.execute('SELECT payload,hash,source FROM checkpoint WHERE id=1').fetchone()
        if not row: return None
        s=unpack(row[0])
        if digest(s)!=row[1] or row[2]!=source_hash(): raise ValueError('checkpoint integrity/source mismatch')
        if s['protocol']!=PROTOCOL or s['protocol_hash']!=PROTOCOL_HASH or not 0<=len(s['core']['population'])<=8: raise ValueError('population schema/protocol hash')
        if set(s['traits'])!={x['id'] for x in s['core']['population']}:raise ValueError('trait identities')
        for item in s['core']['population']:
            validate(item['genome']);trait=s['traits'][item['id']];validate_morphology(trait['morphology_genome'])
            result=develop(item['genome'],trait['morphology_genome'])
            if result['morphology_hash']!=trait['morphology_hash'] or result['phenotype_hash']!=trait['phenotype_hash']:raise ValueError('trait integrity')
        return s

    def commit(self,s,event):
        if self.path.stat().st_size*2+4_000_000>64_000_000: raise RuntimeError('recorder quota')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO checkpoint VALUES(1,?,?,?)',
                            (zlib.compress(canonical(s)),digest(s),source_hash()))
            self.db.execute('INSERT INTO events VALUES(?,?,?)',(event['index'],zlib.compress(canonical(event)),digest(event)))
            fs=os.statvfs(self.path.parent)
            fill=1-fs.f_bavail/max(1,fs.f_blocks)
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES(1,?)',(json.dumps(dict(observed_at=now(),status='storage_warning' if fill>=.8 else 'running',storage_fraction=fill,environment=os.environ.get('SAMO_ENV','local'))),))
            # Explicit aggregate retention: raw rows are finite; the seed and immutable source
            # allow deterministic regeneration. Hash root commits to every discarded record.
            if s['core']['step']>RECENT:
                rows=self.db.execute('SELECT n,hash FROM events WHERE n<? ORDER BY n',(s['core']['step']-RECENT,)).fetchall()
                prior=self.db.execute('SELECT payload FROM retention WHERE id=1').fetchone()
                summary=json.loads(prior[0]) if prior else dict(pruned_records=0,root=digest([]),through=-1)
                for n,h in rows:
                    summary.update(root=digest([summary['root'],n,h]),through=n,pruned_records=summary['pruned_records']+1)
                self.db.execute('INSERT OR REPLACE INTO retention VALUES(1,?)',(json.dumps(summary),))
                self.db.execute('DELETE FROM events WHERE n<?',(s['core']['step']-RECENT,))

    def initialize(self,seed):
        if self.load() is not None: return
        s=initial(seed)
        with self.db:
            self.db.execute('INSERT INTO checkpoint VALUES(1,?,?,?)',(zlib.compress(canonical(s)),digest(s),source_hash()))

    def close(self): self.db.close()

def public_form(form,trait):
    morphology=develop(form['genome'],trait['morphology_genome'])
    if morphology['morphology_hash']!=trait['morphology_hash'] or morphology['phenotype_hash']!=trait['phenotype_hash']:raise ValueError('exported phenotype integrity')
    return dict(id=form['id'],parents=form['parents'],source=form.get('source'),born=form['born'],hash=digest(form['genome']),genome=form['genome'],morphology=dict(**trait,phenotype=morphology['phenotype'],phenotype_payload=canonical(morphology['phenotype']).decode(),phenotype_payload_hash=hashlib.sha256(canonical(morphology['phenotype'])).hexdigest(),development_fuel=morphology['fuel'],truncated=morphology['truncated']),identity_hash=digest([digest(form['genome']),trait['morphology_hash'],trait['interpreter']]))

def public_snapshot(recorder):
    outer_state=recorder.load()
    state=outer_state['core'] if outer_state else None
    if not state: raise ValueError('empty ecosystem')
    recent=[]
    for n,blob,h in recorder.db.execute('SELECT n,payload,hash FROM events ORDER BY n'):
        outer=unpack(blob)
        if digest(outer)!=h or n!=outer['index']:raise ValueError('event integrity')
        e=outer['computational']
        # Validate the actual prequential commitments before projecting public results.
        results=[x['result'] for x in e['evaluations']]+([e['result']] if 'result' in e else [])
        for result in results:
            rows=result['rows']
            for r in rows:
                if r['commitment']!=digest(dict(task_id=r['task_id'],index=r['index'],prediction=r['prediction'],prefix_hash=digest(r['prefix']))): raise ValueError('trial commitment')
                if r['correct']!=(r['prediction'] is not None and r['prediction']==r['target']): raise ValueError('trial score')
            if len(rows)!=result['total'] or abs(result['accuracy']-sum(r['correct'] for r in rows)/max(1,len(rows)))>1e-12: raise ValueError('aggregate score')
        recent.append({k:e[k] for k in ('index','episode','kind','family','task_index','status','accepted','changes','parent_ids','fuel_total','delta','birth','genotype_changed','behavior_changed','duplicate','external','search_error','meta_fuel','meta_scores') if k in e} |
                      dict(lifecycle=[{k:v for k,v in item.items() if k!='organism'} | (dict(id=item['organism']['id'],source=item['organism']['source']) if 'organism' in item else {}) for item in e['lifecycle']],
                           accuracy=e.get('result',{}).get('accuracy'), candidate_id=e.get('candidate',{}).get('id')))
    row=recorder.db.execute('SELECT payload FROM retention WHERE id=1').fetchone()
    retention=json.loads(row[0]) if row else dict(pruned_records=0,root=digest([]),through=-1)
    meta=recorder.db.execute('SELECT payload FROM metadata WHERE id=1').fetchone()
    return dict(schema=1,protocol=PROTOCOL,protocol_hash=PROTOCOL_HASH,generated_at=now(),observation=json.loads(meta[0]) if meta else {},
                step=state['step'],episode=state['episode'],attempts=state['attempts'],births=state['births'],deaths=state['deaths'],
                recolonizations=state['recolonizations'],fuel=state['fuel']+outer_state['morphology_fuel'],computational_fuel=state['fuel'],morphology_fuel=outer_state['morphology_fuel'],
                episodes=state['episodes'],episode_retention=state['episode_retention'],
                interventions=[json.loads(x[0]) for x in recorder.db.execute('SELECT payload FROM interventions ORDER BY id')],
                population=[public_form(x,outer_state['traits'][x['id']]) for x in state['population']],
                events=recent,retention=retention,claims=[],telemetry=dict(morphology_changes=outer_state['morphology_changes'],morphology_effects=outer_state['morphology_effects'],morphology_neutral=outer_state['morphology_neutral'],unique_genomes=len({digest(x['genome']) for x in state['population']}),genotype_changes=state['genotype_changes'],behavior_changes=state['behavior_changes'],search_errors=state['search_errors'],stagnant_attempts=state['stagnant_attempts'],last_change=state['last_change'],training_metric='exact-match; current selection tasks',independent_accuracy=None,capabilities_status='not independently assessed',new_capabilities=None,lost_capabilities=None,search_workability=(sum(not bool(e.get('search_error')) for e in recent if not e.get('external',True))/max(1,sum(not e.get('external',True) for e in recent))),search_workability_scope='retained endogenous attempts only'),
                limitations=['Training feedback only; no confirmed useful discoveries.',
                             'Raw trials retained for latest 1024 attempts; older records are explicitly thinned with a hash commitment. Private seed and archived source allow regeneration.',
                             'Infrastructure uptime, attempts and predictive capability are different measurements.'])

def atomic_json(path,data):
    raw=canonical(data)
    if len(raw)>4_000_000: raise ValueError('public snapshot cap')
    path=Path(path); tmp=path.with_suffix('.tmp')
    with open(tmp,'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o644); os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def notify(message):
    target=os.environ.get('NOTIFY_SOCKET')
    if target:
        if target.startswith('@'): target='\0'+target[1:]
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock: sock.connect(target); sock.sendall(message.encode())

def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['run','export','audit']); p.add_argument('--db',required=True)
    p.add_argument('--output'); p.add_argument('--steps',type=int,default=0); p.add_argument('--pause',type=float,default=1)
    a=p.parse_args(); r=Recorder(a.db,readonly=a.mode!='run')
    try:
        if a.mode=='run':
            r.initialize(secrets.randbits(128)); notify('READY=1')
            for_tick=0
            while not a.steps or for_tick<a.steps:
                stat=os.statvfs(Path(a.db).parent); fill=1-stat.f_bavail/max(1,stat.f_blocks)
                if fill>=.9:
                    notify('WATCHDOG=1\nSTATUS=storage critical; paused without deleting history'); time.sleep(5); continue
                s=r.load(); s,e=advance(s); r.commit(s,e); for_tick+=1
                notify(f'WATCHDOG=1\nSTATUS=episode {s["core"]["episode"]}, attempt {s["core"]["step"]}, storage {fill:.1%}')
                time.sleep(max(0,a.pause))
        elif a.mode=='export':
            if not a.output: raise ValueError('output required')
            atomic_json(a.output,public_snapshot(r))
        else: print(json.dumps(dict(checkpoint='valid',attempts=r.load()['core']['step'],public_records=len(public_snapshot(r)['events']))))
    finally: r.close()

if __name__=='__main__': main()
