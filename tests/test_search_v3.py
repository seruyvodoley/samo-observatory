import random,unittest
from samo.search_v3 import founder,edit,reproduce
from samo.genome import digest
from samo.vm import ins,MAX_CODE
class SearchV3Tests(unittest.TestCase):
 def test_opcode_operand_independent(self):
  a=edit(founder(),[0,0,0,1,32768]);self.assertEqual(a['modules'][0][0],ins('HIST',0))
  b=edit(founder(),[0,0,0,1,32769]);self.assertEqual(b['modules'][0][0],ins('HIST',1))
 def test_full_code_can_delete(self):
  g=founder();g['modules'][0]=[ins('CONST')]*MAX_CODE
  self.assertEqual(len(edit(g,[0,0,1,0,0])['modules'][0]),MAX_CODE-1)
 def test_degenerate_operator_can_escape(self):
  g=founder();g['search']=[ins('CONST'),ins('EMIT')]*5;r=random.Random(119)
  results=[reproduce(g,r) for _ in range(200)]
  self.assertTrue(any(c is not None and digest(c)!=digest(g) for c,_ in results))
  self.assertTrue(any(i['external'] for _,i in results))
 def test_search_cost_recorded(self):
  _,info=reproduce(founder(),random.Random(0));self.assertGreater(info['search_fuel'],0)
 def test_replay(self):
  self.assertEqual(reproduce(founder(),random.Random(4)),reproduce(founder(),random.Random(4)))
