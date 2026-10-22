import json
from pathlib import Path
import tempfile
import unittest

from assistant import BriefError, context
from evaluate_rag_ids_v2 import NEW_CASES, evaluate, make_new_bundle
from ingest import ingest
from local_rag_ids_v2 import materialize


class IdV2EvaluationTests(unittest.TestCase):
    def test_new_references_exist_and_include_retrieval_pressure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_new_bundle(root / 'bundle')
            db = root / 'db.sqlite'
            self.assertEqual(ingest(root / 'bundle', db)['status'], 'committed')
            self.assertEqual(len(context(db, 'T201')['evidence']), 11)
            for _, oid, _, _, required in NEW_CASES:
                self.assertTrue(set(required) <= {e['evidence_id'] for e in context(db, oid)['evidence']})
            self.assertEqual(sum(bool(case[4]) for case in NEW_CASES), 5)

    def test_always_abstain_does_not_pass_answerable_cases(self):
        def provider(endpoint, payload):
            if endpoint == '/api/embed':
                return {'embeddings': [[1, 0] for _ in payload['input']]}
            return {'done': True, 'done_reason': 'stop', 'response': json.dumps(
                dict(status='abstained', evidence_ids=[]))}
        report = evaluate('e', 'g', transport=provider)
        self.assertEqual(report['execution'], 'mock_only')
        self.assertEqual(report['case_count'], 16)
        self.assertEqual(report['generation_requests'], 15)
        self.assertTrue(report['database_unchanged'])
        self.assertEqual([c['reference_checks_passed'] for c in report['cohorts']], [5, 3])
        self.assertEqual([c['answerable_passed'] for c in report['cohorts']], [0, 0])
        self.assertEqual(report['human_review'], 'pending')

    def test_provider_failure_is_retained_in_both_cohorts(self):
        def provider(*args):
            raise BriefError('local_provider_unavailable')
        report = evaluate('e', 'g', transport=provider)
        self.assertEqual([c['reference_checks_passed'] for c in report['cohorts']], [1, 0])
        self.assertEqual(sum(r['result']['status'] == 'failed' for r in report['cases']), 15)

    def test_v2_retains_strict_id_validation_and_source_rendering(self):
        evidence = [dict(evidence_id='note:A', text='Original\ntext.\n')]
        result = materialize(dict(status='review_draft', evidence_ids=['note:A']), evidence)
        self.assertEqual(result['findings'][0]['quote'], evidence[0]['text'])
        for ids, status in [(['note:A', 'note:A'], 'review_draft'),
                            (['foreign'], 'review_draft'), (['note:A'], 'abstained')]:
            with self.subTest(ids=ids, status=status), self.assertRaises(BriefError):
                materialize(dict(status=status, evidence_ids=ids), evidence)
