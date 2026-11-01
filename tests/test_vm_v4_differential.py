import random,unittest
from samo import vm,vm_v4
class VMDifferentialTests(unittest.TestCase):
 def test_all_opcodes_random_control_flow(self):
  rng=random.Random(7809);covered=set()
  for _ in range(1000):
   code=[[rng.randrange(len(vm.OPS)),rng.randrange(-4,13)] for _ in range(rng.randrange(1,25))];covered.update(i[0] for i in code)
   def run(module):
    try:return ('ok',module.execute(code,[12,33,79],[0]*16,[[[1,0]] for _ in range(4)],random.Random(67),module.Meter(64,deadline=float('inf'))))
    except (module.Trap,ValueError) as exc:return ('trap',str(exc))
   self.assertEqual(run(vm),run(vm_v4))
  self.assertEqual(covered,set(range(len(vm.OPS))))
 def test_stack_and_input_caps(self):
  with self.assertRaisesRegex(vm_v4.Trap,'stack limit'):vm_v4.execute([[0,1]],initial=[0]*128)
  with self.assertRaisesRegex(vm_v4.Trap,'input limit'):vm_v4.execute([],history=[0]*257)
