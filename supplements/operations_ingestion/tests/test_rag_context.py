import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from assistant import BriefError
from diagnose_rag_context import evaluate, load_cases, render, schedule
from local_rag_staged import DECISION_PROMPT


class ContextDiagnosticTests(unittest.TestCase):
    def test_reduction_preserves_exact_records_and_required_sources(self):
        baseline, cases = load_cases()
        old = {c['case']: c for c in baseline['cases']}
        self.assertEqual([(len(c['contexts']['full']), len(c['contexts']['reduced']))
                          for c in cases], [(6, 2), (6, 1), (2, 1)])
        for case in cases:
            with self.subTest(case=case['case']):
                full, reduced = case['contexts']['full'], case['contexts']['reduced']
                self.assertTrue(all(item in full for item in reduced))
                self.assertTrue(set(old[case['case']]['required_ids']) <=
                                {r['evidence_id'] for r in reduced})
                self.assertEqual(case['question'], old[case['case']]['question'])

    def test_schedule_is_balanced_and_keeps_all_planned_trials(self):
        _, cases = load_cases()
        trials = list(schedule(cases))
        self.assertEqual(len(trials), 24)
        for case in cases:
            selected = [t for t in trials if t[1]['case'] == case['case']]
            self.assertEqual([t[2] for t in selected[::2]], ['full', 'reduced', 'full', 'reduced'])
            self.assertEqual(sum(t[2] == 'full' for t in selected), 4)
            self.assertEqual(sum(t[2] == 'reduced' for t in selected), 4)

    def test_only_decision_calls_with_frozen_prompt_and_no_oracle_labels(self):
        requests = []
        def provider(endpoint, payload):
            self.assertEqual(endpoint, '/api/generate')
            self.assertEqual(payload['system'], DECISION_PROMPT)
            self.assertEqual(payload['options'], {'temperature': 0, 'num_predict': 1600})
            prompt = json.loads(payload['prompt'])
            self.assertEqual(set(prompt), {'question', 'records'})
            requests.append(payload)
            return dict(done=True, done_reason='stop', response='{"decision":"supported"}')
        report = evaluate('qwen2.5:3b', True, provider)
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(report['generation_requests'], 24)
        self.assertEqual(report['embedding_requests'], 0)
        self.assertEqual(report['selection_requests'], 0)
        self.assertNotIn('reference_checks_passed', report)
        self.assertEqual(report['human_review'], 'pending')
        self.assertTrue(all(r[a]['supported'] == 4 for r in report['summaries'] for a in ('full', 'reduced')))
        self.assertEqual(requests[0], requests[12])

    def test_provider_failures_retained_without_extra_retries(self):
        provider = Mock(side_effect=BriefError('local_provider_unavailable'))
        report = evaluate('qwen2.5:3b', True, provider)
        self.assertEqual(provider.call_count, 24)
        self.assertTrue(all(t['outcome'] == 'failed' for t in report['trials']))
        self.assertTrue(all(r[a]['failed'] == 4 for r in report['summaries'] for a in ('full', 'reduced')))

    def test_invalid_decision_remains_failure(self):
        provider = Mock(return_value=dict(done=True,
            response='{"decision":"insufficient","evidence_ids":[]}'))
        report = evaluate('qwen2.5:3b', True, provider)
        self.assertTrue(all(t['error_code'] == 'invalid_decision' for t in report['trials']))

    def test_missing_opt_in_wrong_model_and_tampered_source_rejected(self):
        provider = Mock()
        with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
            evaluate('qwen2.5:3b', transport=provider)
        with self.assertRaisesRegex(ValueError, 'model_must_match_baseline'):
            evaluate('other-model', True, provider)
        provider.assert_not_called()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'report.json'
            source.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'baseline_report_changed'):
                load_cases(source)

    def test_html_escapes_raw_response(self):
        report = evaluate('qwen2.5:3b', True, Mock(return_value=dict(done=True,
                          response='<script>unsafe</script>')))
        page = render(report)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
