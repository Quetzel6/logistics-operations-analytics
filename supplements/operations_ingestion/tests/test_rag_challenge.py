import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assistant import BriefError, context
from evaluate_rag_challenge import CASES, evaluate, make_bundle, render, score
from ingest import ingest
from local_rag import run


class RagChallengeTests(unittest.TestCase):
    def test_status_alone_does_not_pass_reference_check(self):
        result = {'status': 'review_draft', 'findings': [{'evidence_id': 'order:C101'}]}
        checks = score(CASES[0], result, {'retrieved_ids': ['note:TARGET']}, ['note:TARGET'])
        self.assertTrue(checks['status_matches'])
        self.assertEqual(checks['retrieval_reference_recall'], 1)
        self.assertFalse(checks['reference_checks_passed'])

    def test_fixture_exceeds_retrieval_budget_and_has_valid_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root / 'bundle')
            db = root / 'db.sqlite'
            self.assertEqual(ingest(root / 'bundle', db)['status'], 'committed')
            self.assertEqual(len(context(db, 'C101')['evidence']), 11)
            for _, oid, _, _, required in CASES:
                self.assertTrue(set(required) <= {e['evidence_id'] for e in context(db, oid)['evidence']})

    def test_ranked_selection_excludes_low_ranked_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_bundle(root / 'bundle')
            db = root / 'db.sqlite'
            ingest(root / 'bundle', db)
            def provider(endpoint, payload):
                if endpoint == '/api/embed':
                    vectors = [[1, 0]]
                    for text in payload['input'][1:]:
                        vectors.append([1, 0] if 'Receiving window:' in text else [0, 1])
                    return {'embeddings': vectors}
                records = json.loads(payload['prompt'])['records']
                self.assertEqual(len(records), 6)
                self.assertEqual(records[0]['evidence_id'], 'order:C101')
                self.assertEqual(records[1]['evidence_id'], 'note:TARGET')
                # A genuine source outside the retrieved set must still be rejected.
                excluded = next(e for e in context(db, 'C101')['evidence'] if e not in records)
                return {'done': True, 'response': json.dumps(dict(status='review_draft',
                    findings=[dict(evidence_id=excluded['evidence_id'], quote=excluded['text'])],
                    suggested_action='review_records'))}
            with self.assertRaisesRegex(BriefError, 'invalid_citation'):
                run(db, 'C101', 'Receiving window?', 'e', 'g', True, transport=provider)

    def test_failures_retained_and_mock_not_reported_as_live(self):
        def unavailable(*args):
            raise BriefError('local_provider_unavailable')
        report = evaluate('e', 'g', transport=unavailable)
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(len(report['cases']), 8)
        self.assertEqual(sum(r['result']['status'] == 'failed' for r in report['cases']), 7)
        self.assertTrue(report['database_unchanged'])
        self.assertEqual(report['human_review'], 'pending')
        self.assertEqual(report['reference_checks_passed'], 1)

    def test_prompt_change_rejected_before_inference(self):
        with patch('evaluate_rag_challenge.LOCAL_PROMPT', 'changed'):
            with self.assertRaisesRegex(ValueError, 'prompt_changed'):
                evaluate('e', 'g')

    def test_report_escapes_untrusted_text(self):
        report = evaluate('e', 'g', transport=lambda *a: (_ for _ in ()).throw(BriefError('offline')))
        report['cases'][0]['question'] = '<script>alert(1)</script>'
        page = render(report)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
