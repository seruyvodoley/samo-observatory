"""Owner-authorized administrative transition. Runs under the existing SAMO resource slice."""
import json,os,pwd,grp,secrets,sqlite3,tarfile,zlib,shutil
from pathlib import Path
from samo.runtime_v4 import Recorder as OldRecorder,source_hash as old_source_hash
from morphology.runtime_v5 import Recorder,source_hash
from samo.engine import now
os.umask(0o027)
root=Path('/srv/samo');db=root/'state/ecology-v5.sqlite'
if db.exists():raise RuntimeError('v5 checkpoint already exists; no overwrite')
old=OldRecorder(root/'state/ecology-v4.sqlite',readonly=True);state=old.load();old.close()
source=sqlite3.connect('file:/srv/samo/state/ecology-v4.sqlite?mode=ro',uri=True);target=sqlite3.connect('/srv/samo/releases/v4-final-before-v5.sqlite');source.backup(target);target.close();source.close();os.chmod('/srv/samo/releases/v4-final-before-v5.sqlite',0o600)
with tarfile.open('/srv/samo/releases/v4-final-before-v5-source.tgz','w:gz') as tar:
 for name in ('samo','protocols','tools'):tar.add(root/'releases/core-v4/code'/name,arcname=name)
os.chmod('/srv/samo/releases/v4-final-before-v5-source.tgz',0o600)
a=json.loads((root/'site/data/ecosystem.json').read_text())
if a['protocol']!='samo-ecology-v4':raise ValueError('unexpected previous public protocol')
a['retirement']=dict(at=now(),final_checkpoint_step=state['step'],public_observation_step=a['step'],final_database_archive='private v4-final-before-v5.sqlite; preserved unchanged')
archive=root/'site/data/archive';archive.mkdir(exist_ok=True);os.chmod(archive,0o755);(archive/'v4-final.json').write_text(json.dumps(a,separators=(',',':')));os.chmod(archive/'v4-final.json',0o644)
r=Recorder(db);r.initialize(secrets.randbits(128));intervention=dict(kind='protocol_transition',at=now(),at_attempt=0,from_protocol=state['protocol'],from_step=state['step'],archive='/data/archive/v4-final.json',previous_source=old_source_hash(),new_source=source_hash(),reason='Owner authorized v5 neutral inherited morphogenesis after paired research, Linux isolation/recovery and source-to-render acceptance. New episode, not inherited continuation of retired v4 organisms. Prediction fitness unchanged; no aesthetic or accuracy superiority claimed.')
with r.db:r.db.execute('insert into interventions(payload) values(?)',(json.dumps(intervention),))
r.close();os.chown(db,pwd.getpwnam('samo-organism').pw_uid,grp.getgrnam('samo-data').gr_gid)
(root/'releases/core-v5/transition.json').write_text(json.dumps(intervention,indent=2));print(json.dumps(dict(from_step=state['step'],new_protocol='samo-ecology-v5-morphology',new_episode=0)))
