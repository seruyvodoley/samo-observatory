import tempfile
import json
import unittest
import copy
from pathlib import Path

from morphology.ecology_v5 import initial as initial5, advance as advance5
from morphology.ecology_v6 import (ARMS, advance as advance6, initial as initial6,
                                   public_metrics, PROTOCOL)
from morphology.runtime_v6 import Recorder, snapshot
from samo.genome_v4 import digest


class V6EcologyTests(unittest.TestCase):
    def test_v4_compute_transition_is_identical_to_v5(self):
        for seed in (80931, 271828, 190023):
            old, new = initial5(seed), initial6(seed, arm="neutral")
            for _ in range(80):
                old, e5 = advance5(old)
                new, e6 = advance6(new)
                self.assertEqual(digest(e5["computational"]), digest(e6["computational"]))
                self.assertEqual(digest(old["core"]), digest(new["core"]))
                self.assertTrue(all(x["source"] == "active_parent" for x in e6["morphology_births"] if x["parents"]))
                self.assertTrue(all(not set(x) & {"fitness", "score", "selection_score"} for x in e6["morphology_births"]))

    def test_three_search_arms_keep_compute_core_identical(self):
        states = {arm: initial6(778899, arm=arm) for arm in ARMS}
        for _ in range(160):
            events = {}
            for arm in ARMS:
                states[arm], events[arm] = advance6(states[arm])
            baseline = digest(events["neutral"]["computational"])
            self.assertTrue(all(digest(events[a]["computational"]) == baseline for a in ARMS))
            core = digest(states["neutral"]["core"])
            self.assertTrue(all(digest(states[a]["core"]) == core for a in ARMS))
        self.assertTrue(all(s["arm"] == a for a, s in states.items()))

    def test_archive_has_descriptors_only_and_bounded_capacity(self):
        s = initial6(132451, arm="bounded_archive_diversity")
        for _ in range(120): s, _ = advance6(s)
        self.assertLessEqual(len(s["archive"]), 64)
        self.assertTrue(all("genome" not in x and "genotype" not in x for x in s["archive"]))

    def test_recorder_recovery_and_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "eco.sqlite"
            rec = Recorder(db)
            rec.initialize(77227, arm="novelty")
            state = rec.load()
            for _ in range(32):
                state, ev = advance6(state)
                rec.commit(state, ev)
            expected_next, expected_event = advance6(state)
            expected = digest(state)
            rec.close()
            rec = Recorder(db)
            restored = rec.load()
            self.assertEqual(digest(restored), expected)
            recovered_next, recovered_event = advance6(restored)
            self.assertEqual(expected_event["decision_hash"], recovered_event["decision_hash"])
            self.assertEqual(digest(expected_next["core"]), digest(recovered_next["core"]))
            snap = snapshot(rec)
            self.assertEqual(snap["protocol"], PROTOCOL)
            self.assertEqual(snap["step"], 32)
            self.assertEqual(len(snap["events"]), 32)
            rec.close()

    def test_hash_committed_event_retention_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Recorder(Path(d) / "retention.sqlite")
            rec.initialize(77331)
            state = rec.load()
            for i in range(1025):
                state["core"]["step"] = i + 1
                rec.commit(state, {"index": i, "fixture_only": "retention policy verification"})
            retained = rec.db.execute("select count(*) from events").fetchone()[0]
            summary = json.loads(rec.db.execute("select payload from retention where id=1").fetchone()[0])
            self.assertEqual(retained, 1024)
            self.assertEqual(summary["pruned_records"], 1)
            self.assertEqual(summary["through"], 0)
            self.assertEqual(rec.db.execute("pragma integrity_check").fetchone()[0], "ok")
            rec.close()

    def test_seeded_colonization_is_reproducible_and_not_archival_revival(self):
        a, b = initial6(99811, arm="neutral"), initial6(99811, arm="neutral")
        events_a, events_b = [], []
        for _ in range(3):
            a, ea = advance6(a); b, eb = advance6(b)
            events_a.append(ea); events_b.append(eb)
            self.assertEqual(ea["decision_hash"], eb["decision_hash"])
        founders = [x for e in events_a for x in e["morphology_births"] if not x["parents"]]
        self.assertTrue(all(x["source"] == "fresh_founder" for x in founders))
        self.assertTrue(founders)

    def test_explicit_extinction_stress_recolonizes_from_registered_founder(self):
        s = initial6(119903, arm="bounded_archive_diversity")
        for _ in range(12): s, _ = advance6(s)
        recolonizations = 0
        for _ in range(3):
            # Test-only extinction fixture; it is not written to scientific data.
            s["core"]["population"] = []
            s["traits"] = {}
            s["previous_active"] = {}
            s, e = advance6(s)
            recolonizations += int(e["computational"]["kind"] == "recolonization")
            founder_ids = {x["organism"]["id"] for x in e["computational"]["lifecycle"] if x["kind"] == "founder"}
            founders = [x for x in e["morphology_births"] if x["id"] in founder_ids]
            self.assertTrue(founders)
            self.assertTrue(all(x["source"] == "fresh_founder" and not x["parents"] for x in founders))
            self.assertTrue(all(set(x["parents"]) <= founder_ids for x in e["morphology_births"] if x["id"] not in founder_ids))
        self.assertEqual(recolonizations, 3)
        self.assertTrue(all("genome" not in x and "genotype" not in x for x in s["archive"]))


if __name__ == "__main__": unittest.main()
