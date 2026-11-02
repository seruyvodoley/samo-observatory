#!/bin/sh
set -eu
systemctl stop samo-recorder-export.timer samo-publish.timer
systemctl stop samo-organism.service samo-recorder-export.service samo-publish.service
python3 - <<'PY'
from pathlib import Path
for unit in ('samo-organism','samo-recorder-export','samo-publish'):
 p=Path('/etc/systemd/system/'+unit+'.service.d/z-v4.conf')
 if p.exists():p.unlink()
PY
systemctl daemon-reload
cd /srv/samo/code
PYTHONDONTWRITEBYTECODE=1 python3 -m samo.ecology_runtime audit --db /srv/samo/state/ecology.sqlite
systemctl reset-failed samo-organism.service
systemctl start samo-organism.service
systemctl start samo-recorder-export.timer samo-publish.timer
