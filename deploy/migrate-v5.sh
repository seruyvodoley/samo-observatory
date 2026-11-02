set -eu
if test -e /srv/samo/state/ecology-v5.sqlite; then echo 'Refusing to overwrite existing v5 scientific state' >&2; exit 1; fi
complete=0
trap 'if test "$complete" -eq 0; then sh /srv/samo/releases/core-v5/rollback-v5.sh; fi' EXIT
systemctl stop samo-recorder-export.timer samo-publish.timer
systemctl stop samo-organism.service samo-recorder-export.service samo-publish.service
systemd-run --unit=samo-v5-transition-files --slice=samo-aux.slice --wait --pipe -p CPUQuota=10% -p MemoryMax=128000000 -p MemorySwapMax=0 -p PrivateNetwork=yes -p ProtectSystem=strict -p ReadWritePaths=/srv/samo/releases -p ReadWritePaths=/srv/samo/state -p ReadWritePaths=/srv/samo/site/data -p Environment=PYTHONDONTWRITEBYTECODE=1 -p Environment=PYTHONPATH=/srv/samo/releases/core-v5/code -p WorkingDirectory=/srv/samo/releases/core-v5/code /usr/bin/python3 -B /srv/samo/releases/core-v5/transition-v5-files.py
cat > /etc/systemd/system/samo-organism.service.d/zz-v5.conf <<'UNIT'
[Service]
WorkingDirectory=/srv/samo/releases/core-v5/code
ExecStart=
ExecStart=/usr/bin/python3 -m morphology.runtime_v5 run --db /srv/samo/state/ecology-v5.sqlite --pause 1
UNIT
cat > /etc/systemd/system/samo-recorder-export.service.d/zz-v5.conf <<'UNIT'
[Service]
WorkingDirectory=/srv/samo/releases/core-v5/code
Environment=PYTHONPATH=/srv/samo/releases/core-v5/code
TimeoutStartSec=180
ExecStart=
ExecStart=/usr/bin/python3 /srv/samo/releases/core-v5/code/tools/enrich_snapshot_v5.py /srv/samo/state/ecology-v5.sqlite /srv/samo/site/data/ecosystem.json /srv/samo/observer/state/history-v5.json
UNIT
cat > /etc/systemd/system/samo-publish.service.d/zz-v5.conf <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /srv/samo/publisher/publish_snapshot_v5.py
UNIT
systemctl daemon-reload
systemctl start samo-organism.service
python3 - <<'PY'
import sqlite3,json,zlib,time
for _ in range(100):
 c=sqlite3.connect('file:/srv/samo/state/ecology-v5.sqlite?mode=ro',uri=True);row=c.execute('select payload from checkpoint').fetchone();c.close()
 if row and json.loads(zlib.decompress(row[0]))['core']['step']>0:break
 time.sleep(.2)
else:raise RuntimeError('new episode did not advance')
PY
systemctl start samo-recorder-export.service
systemctl start samo-publish.service
systemctl start samo-recorder-export.timer samo-publish.timer
complete=1
systemctl show samo-organism.service -p ActiveState -p MainPID -p MemoryMax -p MemorySwapMax -p CPUQuotaPerSecUSec
