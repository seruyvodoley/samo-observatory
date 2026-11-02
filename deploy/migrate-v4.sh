set -eu
if test -e /srv/samo/state/ecology-v4.sqlite; then echo "v4 already initialized; refusing repeated initial migration" >&2; exit 1; fi
systemctl stop samo-recorder-export.timer samo-publish.timer
systemctl stop samo-organism.service samo-recorder-export.service samo-publish.service
cd /srv/samo/code
PYTHONDONTWRITEBYTECODE=1 python3 -m samo.ecology_runtime audit --db /srv/samo/state/ecology.sqlite
python3 - <<'PY'
import sqlite3,shutil
from pathlib import Path
src=sqlite3.connect('file:/srv/samo/state/ecology.sqlite?mode=ro',uri=True);dst=sqlite3.connect('/srv/samo/releases/v2-final.sqlite');src.backup(dst);dst.close();src.close()
shutil.copy2('/srv/samo/observer/state/history.json','/srv/samo/releases/v2-final-observer.json')
PY
PYTHONDONTWRITEBYTECODE=1 python3 -m samo.ecology_runtime export --db /srv/samo/state/ecology.sqlite --output /srv/samo/site/data/v2-final.json
mkdir -p /etc/systemd/system/samo-organism.service.d /etc/systemd/system/samo-recorder-export.service.d /etc/systemd/system/samo-publish.service.d
cat > /etc/systemd/system/samo-organism.service.d/z-v4.conf <<'UNIT'
[Service]
WorkingDirectory=/srv/samo/releases/core-v4/code
ExecStart=
ExecStart=/usr/bin/python3 -m samo.runtime_v4 run --db /srv/samo/state/ecology-v4.sqlite --pause 1
UNIT
cat > /etc/systemd/system/samo-recorder-export.service.d/z-v4.conf <<'UNIT'
[Service]
WorkingDirectory=/srv/samo/releases/core-v4/code
Environment=PYTHONPATH=/srv/samo/releases/core-v4/code
ExecStart=
ExecStart=/usr/bin/python3 /srv/samo/releases/core-v4/code/tools/enrich_snapshot_v4.py /srv/samo/state/ecology-v4.sqlite /srv/samo/site/data/ecosystem.json /srv/samo/observer/state/history-v4.json
UNIT
cat > /etc/systemd/system/samo-publish.service.d/z-v4.conf <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /srv/samo/publisher/publish_snapshot_v4.py
UNIT
cd /srv/samo/releases/core-v4/code
runuser -u samo-organism -- env PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import json,secrets,sqlite3,zlib
from samo.runtime_v4 import Recorder
from samo.engine import now
old=sqlite3.connect('file:/srv/samo/releases/v2-final.sqlite?mode=ro',uri=True);step=json.loads(zlib.decompress(old.execute('select payload from checkpoint').fetchone()[0]))['step'];old.close()
r=Recorder('/srv/samo/state/ecology-v4.sqlite');r.initialize(secrets.randbits(128))
with r.db:r.db.execute('insert into interventions(payload) values(?)',(json.dumps(dict(kind='protocol_transition',at_attempt=0,at=now(),reason='Owner-authorized engineering correction; experimental v4, no proven meta superiority',from_protocol='samo-ecology-v2',from_step=step,archive='/data/archive/v2-final.json')),))
r.close()
PY
systemctl daemon-reload
systemctl start samo-organism.service
systemctl start samo-recorder-export.timer samo-publish.timer
systemctl show samo-organism.service -p ActiveState -p MainPID -p MemoryMax -p MemorySwapMax -p CPUQuotaPerSecUSec
