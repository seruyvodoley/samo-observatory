import copy
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from morphology.development_v3 import (LIMITS, describe, develop_v3, founder_v3,
                                       mutate_v3, silhouette_distance, validate)
from morphology.ecology_v7 import (ALL_ARMS, CONTROL, advance, initial,
                                   public_metrics)
from morphology.ecology_v7 import _apply_niche_survival_veto, _update_feature_history
from morphology.runtime_v7 import Recorder, snapshot
from samo.genome_v4 import digest


class V7CandidateTests(unittest.TestCase):
    def test_founders_are_seeded_programs_not_a_frozen_preset(self):
        a=founder_v3(random.Random(77));b=founder_v3(random.Random(77))
        self.assertEqual(a,b)
        self.assertTrue(all(founder_v3(random.Random(x))!=a for x in range(8)))

    def test_step_zero_population_has_seeded_inherited_morphology(self):
        s=initial(615173,arm="v7_neutral")
        self.assertEqual(s["core"]["population"],[])
        self.assertEqual(s["traits"],{})
        with tempfile.TemporaryDirectory() as d:
            r=Recorder(Path(d)/"initial.sqlite");r.initialize(615173,arm="v7_neutral")
            s,event=advance(r.load());r.commit(s,event)
            self.assertEqual(set(s["traits"]),{x["id"] for x in s["core"]["population"]})
            self.assertEqual(s["morphology_births"],len(s["core"]["population"]))
            self.assertTrue(all(x["origin"]["kind"]=="fresh_founder" for x in s["traits"].values()))
            data=snapshot(r)
            self.assertEqual(len(data["population"]),4)
            self.assertTrue(all(json.loads(x["morphology"]["phenotype_payload"])["nodes"] for x in data["population"]))
            self.assertEqual(data["initial_morphology_assignments"],[])
            self.assertTrue(all(len(x["hash"])==64 and len(x["identity_hash"])==64 for x in data["population"]))
            self.assertTrue(all(x["morphology"]["phenotype_payload_hash"] for x in data["population"]))
            self.assertTrue(all("lifecycle" in x and isinstance(x["family"],str) for x in data["events"]))
            self.assertIn("active_unique_silhouettes",data["morphology"])
            r.close()

    def test_v3_is_bounded_and_reports_geometry_separately(self):
        g=founder_v3(random.Random(899))
        for _ in range(200):g,_=mutate_v3(g,random.Random(_))
        validate(g)
        seed_state=initial(901,arm="v7_neutral")
        seed_state,_=advance(seed_state)
        org=seed_state["core"]["population"][0]
        out=develop_v3(org["genome"],g)
        self.assertLessEqual(len(out["phenotype"]["nodes"]),LIMITS["nodes"])
        d=describe(out["phenotype"])
        self.assertIn("all_spheres",d);self.assertIn("spatially_compact",d)
        self.assertIn("silhouette_hash",d)
        self.assertEqual(len(d["silhouette_views"]),3)
        self.assertGreaterEqual(silhouette_distance(d["silhouette_views"],d["silhouette_views"]),0)

    def test_hostile_recursive_genome_hits_interpreter_caps(self):
        g={"version":3,"root":0,"rules":[{"id":0,"instruction_ids":[0],"code":[[8,0,64,64]]}],
           "next_id":1,"next_instruction_id":1}
        validate(g)
        state=initial(615173,arm="v7_neutral");state,_=advance(state)
        out=develop_v3(state["core"]["population"][0]["genome"],g)
        self.assertLessEqual(out["fuel"],LIMITS["fuel"])
        self.assertLessEqual(len(out["phenotype"]["nodes"]),LIMITS["nodes"])
        self.assertTrue(out["truncated"])

    def test_v6_control_and_v7_compute_core_are_byte_identical(self):
        states={arm:initial(615173,arm=arm) for arm in ALL_ARMS}
        for _ in range(12):
            events={}
            for arm in ALL_ARMS:states[arm],events[arm]=advance(states[arm])
            control=events[CONTROL]["computational"]
            for arm in ALL_ARMS[1:]:
                if arm=="v7_niche_survival":continue
                self.assertEqual(digest(events[arm]["computational"]),digest(control))
                self.assertEqual(digest(states[arm]["core"]),digest(states[CONTROL]["core"]))

    def test_live_niche_survival_is_a_visible_selection_intervention(self):
        state=initial(615173,arm="v7_niche_survival");state,event=advance(state)
        prior=copy.deepcopy(state["core"]);core=copy.deepcopy(prior)
        incumbent=prior["population"][0]
        fixture_traits=copy.deepcopy(state["traits"])
        fixture_traits[incumbent["id"]]["niche"]=[999,999,999,999]  # test-only singleton-cell fixture
        candidate=copy.deepcopy(incumbent);candidate["id"]="synthetic-test-candidate"
        core["population"]=[x for x in prior["population"] if x["id"]!=incumbent["id"]]+[candidate]
        core["births"]+=1;core["deaths"]+=1
        trial={"accepted":True,"candidate":candidate,"lifecycle":[{"kind":"death","id":incumbent["id"]}]}
        decision=_apply_niche_survival_veto(prior,core,trial,fixture_traits)
        self.assertEqual(decision["kind"],"last_live_morphology_niche")
        self.assertFalse(trial["accepted"])
        self.assertEqual(core["population"],prior["population"])
        self.assertTrue(trial["morphology_veto"]["compute_trial_was_evaluated"])

    def test_dual_rate_event_is_not_a_compute_birth_or_genome_change(self):
        state=initial(742901,arm="v7_dual_rate")
        found=None
        for _ in range(100):
            state,event=advance(state)
            if event["morphology_events"]:
                found=event["morphology_events"][0];break
        self.assertIsNotNone(found)
        self.assertEqual(found["kind"],"within_lineage_morphology_change")
        self.assertFalse(event["computational"].get("birth",False))
        self.assertIn(found["organism_id"],state["traits"])
        self.assertEqual(found["origin"]["kind"],"within_lineage_morphology_change")

    def test_archive_has_descriptors_only_and_extinction_recolonizes_fresh(self):
        s=initial(893047,arm="v7_archive_diversity")
        for _ in range(15):s,_=advance(s)
        self.assertTrue(all("genome" not in x and "genotype" not in x for x in s["archive"]))
        for episode in range(2):
            s["core"]["population"]=[];s["traits"]={}
            s,event=advance(s)
            founders=[x for x in event["morphology_births"] if not x["parents"]]
            self.assertTrue(founders)
            self.assertTrue(all(x["origin"]["kind"]=="fresh_founder" for x in founders))
            self.assertTrue(all(x["origin"].get("archive_genotype_donor") is False for x in founders))

    def test_checkpoint_recovery_replays_and_bounds_feature_history(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"v7.sqlite";r=Recorder(path);r.initialize(1047293,arm="v7_neutral")
            state=r.load()
            for _ in range(18):state,event=advance(state);r.commit(state,event)
            expected,_=advance(state);expected_hash=digest(expected)
            r.close();r=Recorder(path);restored=r.load()
            self.assertEqual(digest(restored),digest(state))
            replay,_=advance(restored);self.assertEqual(digest(replay["core"]),digest(expected["core"]))
            self.assertEqual(expected_hash,digest(expected))
            snap=snapshot(r)
            self.assertEqual(snap["protocol"],"samo-ecology-v7-morphology")
            self.assertLessEqual(len(restored["feature_history"]),512)
            self.assertLessEqual(len(restored["archive"]),64)
            self.assertEqual(r.db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            r.close()

    def test_service_cli_recovers_after_kill_and_resumes_without_reset(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"live.sqlite";out=Path(d)/"ecosystem.json"
            cmd=[sys.executable,"-m","morphology.runtime_v7","run","--db",str(db),"--seed","1628171",
                 "--arm","v7_neutral","--export",str(out),"--pause","0.1"]
            env={**os.environ,"PYTHONPATH":str(root),"PYTHONDONTWRITEBYTECODE":"1"}
            proc=subprocess.Popen(cmd,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if out.exists():
                    try:
                        first=json.loads(out.read_text())
                        if first["step"]>=3:break
                    except (OSError,json.JSONDecodeError):pass
                if proc.poll() is not None:
                    detail=proc.stderr.read().decode();proc.stderr.close();raise AssertionError(detail)
                time.sleep(.05)
            else:
                proc.kill();proc.wait();self.fail("service did not export live state")
            proc.send_signal(signal.SIGKILL);proc.wait(timeout=5);proc.stderr.close()
            prior_step=json.loads(out.read_text())["step"]
            verify=subprocess.run([sys.executable,"-m","morphology.runtime_v7","verify","--db",str(db)],cwd=root,env=env,capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(verify.stdout)["step"],prior_step)
            resumed=subprocess.run(cmd+["--max-steps","2"],cwd=root,env=env,capture_output=True,text=True,check=True,timeout=30)
            current=json.loads(out.read_text())
            self.assertEqual(current["step"],prior_step+2)
            self.assertEqual(json.loads(resumed.stdout.strip().splitlines()[-1])["step"],prior_step+2)

    def test_feature_history_is_bounded_and_evictions_are_committed(self):
        s=initial(1186327,arm="v7_neutral")
        for step in range(700):
            features={f"view-{i}":f"{step:04x}{i:04x}" for i in range(5)}
            _update_feature_history(s,{"features":features,"feature_ages":{}},step+1,{})
        self.assertEqual(len(s["feature_history"]),512)
        self.assertGreater(s["feature_evictions"],0)
        self.assertEqual(len(s["feature_eviction_root"]),64)

    def test_long_recorder_prunes_events_with_a_hash_chain(self):
        with tempfile.TemporaryDirectory() as d:
            r=Recorder(Path(d)/"bounded.sqlite");r.initialize(1327219,arm="v7_neutral")
            state=r.load()
            for i in range(1050):
                state["core"]["step"]=i+1
                r.commit(state,{"index":i,"fixture_only":"retention test, not experiment data"})
            kept=r.db.execute("select count(*) from events").fetchone()[0]
            retention=json.loads(r.db.execute("select payload from retention where id=1").fetchone()[0])
            self.assertEqual(kept,1024)
            self.assertEqual(retention["pruned_records"],26)
            self.assertEqual(retention["through"],25)
            self.assertEqual(r.db.execute("pragma integrity_check").fetchone()[0],"ok")
            self.assertLess(Path(d,"bounded.sqlite").stat().st_size,64_000_000)
            r.close()


if __name__=="__main__":unittest.main()
