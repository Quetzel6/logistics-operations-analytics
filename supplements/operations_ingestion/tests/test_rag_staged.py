import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from assistant import BriefError
from evaluate_rag_challenge import make_bundle
from evaluate_rag_staged import evaluate
from ingest import ingest
from local_rag_staged import run


class StagedRagTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        make_bundle(root / 'bundle')
        self.db = root / 'db.sqlite'
        ingest(root / 'bundle', self.db)

    def provider(self, outputs, calls):
        pending = iter(outputs)
        def call(endpoint, payload):
            calls.append((endpoint, payload))
            if endpoint == '/api/embed':
                # Ensure the actual note is retrieved; unselected routine note stays outside budget.
                return {'embeddings': [[1, 0]] + [
                    [1, 0] if 'Receiving window:' in text else [0, 1]
                    for text in payload['input'][1:]]}
            value = next(pending)
            if isinstance(value, Exception):
                raise value
            return value
        return call

    def response(self, value):
        return dict(done=True, done_reason='stop', response=json.dumps(value))

    def invoke(self, outputs, diagnostics=None):
        calls = []
        result = run(self.db, 'C101', 'What receiving window is recorded?', 'e', 'g',
                     True, self.provider(outputs, calls), diagnostics)
        return result, calls

    def test_insufficient_skips_selection_and_returns_empty_findings(self):
        trace = {}
        result, calls = self.invoke([self.response({'decision': 'insufficient'})], trace)
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['generation_requests'], 1)
        self.assertEqual(len(calls), 2)  # embedding + decision, no selection
        self.assertFalse(trace['selection']['request_started'])
        self.assertFalse(result['live_execution'])

    def test_supported_selects_exact_source_from_identical_context(self):
        before = self.db.read_bytes()
        result, calls = self.invoke([self.response({'decision': 'supported'}),
                                    self.response({'evidence_ids': ['note:TARGET']})])
        self.assertEqual(result['findings'][0]['quote'],
            'SYNTHETIC: Receiving window: 2026-11-01 09:00-11:00 UTC. Cause of delay is unverified.\n')
        self.assertEqual(result['generation_requests'], 2)
        self.assertEqual(calls[1][1]['prompt'], calls[2][1]['prompt'])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertTrue(result['human_review_required'])
        self.assertFalse(result['action_executed'])
        self.assertFalse(result['live_execution'])
        allowed = calls[2][1]['format']['properties']['evidence_ids']['items']['enum']
        self.assertEqual(allowed, result['retrieval']['retrieved_ids'])
        self.assertNotIn('tools', calls[2][1])

    def test_missing_order_makes_no_provider_calls(self):
        provider = Mock()
        result = run(self.db, 'MISSING', 'Question?', 'e', 'g', True, provider)
        self.assertEqual(result['reason'], 'order_not_found')
        provider.assert_not_called()

    def test_explicit_opt_in_and_input_validation_before_calls(self):
        provider = Mock()
        with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
            run(self.db, 'C101', 'Question?', 'e', 'g', transport=provider)
        for question, model in [('', 'g'), ('x' * 1001, 'g'), ('Question?', None)]:
            with self.assertRaises(BriefError):
                run(self.db, 'C101', question, 'e', model, True, provider)
        provider.assert_not_called()

    def test_malformed_decision_rejected_without_selection(self):
        for decision in [{'decision': 'insufficient', 'evidence_ids': ['note:TARGET']},
                         {'decision': 'supported', 'action': 'update'},
                         {'decision': 'unknown'}, {'decision': True}, {}, []]:
            with self.subTest(decision=decision):
                trace = {}
                with self.assertRaisesRegex(BriefError, 'invalid_decision'):
                    self.invoke([self.response(decision)], trace)
                self.assertFalse(trace['selection']['request_started'])

    def test_invalid_selection_is_never_repaired(self):
        for selection in [{'evidence_ids': []}, {'evidence_ids': ['note:TARGET'] * 2},
                          {'evidence_ids': ['order:C102']}, {'evidence_ids': ['note:ROUTINE']},
                          {'evidence_ids': [False]}, {'evidence_ids': 'note:TARGET'},
                          {'evidence_ids': ['note:TARGET'], 'decision': 'insufficient'}]:
            with self.subTest(selection=selection), self.assertRaises(BriefError):
                self.invoke([self.response({'decision': 'supported'}), self.response(selection)])

    def test_incomplete_decision_does_not_call_selection(self):
        trace = {}
        with self.assertRaisesRegex(BriefError, 'local_generation_incomplete'):
            self.invoke([dict(done=True, done_reason='length', response='{}')], trace)
        self.assertFalse(trace['selection']['request_started'])

    def test_incomplete_selection_is_not_an_accepted_review(self):
        with self.assertRaisesRegex(BriefError, 'local_generation_incomplete'):
            self.invoke([self.response({'decision': 'supported'}), dict(done=False, response='{}')])

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(BriefError, 'duplicate_json_key'):
            self.invoke([dict(done=True, response='{"decision":"supported","decision":"insufficient"}')])

    def test_selection_provider_failure_retains_stage_and_no_retry(self):
        trace = {}
        with self.assertRaisesRegex(BriefError, 'local_provider_unavailable'):
            self.invoke([self.response({'decision': 'supported'}),
                         BriefError('local_provider_unavailable')], trace)
        self.assertTrue(trace['selection']['request_started'])
        self.assertFalse(trace['selection']['response_received'])
        self.assertEqual(trace['accepted_decision'], 'supported')

    def test_evaluator_does_not_reward_always_abstain_on_answerable_cases(self):
        calls = []
        provider = self.provider([self.response({'decision': 'insufficient'})] * 15, calls)
        report = evaluate('e', 'g', provider)
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(report['generation_requests'], 15)
        self.assertEqual([c['answerable_passed'] for c in report['cohorts']], [0, 0])
        self.assertEqual([c['model_abstention_passed'] for c in report['cohorts']], [4, 3])
        self.assertEqual([c['pre_inference_cases'] for c in report['cohorts']], [1, 0])
        self.assertEqual(report['human_review'], 'pending')

    def test_evaluator_retains_selection_failures_separately(self):
        def provider(endpoint, payload):
            if endpoint == '/api/embed':
                return {'embeddings': [[1, 0] for _ in payload['input']]}
            if 'decision' in payload['format']['properties']:
                return self.response({'decision': 'supported'})
            raise BriefError('local_provider_unavailable')
        report = evaluate('e', 'g', provider)
        self.assertEqual(report['generation_requests'], 30)
        failures = [r['result'] for r in report['cases'] if r['result']['status'] == 'failed']
        self.assertEqual(len(failures), 15)
        self.assertTrue(all(r['failure_stage'] == 'selection' for r in failures))
        self.assertTrue(report['database_unchanged'])
