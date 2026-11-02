set -eu
systemctl stop samo-recorder-export.timer samo-publish.timer
systemctl stop samo-organism.service samo-recorder-export.service samo-publish.service
python3 - <<'PY'
from pathlib import Path
for unit in ('samo-organism.service','samo-recorder-export.service','samo-publish.service'):
 p=Path('/etc/systemd/system')/(unit+'.d')/'zz-v5.conf'
 if p.exists():p.unlink()
PY
systemctl daemon-reload
systemctl reset-failed samo-organism.service
systemctl start samo-organism.service
systemctl start samo-recorder-export.service
systemctl start samo-recorder-export.timer samo-publish.timer
systemctl start samo-publish.service
