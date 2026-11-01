import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from samo.ecology import initial, advance
from samo.ecology_runtime import Recorder, public_snapshot
from samo.genome import digest

class DurableEcologyTests(unittest.TestCase):
    def test_crash_before_commit_repeats_exact_transition(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'db.sqlite'; r=Recorder(path); r.initialize(901)
            start=r.load(); after,event=advance(start); r.close()
            r=Recorder(path); replay,ev=advance(r.load())
            self.assertEqual(event,ev); self.assertEqual(digest(after),digest(replay))
            r.commit(replay,ev); r.close(); r=Recorder(path)
            self.assertEqual(r.load()['step'],1); self.assertEqual(len(public_snapshot(r)['events']),1); r.close()

    def test_corrupt_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r=Recorder(Path(d)/'db'); r.initialize(1)
            r.db.execute("UPDATE checkpoint SET hash='bad'"); r.db.commit()
            with self.assertRaisesRegex(ValueError,'integrity'): r.load()
            r.close()

    def test_retention_is_explicit_and_resume_deterministic(self):
        with tempfile.TemporaryDirectory() as d, patch('samo.ecology_runtime.RECENT',4):
            r=Recorder(Path(d)/'db'); r.initialize(41)
            expected=initial(41)
            for _ in range(12):
                state,event=advance(r.load()); expected,_=advance(expected)
                r.commit(state,event)
            self.assertEqual(digest(state),digest(expected))
            public=public_snapshot(r)
            self.assertEqual(len(public['events']),4)
            self.assertEqual(public['retention']['pruned_records'],8)
            self.assertNotIn('seed',public); r.close()

    def test_extinction_recolonizes_distinct_full_population(self):
        state=initial(1); state,event=advance(state)
        dead_ids={x['id'] for x in state['population']}; state['population']=[]
        state,event=advance(state)
        self.assertEqual(event['kind'],'recolonization'); self.assertEqual(state['episode'],1)
        founders=[x for x in event['lifecycle'] if x['kind']=='founder']
        self.assertEqual(len(founders),state['size'])
        self.assertTrue(all(x['organism']['id'] not in dead_ids for x in founders))

    def test_real_structural_changes_and_fresh_tasks(self):
        state=initial(17); tasks=[]; changes=[]
        for _ in range(40):
            state,event=advance(state); tasks.append(event['task_hash']); changes+=event.get('changes',[])
        self.assertEqual(len(set(tasks)),40)
        self.assertTrue(changes); self.assertLessEqual(len(state['population']),8)

if __name__=='__main__': unittest.main()
