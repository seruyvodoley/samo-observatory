#!/usr/bin/env bash
set -euo pipefail

root=/srv/samo
release="$root/releases/core-v6"
acceptance="$release/acceptance.json"
db="$root/state/ecology-v6.sqlite"
complete=0

test -s "$acceptance"
python3 - "$acceptance" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x.get('technical_acceptance') is True
assert x.get('isolated_linux_vm') is True
assert x.get('compute_path_parity') is True
assert x.get('checkpoint_recovery') is True
assert x.get('public_snapshot_validation') is True
PY

test -f "$root/state/ecology-v5.sqlite"
test ! -e "$db"
test -d "$release/code"
test "$(df -B1 --output=avail "$root" | tail -1)" -gt 100000000
systemctl is-active --quiet samo-organism.service
systemctl is-active --quiet samo-web.service

rollback() {
  if test "$complete" -ne 1; then
    systemctl disable --now samo-recorder-export-v6.timer samo-organism-v6.service 2>/dev/null || true
    systemctl enable --now samo-organism.service
    systemctl enable --now samo-recorder-export.timer
    systemctl start samo-recorder-export.service || true
  fi
}
trap rollback EXIT

install -m 0644 /srv/samo/deploy/samo-organism-v6.service /etc/systemd/system/samo-organism-v6.service
install -m 0644 /srv/samo/deploy/samo-recorder-export-v6.service /etc/systemd/system/samo-recorder-export-v6.service
install -m 0644 /srv/samo/deploy/samo-recorder-export-v6.timer /etc/systemd/system/samo-recorder-export-v6.timer
systemctl daemon-reload
install -d -o samo-organism -g samo-data -m 2750 "$root/state/tmp"

systemctl start samo-recorder-export.service
systemctl stop samo-recorder-export.timer
systemctl stop samo-organism.service samo-recorder-export.service

transition_unit="samo-v6-transition-$(date -u +%s)"
systemd-run --unit="$transition_unit" --slice=samo-aux.slice --wait --pipe \
  -p CPUQuota=10% -p MemoryMax=160000000 -p MemorySwapMax=0 -p TasksMax=4 \
  -p PrivateNetwork=yes -p ProtectSystem=strict -p ProtectHome=yes \
  -p 'CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH' \
  -p 'AmbientCapabilities=CAP_CHOWN CAP_DAC_OVERRIDE CAP_DAC_READ_SEARCH' \
  -p ReadWritePaths="$root/releases/core-v5" -p ReadWritePaths="$release" \
  -p ReadWritePaths="$root/state" -p ReadWritePaths="$root/site/data" \
  -p NoNewPrivileges=yes \
  -p WorkingDirectory="$release/code" \
  -p Environment=PYTHONDONTWRITEBYTECODE=1 \
  -p Environment=PYTHONPATH="$release/code" \
  /usr/bin/python3 "$release/code/deploy/transition-v6-files.py"

systemctl disable samo-organism.service samo-recorder-export.timer
systemctl enable samo-organism-v6.service samo-recorder-export-v6.timer
systemctl start samo-organism-v6.service

python3 - "$db" <<'PY'
import sqlite3,sys,time,zlib,json
p=sys.argv[1]
for _ in range(300):
 try:
  c=sqlite3.connect(f'file:{p}?mode=ro',uri=True);r=c.execute('select payload from checkpoint where id=1').fetchone();c.close()
  if r and json.loads(zlib.decompress(r[0]))['core']['step']>=1:break
 except sqlite3.Error:pass
 time.sleep(.5)
else:raise SystemExit('v6 checkpoint did not advance')
PY

systemctl start samo-recorder-export-v6.service
python3 - "$root/site/data/ecosystem.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert x['protocol']=='samo-ecology-v6-morphology'
assert x['episode']==0 and x['step']>=1
assert len(x['population'])<=8 and all(y.get('morphology') for y in x['population'])
assert any(y.get('kind')=='protocol_transition' for y in x['interventions'])
PY

systemctl start samo-recorder-export-v6.timer
systemctl is-active --quiet samo-organism-v6.service
systemctl is-active --quiet samo-recorder-export-v6.timer
systemctl is-active --quiet samo-web.service

complete=1
trap - EXIT
systemctl show samo-organism-v6.service -p ActiveState -p MainPID -p NRestarts -p CPUQuotaPerSecUSec -p MemoryMax -p MemorySwapMax
df -B1 "$root"
