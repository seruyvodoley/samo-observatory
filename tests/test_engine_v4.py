import copy,random,tempfile,unittest,json
from pathlib import Path
from samo.ecology_v4 import initial,advance,measure,trials
from samo.genome_v4 import digest,predict
from samo.vm_v4 import execute,ins,Meter,Trap
from samo.runtime_v4 import Recorder,public_snapshot
class EngineV4Tests(unittest.TestCase):
 def test_empty_memory_stays_empty(self):
  self.assertEqual(execute([ins('CONST',7),ins('STORE')],memory=[])[2],[])
 def test_reference_arithmetic_fuzz(self):
  r=random.Random(302)
  for _ in range(500):
   a,b=r.randrange(65536),r.randrange(65536)
   for op,f in [('ADD',lambda:a+b),('SUB',lambda:a-b),('MUL',lambda:a*b),('XOR',lambda:a^b),('MOD',lambda:a%b if b else 0)]:
    self.assertEqual(execute([ins('CONST',a),ins('CONST',b),ins(op)])[0],f()&65535)
 def test_traps_and_fuel(self):
  with self.assertRaisesRegex(Trap,'underflow'):execute([ins('ADD')])
  with self.assertRaisesRegex(Trap,'fuel'):execute([ins('JMP')],meter=Meter(7))
 def test_recovery(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'db';r=Recorder(p);r.initialize(12);a,e=advance(r.load());r.close();r=Recorder(p);b,f=advance(r.load());self.assertEqual(e,f);r.commit(b,f);r.close();r=Recorder(p);self.assertEqual(digest(r.load()),digest(a));self.assertEqual(public_snapshot(r)['protocol'],'samo-ecology-v4');r.close()
 def test_no_duplicate_births(self):
  s=initial(32)
  for _ in range(70):
   old=copy.deepcopy(s);s,e=advance(s)
   if e['birth']:
    self.assertTrue(e['genotype_changed']);self.assertFalse(e['duplicate']);self.assertNotIn(digest(e['candidate']['genome']),[digest(x['genome']) for x in old['population']])
   self.assertEqual(len({digest(x['genome']) for x in s['population']}),len(s['population']))
 def test_extinction_and_new_episode(self):
  s,e=advance(initial(8));s['population']=[];s,e=advance(s);self.assertEqual(e['kind'],'recolonization');self.assertEqual(s['episode'],1)
 def test_meta_cost_bounded(self):
  s=initial(17);seen=False
  for _ in range(80):
   s,e=advance(s)
   if e['meta_fuel']:seen=True;self.assertLessEqual(e['meta_fuel'],4*(512+4096))
  self.assertTrue(seen)
 def test_partial_signal_and_control(self):
  from samo.search_v4 import founder
  g=founder();h=copy.deepcopy(g);h['modules']=[[ins('HIST')]];t=trials(555,3);a,b=measure(g,t),measure(h,t);self.assertNotEqual(a['selection_score'],b['selection_score']);self.assertGreater(b['families']['constant'],a['families']['constant'])

class RandomControlIdentityTests(unittest.TestCase):
 def test_random_does_not_inherit_population_parent(self):
  s=initial(71,mode='random');births=0
  for _ in range(30):
   s,e=advance(s)
   self.assertEqual(e['parent_ids'],[])
   if e['birth']:
    births+=1;self.assertEqual(e['candidate']['parents'],[]);self.assertEqual(e['candidate']['source']['kind'],'random_search')
  self.assertGreater(births,0)
