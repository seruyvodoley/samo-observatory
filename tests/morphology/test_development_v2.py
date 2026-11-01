import random
import unittest

from morphology import development_v2 as morph


class MorphogenesisV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.computational = {"modules": [], "dialect": [], "router": [], "search": [], "memory": []}

    def test_seeded_founders_reproduce_and_vary(self):
        self.assertEqual(morph.founder_v2(random.Random(7)), morph.founder_v2(random.Random(7)))
        self.assertNotEqual(morph.founder_v2(random.Random(7)), morph.founder_v2(random.Random(8)))

    def test_all_four_shapes_can_be_inherited_by_mandatory_anchors(self):
        for shape in range(4):
            genome = {"version": 2, "root": 0, "next_id": 1, "next_instruction_id": 2,
                      "rules": [{"id": 0, "instruction_ids": [0, 1],
                                 "code": [[6, 0, 8, 0], [3, shape, 0, 0]]}]}
            developed = morph.develop_v2(self.computational, genome)
            anchors = [node for node in developed["phenotype"]["nodes"] if not node["decorative"]]
            self.assertEqual(len(anchors), developed["binding_count"])
            self.assertTrue(all(node["shape"] == shape for node in anchors))

    def test_branching_generates_spatially_distinct_nodes_within_limits(self):
        genome = {"version": 2, "root": 0, "next_id": 1, "next_instruction_id": 3,
                  "rules": [{"id": 0, "instruction_ids": [0, 1, 2],
                             "code": [[6, 0, 8, 0], [8, 0, 0, 16], [3, 2, 0, 0]]}]}
        developed = morph.develop_v2(self.computational, genome)
        points = {tuple(node["position"]) for node in developed["phenotype"]["nodes"] if node["decorative"]}
        anchors = [node for node in developed["phenotype"]["nodes"] if not node["decorative"]]
        self.assertGreater(len(points), 1)
        self.assertEqual(len(anchors), developed["binding_count"])
        self.assertLessEqual(len(developed["phenotype"]["nodes"]), morph.LIMITS["nodes"])
        self.assertLessEqual(developed["fuel"], morph.LIMITS["fuel"])
        self.assertTrue(developed["truncated"])

    def test_long_mutation_chain_remains_valid_and_bounded(self):
        for seed in range(12):
            rng = random.Random(seed)
            genome = morph.founder_v2(rng)
            for step in range(30):
                genome, _ = morph.mutate_v2(genome, random.Random(seed * 1000 + step))
                morph.validate(genome)
                developed = morph.develop_v2(self.computational, genome)
                self.assertLessEqual(len(developed["phenotype"]["nodes"]), morph.LIMITS["nodes"])
                self.assertLessEqual(developed["fuel"], morph.LIMITS["fuel"])


if __name__ == "__main__":
    unittest.main()
