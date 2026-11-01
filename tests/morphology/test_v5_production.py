import copy,json,sqlite3,tempfile,unittest
from pathlib import Path
from morphology.ecology_v5 import initial,advance
from morphology.development import digest,develop,founder
from morphology.runtime_v5 import Recorder,public_snapshot,unpack
class V5Tests(unittest.TestCase):
 def test_same_tick_founders_are_parents(self):
  for seed in range(8):
   s,e=advance(initial(seed));known={}
   for r in e['morphology']:
    if r['parent']:self.assertIn(r['parent'],known);self.assertEqual(r['parent_morphology_hash'],known[r['parent']]['morphology_hash'])
    known[r['id']]=r
   self.assertEqual(set(s['traits']),{x['id'] for x in s['core']['population']})
 def test_inheritance_and_counterfactual(self):
  s=initial(4)
  for _ in range(100):
   prior=copy.deepcopy(s);s,e=advance(s);available=dict(prior['traits']);births={x['organism']['id']:x['organism'] for x in e['computational']['lifecycle'] if x['kind']=='founder'}
   if e['computational'].get('candidate'):births[e['computational']['candidate']['id']]=e['computational']['candidate']
   for r in e['morphology']:
    if r['parent']:
     base=available[r['parent']]['morphology_genome'];cf=develop(births[r['id']]['genome'],base)
     self.assertEqual(digest(base),r['parent_morphology_hash']);self.assertEqual(r['morphology_effect'],cf['phenotype_hash']!=r['phenotype_hash'])
    available[r['id']]=r
 def test_crash_replay_and_readonly_export(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'r.sqlite';r=Recorder(path);r.initialize(22)
   for _ in range(20):s,e=advance(r.load());r.commit(s,e)
   before=r.load();r.close();r=Recorder(path);self.assertEqual(digest(before),digest(r.load()));s,e=advance(before);r.commit(s,e);r.close()
   raw=path.read_bytes();r=Recorder(path,readonly=True);p=public_snapshot(r);r.close();self.assertEqual(raw,path.read_bytes());self.assertEqual(p['step'],21)
   for form in p['population']:self.assertEqual(develop(form['genome'],form['morphology']['morphology_genome'])['phenotype_hash'],form['morphology']['phenotype_hash'])
 def test_corrupt_checkpoint_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'r.sqlite';r=Recorder(p);r.initialize(1);r.db.execute("update checkpoint set hash='bad'");r.db.commit()
   with self.assertRaises(ValueError):r.load()
   r.close()
 def test_extinction_has_new_founders(self):
  s,e=advance(initial(5));s['core']['population']=[];s['traits']={};s,e=advance(s)
  self.assertEqual(s['core']['episode'],1)
  for r in e['morphology']:
   if r['operator']=='registered_morphology_founder':self.assertIsNone(r['parent']);self.assertEqual(r['morphology_hash'],digest(founder()))
if __name__=='__main__':unittest.main()
