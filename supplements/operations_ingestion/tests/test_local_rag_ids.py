import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from assistant import BriefError
from evaluate_rag_challenge import make_bundle
from evaluate_rag_ids import evaluate
from ingest import ingest
from local_rag_ids import materialize, run


class IdSelectionTests(unittest.TestCase):
    def test_exact_source_text_is_copied_including_whitespace(self):
        text = '  Quantity=137; date=2026-11-01.\nThai: จำนวน\n\n'
        evidence = [dict(evidence_id='note:A', text=text)]
        result = materialize(dict(status='review_draft', evidence_ids=['note:A']), evidence)
        self.assertEqual(result['findings'][0]['quote'], text)
        self.assertEqual(result['suggested_action'], 'review_records')

    def test_duplicate_ids_are_rejected_not_silently_deduplicated(self):
        with self.assertRaisesRegex(BriefError, 'duplicate_citation'):
            materialize(dict(status='review_draft', evidence_ids=['note:A', 'note:A']),
                        [dict(evidence_id='note:A', text='source')])

    def test_foreign_or_unretrieved_id_rejected(self):
        with self.assertRaisesRegex(BriefError, 'invalid_citation'):
            materialize(dict(status='review_draft', evidence_ids=['note:B']),
                        [dict(evidence_id='note:A', text='source')])

    def test_invalid_shapes_and_actions_rejected(self):
        for selection in [
            dict(status='review_draft', evidence_ids=[]),
            dict(status='abstained', evidence_ids=['note:A']),
            dict(status='review_draft', evidence_ids=[True]),
            dict(status='review_draft', evidence_ids=[{}]),
            dict(status='review_draft', evidence_ids='note:A'),
            dict(status='review_draft', evidence_ids=['note:A'], suggested_action='update'),
            dict(status='review_draft', evidence_ids=['note:A'], quote='modified'),
            dict(status='unknown', evidence_ids=[]),
            dict(status='review_draft', evidence_ids=[str(i) for i in range(7)]),
        ]:
            with self.subTest(selection=selection), self.assertRaises(BriefError):
                materialize(selection, [dict(evidence_id='note:A', text='source')])

    def test_valid_abstention_has_no_findings(self):
        result = materialize(dict(status='abstained', evidence_ids=[]), [])
        self.assertEqual(result['findings'], [])

    def test_transport_selection_read_only_and_not_live(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root / 'bundle')
            db = root / 'db.sqlite'
            ingest(root / 'bundle', db)
            before = db.read_bytes()
            def provider(endpoint, payload):
                if endpoint == '/api/embed':
                    return {'embeddings': [[1, 0] for _ in payload['input']]}
                self.assertEqual(set(payload['format']['properties']), {'status', 'evidence_ids'})
                self.assertNotIn('tools', payload)
                return {'done': True, 'done_reason': 'stop', 'response': json.dumps(
                    dict(status='review_draft', evidence_ids=['order:C101']))}
            result = run(db, 'C101', 'Quantity?', 'e', 'g', True, transport=provider)
            self.assertEqual(result['findings'][0]['quote'],
                             'Order C101; due_date=2026-11-01; quantity=137.')
            self.assertEqual(db.read_bytes(), before)
            self.assertFalse(result['live_execution'])
            self.assertFalse(result['action_executed'])
            self.assertTrue(result['human_review_required'])
            self.assertEqual(len(result['retrieval']['retrieved_ids']), 6)

    def test_opt_in_and_missing_order_do_not_call_provider(self):
        provider = Mock()
        with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
            run('missing.sqlite', 'UNKNOWN', 'Question?', 'e', 'g', transport=provider)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root / 'bundle')
            db = root / 'db.sqlite'
            ingest(root / 'bundle', db)
            result = run(db, 'C999', 'Question?', 'e', 'g', True, transport=provider)
            self.assertEqual(result['reason'], 'order_not_found')
        provider.assert_not_called()

    def test_regression_runner_keeps_model_failures(self):
        def provider(*args):
            raise BriefError('local_provider_unavailable')
        report = evaluate('e', 'g', transport=provider)
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(report['reference_checks_passed'], 1)
        self.assertEqual(sum(r['result']['status'] == 'failed' for r in report['cases']), 7)
        self.assertEqual(report['human_review'], 'pending')
        self.assertEqual(report['fixture_fingerprint'],
                         'b6612b089206cbb4a65edd4d8b50423ed187c3dc2d1ecc7f6e8dd992f2113764')
