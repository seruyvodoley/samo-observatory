import copy
import json
import random
import tempfile
import time
import unittest
from pathlib import Path
from samo.vm import execute, ins, Meter, Trap, OPS
from samo.genome import ancestor, apply_edits, digest, reproduce, predict, validate
from samo.evaluator import evaluate, tasks, strong_baseline
from samo.archive import Archive
from samo.engine import run_experiment
from samo.exporter import export, verify, build_snapshot
from samo.cli import replay


def encoded(name, arg=0):
    return OPS.index(name) + len(OPS) * (arg + 1724)


def emitter(values):
    return [x for value in values for x in (ins('CONST', value), ins('EMIT'))]


class VMTests(unittest.TestCase):
    def test_arithmetic_wrap_and_prefix(self):
        self.assertEqual(execute([ins('HIST'), ins('CONST', 1), ins('ADD')], [65535])[0], 0)

    def test_infinite_loop_consumes_shared_fuel(self):
        meter = Meter(17)
        with self.assertRaisesRegex(Trap, 'fuel'):
            execute([ins('JMP')], meter=meter)
        self.assertEqual(meter.used, 17)

    def test_stack_memory_and_output_limits(self):
        for code in ([ins('DROP')], [ins('CONST'), ins('JMP')],
                     [ins('CONST'), ins('EMIT'), ins('JMP')]):
            with self.assertRaises(Trap):
                execute(code, meter=Meter(1000))
        with self.assertRaises(Trap):
            execute([], memory=[0] * 65)

    def test_deadline(self):
        with self.assertRaisesRegex(Trap, 'deadline'):
            execute([ins('JMP')], meter=Meter(1000, deadline=time.monotonic() - 1))

    def test_no_host_random_or_nested_calls(self):
        with self.assertRaisesRegex(Trap, 'capability'):
            execute([ins('RAND')])
        with self.assertRaisesRegex(Trap, 'nested'):
            execute([ins('CALL')], dialect=[[ins('CALL')]])

    def test_reject_malformed_host_objects(self):
        for code in ([[True, 0]], [[999, 0]], [[0, 'import os']], [[0, 10**100]]):
            with self.assertRaises(ValueError):
                execute(code)

    def test_dynamic_addressing_and_mutable_working_memory(self):
        value, _, memory = execute([ins('CONST', 42), ins('CONST', 3), ins('STORE', -1),
                                    ins('CONST', 3), ins('MEM', -1)])
        self.assertEqual((value, memory[3]), (42, 42))

    def test_loop_program_computes_sum(self):
        # Sum history from oldest through newest using inherited VM-level representation.
        code = [ins('CONST', 0), ins('STORE', 0), ins('LEN'), ins('STORE', 1),
                ins('MEM', 1), ins('JZ', 19), ins('MEM', 1), ins('CONST', 1), ins('SUB'),
                ins('DUP'), ins('STORE', 1), ins('HIST', -1), ins('MEM', 0), ins('ADD'),
                ins('STORE', 0), ins('JMP', 4), ins('HALT'), ins('HALT'), ins('HALT'), ins('MEM', 0)]
        self.assertEqual(execute(code, [1, 2, 3, 4], meter=Meter(200))[0], 10)


class EvolutionTests(unittest.TestCase):
    def test_inherited_structural_search_changes_next_offspring(self):
        g = ancestor()
        # First edit inserts a predictor; second rewrites the search's own first CONST.
        g['search'] = emitter([0, 0, 2, encoded('CONST', 7), 1, 0, 0, encoded('CONST', 3)])
        child, changes, _, status = reproduce(g, random.Random(4))
        self.assertEqual(status, 'ok')
        self.assertIn('search', changes)
        self.assertNotEqual(g['search'], child['search'])
        grandchild, changes2, _, _ = reproduce(child, random.Random(4))
        self.assertIn('memory', changes2)
        self.assertNotEqual(child['memory'], grandchild['memory'])
        self.assertEqual(g['search'][0], ins('CONST', 0))

    def test_semantics_change_executes_and_is_inherited(self):
        g = ancestor()
        g['modules'] = [[ins('CALL')]]
        g['dialect'][0] = [ins('HIST'), ins('CONST', 1), ins('ADD')]
        self.assertEqual(predict(g, [3])[0], 4)
        # target=2 chooses dialect 0; position 4 modulo length 3 selects constant.
        child, _ = apply_edits(g, [2, 4, 0, encoded('CONST', 2)])
        self.assertEqual(predict(child, [3])[0], 5)
        self.assertNotEqual(digest(g['dialect']), digest(child['dialect']))

    def test_sterility_has_no_fallback(self):
        g = ancestor()
        g['search'] = []
        child, _, _, status = reproduce(g, random.Random(1))
        self.assertIsNone(child)
        self.assertEqual(status, 'sterile')

    def test_memory_loss_and_component_deletion(self):
        g = ancestor()
        child, changes = apply_edits(g, [3, 0, 1, 0, 5, 0, 1, 0])
        self.assertEqual(len(child['memory']), 15)
        self.assertEqual(len(child['modules']), 1)
        self.assertEqual(len(g['modules']), 2)

    def test_search_ablations_restrict_targets(self):
        g = ancestor()
        child, changes = apply_edits(g, [1, 0, 2, encoded('CONST')], 'gp')
        self.assertEqual(child['search'], g['search'])
        self.assertEqual(changes, ['modules'])

    def test_rng_reproducibility(self):
        self.assertEqual(reproduce(ancestor(), random.Random(8)), reproduce(ancestor(), random.Random(8)))


class EvaluatorTests(unittest.TestCase):
    def test_unknown_future_cannot_affect_prediction(self):
        a = list(range(24))
        b = a[:12] + [900] * 12
        ra = evaluate(ancestor(), [('t', 'x', a)], 'train')['rows'][0]
        rb = evaluate(ancestor(), [('t', 'x', b)], 'train')['rows'][0]
        self.assertEqual(ra['prediction'], rb['prediction'])
        self.assertEqual(ra['commitment'], rb['commitment'])
        self.assertNotEqual(ra['target'], rb['target'])

    def test_budget_is_not_exceeded(self):
        g = ancestor()
        g['modules'] = [[ins('JMP')]]
        result = evaluate(g, tasks(77), 'train', fuel_limit=179)
        self.assertEqual(result['fuel'], 179)
        self.assertEqual(result['status'], 'budget')
        self.assertGreater(result['failures'], 0)

    def test_controls_and_new_families(self):
        ts = tasks(8)
        self.assertEqual(len(ts), 12)
        self.assertEqual(strong_baseline([i*i for i in range(12)]), 144)
        self.assertNotEqual(tasks(8), tasks(9))
        result = evaluate(ancestor(), ts, 'confirm', baseline='expert')
        self.assertGreater(result['accuracy'], .6)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.archive = Archive(Path(self.temp.name) / 'test.sqlite')

    def tearDown(self):
        self.archive.close()
        self.temp.cleanup()

    def test_end_to_end_replay_and_export(self):
        run = run_experiment(self.archive, 17, 'samo', 42, attempts=12, fuel_ceiling=20000)
        self.assertLessEqual(run['fuel'], 20000)
        self.assertEqual(replay(self.archive, {'17': 42})['reproduced_runs'], 1)
        out = Path(self.temp.name) / 'snapshot.json'
        export(self.archive, out)
        data = json.loads(out.read_text())
        self.assertNotIn('rng_state', data['runs'][0])
        self.assertNotIn('secret_commitment', data['runs'][0])
        self.assertNotIn('rng_before', data['events'][0])
        self.assertEqual(data['source_status'], 'stopped')
        h = data.pop('snapshot_hash')
        self.assertEqual(digest(data), h)

    def test_empty_archive_is_honest(self):
        self.assertEqual(build_snapshot(self.archive)['source_status'], 'empty')
        self.assertEqual(build_snapshot(self.archive)['events'], [])

    def test_tamper_fails_closed(self):
        run_experiment(self.archive, 2, 'gp', 7, attempts=2)
        self.archive.db.execute("UPDATE artifacts SET payload='{}'")
        self.archive.db.commit()
        with self.assertRaises(ValueError):
            verify(self.archive)

    def test_quota_and_no_archive_pruning(self):
        self.archive.limit = 1
        with self.assertRaisesRegex(RuntimeError, 'quota'):
            self.archive.check_capacity()

    def test_negative_results_and_nonmonotonic_history(self):
        run_experiment(self.archive, 41, 'samo', 42, attempts=30)
        events = self.archive.all('events')
        self.assertGreater(len(events), 1)
        self.assertEqual(len(events), len(self.archive.all('evidence')) - 2)
        self.assertTrue(all(e['evidence_id'] for e in events))

    def test_duplicate_runs_not_overwritten(self):
        run_experiment(self.archive, 1, 'fixed', 42, attempts=2)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            run_experiment(self.archive, 1, 'fixed', 42, attempts=2)

class ContinuationTests(unittest.TestCase):
    def test_checkpoint_resumes_exact_active_state(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'a.sqlite');b=Archive(Path(d)/'b.sqlite')
            try:
                whole=run_experiment(a, 211, 'gp', 9, attempts=8)
                part=run_experiment(b, 211, 'gp', 9, attempts=8, checkpoint_steps=3)
                self.assertEqual(part['status'],'interrupted')
                self.assertNotIn('confirm',part)
                final=run_experiment(b,211,'gp',9,resume_id=part['id'])
                self.assertEqual(whole['active_hash'],final['active_hash'])
                self.assertEqual(whole['confirm']['behavior_hash'],final['confirm']['behavior_hash'])
                self.assertEqual(whole['fuel'],final['fuel'])
                verify(b)
            finally:
                a.close();b.close()

    def test_noop_is_not_reported_as_change(self):
        g=ancestor()
        child,changes=apply_edits(g,[3,0,0,0])
        self.assertEqual(g,child)
        self.assertEqual(changes,[])

    def test_random_search_records_true_parent(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'a.sqlite')
            try:
                run=run_experiment(a,17,'random',123,attempts=8)
                for event in a.all('events')[1:]:
                    self.assertEqual(event['parent_ids'],[run['id']+':0'])
                    self.assertEqual(event['generation'],1)
                verify(a)
            finally:a.close()

class SecurityAndRecoveryTests(unittest.TestCase):
    def test_dialect_loop_shares_parent_fuel(self):
        meter=Meter(23)
        with self.assertRaisesRegex(Trap,'fuel'):
            execute([ins('CALL')],dialect=[[ins('JMP')]],meter=meter)
        self.assertEqual(meter.used,23)

    def test_compressed_archive_bomb_is_bounded(self):
        import zlib
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'a.sqlite')
            try:
                a.run({'id':'x'})
                a.db.execute('INSERT INTO evidence VALUES(?,?,?)',('x','x',zlib.compress(b'0'*1_000_001)))
                a.db.commit()
                with self.assertRaisesRegex(ValueError,'limit'):
                    list(a.iter_records('evidence'))
            finally:a.close()

    def test_modified_event_measurement_is_rejected(self):
        from samo.genome import canonical
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'a.sqlite')
            try:
                run_experiment(a,17,'gp',42,attempts=2)
                event=a.all('events')[0];event['score']['accuracy']=.99
                a.db.execute('UPDATE events SET payload=? WHERE id=?',(canonical(event).decode(),event['id']))
                a.db.commit()
                with self.assertRaisesRegex(ValueError,'score'):
                    verify(a)
            finally:a.close()

    def test_interruption_restores_committed_checkpoint_not_best(self):
        from unittest.mock import patch
        import samo.engine as engine
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'a.sqlite');b=Archive(Path(d)/'b.sqlite')
            original=engine.reproduce;calls=[0]
            def interrupted(*args,**kwargs):
                calls[0]+=1
                if calls[0]==3:raise KeyboardInterrupt()
                return original(*args,**kwargs)
            try:
                whole=run_experiment(a,41,'gp',42,attempts=8)
                with patch('samo.engine.reproduce',side_effect=interrupted):
                    part=run_experiment(b,41,'gp',42,attempts=8)
                self.assertEqual(part['status'],'interrupted')
                self.assertEqual(part['attempts'],2)
                final=run_experiment(b,41,'gp',42,resume_id=part['id'])
                self.assertEqual(final['active_hash'],whole['active_hash'])
                self.assertEqual(final['confirm']['behavior_hash'],whole['confirm']['behavior_hash'])
                verify(b)
            finally:a.close();b.close()


if __name__ == '__main__':
    unittest.main()
