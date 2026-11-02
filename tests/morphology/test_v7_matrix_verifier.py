import unittest

from tools.run_v7_matrix import compute_projection
from samo.genome_v4 import digest


class MatrixVerifierTests(unittest.TestCase):
    def test_v6_and_v7_envelopes_compare_only_compute_transition(self):
        compute = {"accepted": True, "birth": False, "delta": 0.0}
        v6 = {"arm": "neutral", "computational": compute,
              "morphology_births": 3, "state_hash": "v6-envelope"}
        v7 = {"arm": "v7_neutral", "computational": compute,
              "morphology_events": [{"kind": "within_lineage_morphology_change"}],
              "state_hash": "v7-envelope"}
        self.assertEqual(digest(compute_projection(v6)), digest(compute_projection(v7)))

    def test_missing_compute_transition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing its computational transition"):
            compute_projection({"arm": "neutral"})


if __name__ == "__main__":
    unittest.main()
