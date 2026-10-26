"""Simulated HTTP, including full 16-case paired control/candidate executions."""
import json
import base64
import unittest
from unittest.mock import patch

from assistant import BriefError
from evaluate_context_selector import execute
from diagnose_rag_format import execute as diagnostic
from inspect_rag_run import inspect
import test_rag_format as fixture_module


class ContextComparisonTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.FormatDiagnosticTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.support_all = False
        original = f.opened
        def opened(request, timeout):
            endpoint = request.full_url.rsplit('/', 1)[-1]
            payload = json.loads(request.data) if request.data else None
            if endpoint == 'tags':
                return fixture_module.Response(json.dumps({'models': [
                    {'name': 'qwen2.5:3b', 'digest': f.model_digest},
                    {'name': 'nomic-embed-text:v1.5', 'digest': 'b' * 64}]}).encode())
            if endpoint == 'embed':
                return fixture_module.Response(json.dumps({'embeddings': [[1, 0] for _ in payload['input']]}).encode())
            if endpoint == 'generate' and 'format' in payload:
                ids = payload['format']['properties']['evidence_ids']['items']['enum']
                return fixture_module.Response(json.dumps(dict(done=True, done_reason='stop',
                    response=json.dumps({'evidence_ids': ids[:1]}))).encode())
            if endpoint == 'generate' and self.support_all:
                return fixture_module.Response(json.dumps(dict(done=True, done_reason='stop',
                    response='{"decision":"supported"}')).encode())
            return original(request, timeout)
        f.opened = opened
        f.no_format_baseline()
        with patch('diagnose_rag_format.CapturedTransport', side_effect=f.factory):
            diagnostic(f.output, f.baseline, True, experiment='short-system')
        self.baseline = f.output
        self.output = f.root / 'paired'
        f.calls.clear()

    def invoke(self):
        return execute(self.output, self.baseline, True, self.fixture.factory)

    def events(self):
        return [json.loads(line) for line in (self.output / 'events.jsonl').read_text().splitlines()]

    def test_always_abstain_pairing_shared_ranking_and_separate_gate_counts(self):
        report = self.invoke()
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(report['request_counts'], dict(embedding=15, decision=30, selection=0))
        for arm in report['arms'].values():
            self.assertEqual(arm['reference_checks_passed'], 8)
            self.assertEqual((arm['answerable_count'], arm['answerable_reference_passed']), (8, 0))
            self.assertEqual((arm['model_abstention_count'], arm['model_abstention_reference_passed']), (7, 7))
            self.assertEqual((arm['application_gate_count'], arm['application_gate_passed']), (1, 1))
        self.assertTrue(report['database_unchanged'])
        self.assertEqual(inspect(self.output)['completed_observations'], 32)
        rows = report['cases']
        self.assertEqual([r['arm'] for r in rows[:4]], ['B', 'C', 'C', 'B'])
        for name in {r['case'] for r in rows}:
            pair = {r['arm']: r for r in rows if r['case'] == name}
            self.assertEqual(pair['B']['ranking'], pair['C']['ranking'])
            if pair['C']['context_selection']['route'] == 'fallback':
                self.assertEqual(pair['B']['context_selection']['records'], pair['C']['context_selection']['records'])
        routed = [r for r in rows if r['arm'] == 'C' and r['context_selection']['route'] != 'fallback']
        self.assertEqual(len(routed), 4)
        self.assertTrue(all(len(r['context_selection']['records']) == 1 for r in routed))
        gate_events = [e for e in self.events() if e['scope'].get('case') == 'unknown_order']
        self.assertFalse(any(e['event'] in ('http_request_prepared', 'inference_dispatch') for e in gate_events))
        self.assertTrue(all('failure_stage' not in r['diagnostics'] for r in rows if not r['order_found']))
        for event in self.events():
            if event['event'] == 'http_request_prepared' and event['url'].endswith('/generate'):
                payload = json.loads(base64.b64decode(event['body_base64']))
                self.assertEqual(set(json.loads(payload['prompt'])), {'question', 'records'})

    def test_embedding_digest_mismatch_stops_before_any_inference(self):
        baseline_runtime = self.baseline / 'runtime.json'
        runtime = json.loads(baseline_runtime.read_text())
        next(m for m in runtime['inventory']['models'] if m['name'] == 'nomic-embed-text:v1.5')['digest'] = 'c' * 64
        baseline_runtime.write_text(json.dumps(runtime))
        with self.assertRaisesRegex(ValueError, 'embedding_digest_differs_from_baseline'):
            self.invoke()
        self.assertFalse(any(e['event'] == 'inference_dispatch' for e in self.events()))

    def test_all_supported_reaches_true_sixty_generation_bound_and_flags_false_support(self):
        self.support_all = True
        report = self.invoke()
        self.assertEqual(report['request_counts'], dict(embedding=15, decision=30, selection=30))
        self.assertEqual(report['generation_requests'], 60)
        self.assertTrue(all(arm['false_support'] == 7 for arm in report['arms'].values()))
        self.assertTrue(all(arm['selection_requests'] == 15 for arm in report['arms'].values()))
        for row in report['cases']:
            sources = {r['evidence_id']: r['text'] for r in row['context_selection']['records']}
            self.assertTrue(all(f['quote'] == sources[f['evidence_id']] for f in row['result'].get('findings', [])))
        self.assertTrue(report['database_unchanged'])

    def test_retrieval_failure_is_not_counted_as_model_abstention(self):
        opened = self.fixture.opened
        def fail_embed(request, timeout):
            if request.full_url.endswith('/embed'):
                raise OSError('synthetic transport failure')
            return opened(request, timeout)
        self.fixture.opened = fail_embed
        report = self.invoke()
        self.assertEqual(report['request_counts'], dict(embedding=15, decision=0, selection=0))
        for arm in report['arms'].values():
            self.assertEqual(arm['failures_by_stage'], {'retrieval': 15})
            self.assertEqual(arm['model_abstention_reference_passed'], 0)
            self.assertEqual(arm['model_abstention_decision_requests'], 0)
            self.assertEqual(arm['application_gate_passed'], 1)

    def test_interrupt_preserves_first_arm_without_scoring_or_retry(self):
        opened = self.fixture.opened
        decisions = []
        def interrupt(request, timeout):
            if request.full_url.endswith('/generate'):
                decisions.append(True)
                if len(decisions) == 2:
                    raise KeyboardInterrupt()
            return opened(request, timeout)
        self.fixture.opened = interrupt
        with self.assertRaises(KeyboardInterrupt):
            self.invoke()
        recovered = inspect(self.output)
        self.assertEqual((recovered['state'], recovered['completed_observations']), ('interrupted', 1))
        self.assertEqual(len(decisions), 2)
        self.assertFalse(any(e['event'] == 'case_scored' for e in self.events()))

    def test_opt_in_existing_directory_and_generation_runtime_mismatch(self):
        with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
            execute(self.output, self.baseline, transport_factory=self.fixture.factory)
        self.assertFalse(self.output.exists())
        self.fixture.version = 'changed'
        with self.assertRaisesRegex(ValueError, 'runtime_version_differs_from_baseline'):
            self.invoke()
        self.assertFalse(any(e['event'] == 'inference_dispatch' for e in self.events()))
        with self.assertRaises(FileExistsError):
            self.invoke()
