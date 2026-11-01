import json,zlib,tempfile,unittest
from pathlib import Path
from morphology.runtime_v5 import Recorder
from morphology.observer_v5 import verified_snapshot
from morphology.ecology_v5 import advance
from morphology.development import digest
class ObserverTests(unittest.TestCase):
 def test_cache_is_content_addressed_and_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   r=Recorder(Path(d)/'r.sqlite');r.initialize(3)
   for _ in range(3):s,e=advance(r.load());r.commit(s,e)
   cache={};a=verified_snapshot(r,cache);self.assertEqual(cache['checked'],3);b=verified_snapshot(r,cache);self.assertEqual(cache['hits'],3);self.assertEqual(a['events'],b['events'])
   row=r.db.execute('select n,payload from events order by n limit 1').fetchone();e=json.loads(zlib.decompress(row[1]));e['index']=99
   with r.db:r.db.execute('update events set payload=?,hash=? where n=?',(zlib.compress(json.dumps(e).encode()),digest(e),row[0]))
   with self.assertRaises(ValueError):verified_snapshot(r,cache)
   r.close()
