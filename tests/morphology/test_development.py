import copy,random,tempfile,unittest,json,sqlite3
from morphology.development import *
from morphology.experiment import run
G=dict(modules=[[[0,1]],[]],router=[[0,0]],search=[[13,0]],dialect=[[],[],[],[]],memory=[0,1])
class MorphologyTests(unittest.TestCase):
 def test_repeatable(self):self.assertEqual(develop(G,founder()),develop(G,founder()))
 def test_architecture_identity(self):
  p=develop(G,founder())['phenotype'];self.assertEqual({n['binding'] for n in p['nodes'] if not n['decorative']},{b['id'] for b in bindings(G)})
 def test_bounded_recursive(self):
  g=founder();g['rules'][0]['code']=[[5,0,4,8],[3,1,0,0]];p=develop(G,g);self.assertLessEqual(p['fuel'],2048);self.assertLessEqual(len(p['phenotype']['nodes']),256);self.assertTrue(p['truncated']);self.assertEqual({n['binding'] for n in p['phenotype']['nodes'] if not n['decorative']},{b['id'] for b in bindings(G)})
 def test_invalid(self):
  for g in [None,{},dict(version=1,rules=[dict(id=0,code=[[99,0,0,0]])],root=0,next_id=1)]:
   with self.assertRaises(ValueError):develop(G,g)
 def test_mutation_and_neutrality(self):
  rng=random.Random(8);g=founder();hashes=set()
  for _ in range(300):g,op=mutate(g,rng);hashes.add(develop(G,g)['phenotype_hash'])
  self.assertGreater(len(hashes),1)
 def test_unreachable_rule_is_neutral(self):
  a=founder();b=copy.deepcopy(a);b['rules'].append(dict(id=1,instruction_ids=[2],code=[[3,1,0,0]]));b['next_id']=2;b['next_instruction_id']=3
  self.assertNotEqual(digest(a),digest(b));self.assertEqual(develop(G,a)['phenotype_hash'],develop(G,b)['phenotype_hash'])
 def test_resume(self):
  with tempfile.TemporaryDirectory() as d:
   a=d+'/a.db';b=d+'/b.db';run(a,G,[0],5);run(a,G,[0],10);run(b,G,[0],10)
   x=sqlite3.connect(a);y=sqlite3.connect(b)
   self.assertEqual(x.execute('select payload from events order by line,n').fetchall(),y.execute('select payload from events order by line,n').fetchall())
if __name__=='__main__':unittest.main()
class IntegrationTests(unittest.TestCase):
 def test_computational_path_is_unchanged(self):
  from morphology.ecology import initial,advance
  from samo.ecology_v4 import advance as core_advance
  s=initial(11);core=copy.deepcopy(s['core']);births=0
  for _ in range(50):
   core,e=core_advance(core);s,event=advance(s);self.assertEqual(s['core'],core);self.assertEqual(set(s['traits']),{x['id'] for x in core['population']})
   for record in event['morphology']:
    births+=1;self.assertEqual(record['morphology_hash'],digest(record['morphology_genome']))
  self.assertGreater(births,4)
class RuntimeTests(unittest.TestCase):
 def test_reopen_coevolution(self):
  from morphology.runtime import Recorder
  with tempfile.TemporaryDirectory() as d:
   r=Recorder(d+'/r.sqlite',3)
   for _ in range(12):r.step()
   state=copy.deepcopy(r.state);r.close();r=Recorder(d+'/r.sqlite',3);self.assertEqual(digest(r.state),digest(state));r.step();self.assertEqual(r.state['ecology']['core']['step'],13);r.close()
