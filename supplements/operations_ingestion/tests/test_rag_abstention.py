"""Synthetic HTTP fixtures; no Ollama execution or quality claims."""
import json
import unittest
from unittest.mock import patch

from assistant import BriefError
from diagnose_rag_abstention import execute
from diagnose_rag_context import load_cases
from diagnose_rag_format import execute as experiment, SHORT_DECISION_PROMPT
from inspect_rag_run import inspect
import test_rag_format as fixture_module


class AbstentionControlTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.FormatDiagnosticTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        f.no_format_baseline()
        f.generation['response'] = '{"decision":"supported"}'
        with patch('diagnose_rag_format.CapturedTransport', side_effect=f.factory):
            experiment(f.output, f.baseline, True, experiment='short-system')
        self.baseline = f.output
        self.output = f.root / 'controls'
        f.calls.clear()
        self.before = {p.name: p.read_bytes() for p in self.baseline.iterdir()}

    def invoke(self):
        return execute(self.output, self.baseline, True, self.fixture.factory)

    def test_always_supported_exposes_seven_false_supports(self):
        report = self.invoke()
        self.assertEqual(report['negative_controls'], dict(count=7, correct_insufficient=0, false_support=7, failed=0))
        self.assertEqual(report['positive_control'], dict(count=1, correct_supported=1, false_abstention=0, failed=0))
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(report['generation_requests'], 8)
        self.assertEqual([r['case'] for r in report['trials']], [
            'unconfirmed_cause', 'dispatch_only', 'missing_history', 'foreign_order',
            'cause_still_unknown', 'estimate_not_acceptance', 'missing_weight',
            'due_date_reduced_positive_control'])
        self.assertEqual(self.before, {p.name: p.read_bytes() for p in self.baseline.iterdir()})
        payloads = [p for e, p in self.fixture.calls if e == 'generate']
        self.assertEqual(len(payloads), 8)
        for payload in payloads:
            self.assertEqual(set(payload), {'model', 'system', 'prompt', 'options', 'stream'})
            self.assertEqual(payload['system'], SHORT_DECISION_PROMPT)
            self.assertEqual(payload['options'], {'temperature': 0, 'num_predict': 1600})
            self.assertEqual(set(json.loads(payload['prompt'])), {'question', 'records'})
        self.assertEqual(json.loads(payloads[-1]['prompt'])['records'], [dict(
            evidence_id='order:T204', kind='order', text='Order T204; due_date=2026-12-06; quantity=73.')])

    def test_always_insufficient_does_not_pass_positive_control(self):
        self.fixture.generation['response'] = '{"decision":"insufficient"}'
        report = self.invoke()
        self.assertEqual(report['negative_controls']['correct_insufficient'], 7)
        self.assertEqual(report['positive_control']['false_abstention'], 1)
        self.assertFalse(report['trials'][-1]['decision_matches_reference'])

    def test_parse_failures_preserved_without_retries_or_counting_as_abstention(self):
        self.fixture.generation['response'] = 'No evidence was provided.'
        report = self.invoke()
        self.assertEqual(report['negative_controls']['failed'], 7)
        self.assertEqual(report['negative_controls']['correct_insufficient'], 0)
        self.assertEqual(report['positive_control']['failed'], 1)
        self.assertEqual(sum(e == 'generate' for e, _ in self.fixture.calls), 8)
        self.assertEqual(inspect(self.output)['completed_observations'], 8)
        self.assertTrue(all(r['diagnostics']['decision']['raw_generation'] == 'No evidence was provided.' for r in report['trials']))

    def test_interrupt_keeps_first_completed_case(self):
        opened = self.fixture.opened
        generations = []
        def interrupted(request, timeout):
            if request.full_url.endswith('/generate'):
                generations.append(True)
                if len(generations) == 2:
                    raise KeyboardInterrupt()
            return opened(request, timeout)
        self.fixture.opened = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.invoke()
        recovered = inspect(self.output)
        self.assertEqual(recovered['state'], 'interrupted')
        self.assertEqual(recovered['completed_observations'], 1)
        self.assertEqual(len(generations), 2)

    def test_runtime_mismatch_and_missing_opt_in_do_not_generate(self):
        with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
            execute(self.output, self.baseline, transport_factory=self.fixture.factory)
        self.assertFalse(self.output.exists())
        self.fixture.version = 'changed'
        with self.assertRaisesRegex(ValueError, 'runtime_version_differs_from_baseline'):
            self.invoke()
        self.assertFalse(any(e == 'generate' for e, _ in self.fixture.calls))

    def test_existing_directory_rejected_before_calls(self):
        self.invoke()
        self.fixture.calls.clear()
        with self.assertRaises(FileExistsError):
            self.invoke()
        self.assertEqual(self.fixture.calls, [])

    def test_two_false_abstentions_use_exact_full_historical_contexts(self):
        original, _ = load_cases()
        indexed = {r['case']: r for r in original['cases']}
        report = execute(self.output, self.baseline, True, self.fixture.factory,
                         suite='false-abstentions')
        self.assertEqual(report['protocol'], 'short-system-false-abstentions-v1')
        self.assertEqual(report['generation_requests'], 2)
        self.assertEqual(report['positive_control']['correct_supported'], 2)
        self.assertEqual(report['negative_controls']['count'], 0)
        requests = [p for e, p in self.fixture.calls if e == 'generate']
        self.assertEqual(len(requests), 2)
        for payload, name in zip(requests, ('receiving_window', 'quantity_with_cause_context')):
            row = indexed[name]
            sources = {r['evidence_id']: r for r in row['candidate_evidence']}
            expected_records = [sources[eid] for eid in row['diagnostics']['retrieved_ids']]
            self.assertEqual(json.loads(payload['prompt']), {'question': row['question'], 'records': expected_records})
            self.assertEqual(len(expected_records), 6)
            self.assertEqual(payload['system'], SHORT_DECISION_PROMPT)
            self.assertEqual(set(payload), {'model', 'system', 'prompt', 'options', 'stream'})
            self.assertEqual(payload['options'], {'temperature': 0, 'num_predict': 1600})
        self.assertFalse(any(e == 'embed' for e, _ in self.fixture.calls))
        self.assertEqual(self.before, {p.name: p.read_bytes() for p in self.baseline.iterdir()})

    def test_false_abstentions_are_not_scored_as_successful_abstentions(self):
        self.fixture.generation['response'] = '{"decision":"insufficient"}'
        report = execute(self.output, self.baseline, True, self.fixture.factory,
                         suite='false-abstentions')
        self.assertEqual(report['positive_control']['false_abstention'], 2)
        self.assertEqual(report['positive_control']['correct_supported'], 0)
        self.assertTrue(all(not r['decision_matches_reference'] for r in report['trials']))

    def test_invalid_suite_stops_before_calls(self):
        with self.assertRaisesRegex(ValueError, 'invalid_suite'):
            execute(self.output, self.baseline, True, self.fixture.factory, suite='unknown')
        self.assertEqual(self.fixture.calls, [])
        self.assertFalse(self.output.exists())
