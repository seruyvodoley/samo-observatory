import random
import tempfile
import unittest
from pathlib import Path

from samo.ecosystem import create, load, save, step
from samo.evaluator import task_stream
from samo.genome import ancestor, recombine


class EcosystemTests(unittest.TestCase):
    def test_stream_is_counter_deterministic_and_nonterminal(self):
        self.assertEqual(task_stream(4, 99)[0], task_stream(4, 99)[0])
        self.assertNotEqual(task_stream(4, 99)[0], task_stream(4, 100)[0])

    def test_recombination_returns_valid_genome_and_provenance(self):
        a, b = ancestor(), ancestor()
        child, changed = recombine(a, b, random.Random(2))
        self.assertIn('search', child)
        self.assertIsInstance(changed, list)

    def test_ecosystem_step_and_checkpoint(self):
        state = create(33, 3)
        for _ in range(4):
            step(state)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'checkpoint.json'
            save(state, path)
            restored = load(path)
            self.assertEqual(restored['step'], state['step'])
            self.assertEqual(restored['events'], state['events'])

    def test_extinction_is_a_new_registered_episode(self):
        state = create(12, 2)
        state['population'].clear()
        step(state)
        events = [e for e in state['events'] if e['kind'] == 'recolonization']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['episode'], 1)


if __name__ == '__main__':
    unittest.main()
