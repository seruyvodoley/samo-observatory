"""One explicit infrastructure-only migration. Stop organism before running this tool."""
import json
import sqlite3
import sys
import zlib
from samo.engine import source_hash,now
from samo.genome import digest

c=sqlite3.connect(sys.argv[1]);row=c.execute('SELECT payload,hash,source FROM checkpoint WHERE id=1').fetchone()
s=json.loads(zlib.decompress(row[0]));assert digest(s)==row[1]
if row[2]==source_hash(): raise RuntimeError('already migrated; do not append duplicate intervention')
with c:
 c.execute('CREATE TABLE IF NOT EXISTS interventions(id INTEGER PRIMARY KEY,payload TEXT)')
 item=dict(kind='recorder_snapshot_isolation',observed_at=now(),at_attempt=s['step'],state_hash=row[1],previous_source=row[2],new_source=source_hash(),reason='Export from SQLite online-backup memory snapshot; release source read locks before validation. Evolutionary population, RNG, protocol and selection unchanged.')
 c.execute('INSERT INTO interventions(payload) VALUES(?)',(json.dumps(item),))
 c.execute('UPDATE checkpoint SET source=? WHERE id=1',(source_hash(),))
c.close();print(json.dumps(dict(migration='explicit recorder-only',attempt=s['step'],state_hash_unchanged=row[1])))
