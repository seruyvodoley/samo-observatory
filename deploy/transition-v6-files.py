"""Additive, owner-authorized v5 archive and v6 episode initialization."""
import json, os, pwd, grp, shutil, sqlite3, time
from pathlib import Path
from morphology.runtime_v6 import Recorder, PROTOCOL, source_hash
from samo.genome_v4 import digest

ROOT=Path('/srv/samo')
OLD_DB=ROOT/'state/ecology-v5.sqlite'
OLD_BACKUP=ROOT/'releases/core-v5/v5-final-before-v6.sqlite'
NEW_DB=ROOT/'state/ecology-v6.sqlite'
PUBLIC=ROOT/'site/data/ecosystem.json'
PUBLIC_ARCHIVE=ROOT/'site/data/archive/v5-final-before-v6.json'
SEED=2026110202

if not OLD_DB.is_file() or not PUBLIC.is_file(): raise RuntimeError('v5 production files missing')
if shutil.disk_usage(ROOT).free < 100_000_000: raise RuntimeError('insufficient project volume headroom')

source=sqlite3.connect(OLD_DB.resolve().as_uri()+'?mode=ro',uri=True)
try:
    if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('v5 database integrity failure')
    backup_path=OLD_BACKUP
    if backup_path.exists():
        stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
        backup_path=OLD_BACKUP.with_name(f'v5-before-v6-retry-{stamp}.sqlite')
        if backup_path.exists(): raise RuntimeError('backup target already exists')
    target=sqlite3.connect(backup_path)
    try: source.backup(target,pages=64,sleep=.01)
    finally: target.close()
finally: source.close()
os.chmod(backup_path,0o600)
check=sqlite3.connect(backup_path)
if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('v5 backup integrity failure')
check.close()

old_raw=PUBLIC.read_bytes(); old=json.loads(old_raw)
if old.get('protocol') != 'samo-ecology-v5-morphology': raise RuntimeError('public v5 snapshot changed unexpectedly')
PUBLIC_ARCHIVE.parent.mkdir(exist_ok=True)
archive_path=PUBLIC_ARCHIVE
if archive_path.exists():
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    archive_path=PUBLIC_ARCHIVE.with_name(f'v5-before-v6-retry-{stamp}.json')
    if archive_path.exists(): raise RuntimeError('snapshot archive target already exists')
archive_path.write_bytes(old_raw)
os.chmod(archive_path,0o644)

resume_existing=NEW_DB.exists()
rec=Recorder(NEW_DB)
try:
    if resume_existing:
        state=rec.load()
        if state is None or state['protocol']!=PROTOCOL: raise RuntimeError('existing v6 state cannot be resumed safely')
        if not rec.db.execute('select 1 from interventions where id=1').fetchone(): raise RuntimeError('existing v6 checkpoint has no transition record')
        intervention=json.loads(rec.db.execute('select payload from interventions where id=1').fetchone()[0])
    else:
        rec.initialize(SEED,arm='neutral')
        intervention={'kind':'protocol_transition','at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                      'from_protocol':'samo-ecology-v5-morphology','from_step':old.get('step'),
                      'from_snapshot_id':old.get('snapshot_id'),'to_protocol':PROTOCOL,
                      'to_episode':0,'reason':'Registered v6 morphology interpreter integrated at genuine computational births after isolated Linux acceptance; new episode with fresh computational and morphology founders. No prior genome was restored; prediction fitness and v4 search are unchanged.',
                      'v6_source_hash':source_hash(),'morphology_policy':'neutral','archive_genotype_donors':False,
                      'previous_snapshot':('/data/archive/'+archive_path.name),
                      'previous_public_snapshot_sha256':__import__('hashlib').sha256(old_raw).hexdigest()}
        with rec.db:
            rec.db.execute('INSERT INTO interventions(payload) VALUES(?)',(json.dumps(intervention,sort_keys=True),))
finally: rec.close()
os.chown(NEW_DB,pwd.getpwnam('samo-organism').pw_uid,grp.getgrnam('samo-data').gr_gid)
print(json.dumps({'v5_step_archived':old.get('step'),'old_db_backup':str(backup_path),'old_db_backup_bytes':backup_path.stat().st_size,
                  'new_protocol':PROTOCOL,'new_episode':0,'intervention_hash':digest(intervention)},sort_keys=True))
