import errno,json,os,sqlite3
from pathlib import Path
from samo.runtime_v4 import Recorder,public_snapshot,atomic_json
from samo.ecology_v4 import advance
from samo.genome_v4 import digest
base=Path('/srv/samo-v4-acceptance/state');db=base/'ecology.sqlite';r=Recorder(db);before=r.load();expected,event=advance(before);r.close()
# Simulated crash before transaction: process-local work discarded, durable state stays unchanged.
r=Recorder(db);again,replayed=advance(r.load());assert replayed==event;r.commit(again,replayed);r.close()
# Exhaust only the isolated acceptance loop filesystem.
filler=base/'quota-probe.bin'
try:
 with filler.open('wb') as f:
  while True:f.write(b'0'*65536)
except OSError as exc:assert exc.errno==errno.ENOSPC
r=Recorder(db);stable=r.load();a,e=advance(stable)
try:r.commit(a,e);raise AssertionError('full filesystem accepted commit')
except (OSError,sqlite3.Error,RuntimeError):pass
finally:r.close();filler.unlink()
r=Recorder(db);assert digest(r.load())==digest(stable);a,e=advance(r.load());r.commit(a,e);atomic_json(base/'export.json',public_snapshot(r));r.close()
print(json.dumps(dict(crash_replay=True,enospc_rollback=True,resumed_step=a['step'],sqlite=sqlite3.connect(db).execute('pragma integrity_check').fetchone()[0])))
