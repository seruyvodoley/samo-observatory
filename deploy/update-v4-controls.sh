set -eu
if test -e /srv/samo/releases/core-v4/controls-fixed.marker; then echo "correction already applied" >&2; exit 1; fi
systemctl stop samo-recorder-export.timer samo-publish.timer
systemctl stop samo-organism.service samo-recorder-export.service samo-publish.service
cd /srv/samo/releases/core-v4/code
PYTHONDONTWRITEBYTECODE=1 python3 -m samo.runtime_v4 audit --db /srv/samo/state/ecology-v4.sqlite
python3 - <<'PY'
import sqlite3
a=sqlite3.connect('file:/srv/samo/state/ecology-v4.sqlite?mode=ro',uri=True);b=sqlite3.connect('/srv/samo/releases/core-v4-before-controls.sqlite');a.backup(b);b.close();a.close()
PY
tar -czf /srv/samo/releases/core-v4-before-controls.tgz samo protocols tools
cp /srv/samo/releases/ecology_v4-controls-fixed.py samo/ecology_v4.py
cp /srv/samo/releases/genome_v4-controls-fixed.py samo/genome_v4.py
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import sqlite3,zlib,json
from samo.runtime_v4 import source_hash
from samo.genome_v4 import digest
from samo.engine import now
c=sqlite3.connect('/srv/samo/state/ecology-v4.sqlite');payload,state_hash,old=c.execute('select payload,hash,source from checkpoint where id=1').fetchone();state=json.loads(zlib.decompress(payload));assert digest(state)==state_hash;new=source_hash()
with c:
 c.execute('update checkpoint set source=? where id=1',(new,))
 c.execute('insert into interventions(payload) values(?)',(json.dumps(dict(kind='registered_code_correction',at=now(),at_attempt=state['step'],reason='Random control has no recombination or inherited parent; removed unused legacy edit ABI from genome_v4. Production meta transitions invariant in 200 paired tests; checkpoint payload, genome and PRNG unchanged.',old_source=old,new_source=new)),))
c.close();print('registered code correction at',state['step'])
PY
systemctl start samo-organism.service
systemctl start samo-recorder-export.timer samo-publish.timer
systemctl start samo-recorder-export.service
systemctl start samo-publish.service
