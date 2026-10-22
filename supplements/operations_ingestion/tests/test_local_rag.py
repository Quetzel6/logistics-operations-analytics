import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from assistant import BriefError
from ingest import ingest
from local_rag import checked_vectors, run

class LocalRagTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / 'demo.sqlite'
        ingest(Path(__file__).resolve().parents[1] / 'fixtures', self.db)

    def provider(self, endpoint, payload):
        if endpoint == '/api/embed':
            return {'embeddings': [[1.0, 0.5] for _ in payload['input']]}
        self.assertFalse(payload['stream'])
        self.assertNotIn('tools', payload)
        data = json.loads(payload['prompt'])
        self.assertTrue(all('O002' not in item['text'] for item in data['records']))
        item = data['records'][0]
        return {'done': True, 'done_reason': 'stop', 'response': json.dumps({
            'status': 'review_draft', 'findings': [{'evidence_id': item['evidence_id'], 'quote': item['text']}],
            'suggested_action': 'review_records'})}

    def call(self, **kwargs):
        return run(self.db, 'O001', 'Which exception was recorded?',
                   'test-embed', 'test-generator', **kwargs)

    def test_requires_explicit_opt_in_without_network(self):
        with patch('local_rag.post') as provider:
            with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
                self.call()
        provider.assert_not_called()

    def test_missing_order_abstains_without_model_call(self):
        provider = Mock()
        result = run(self.db, 'UNKNOWN', 'What happened?', 'e', 'g', True, provider)
        self.assertEqual(result['status'], 'abstained')
        provider.assert_not_called()

    def test_scoped_citations_read_only_and_mock_not_live(self):
        before = self.db.read_bytes()
        result = self.call(allow_local=True, transport=self.provider)
        self.assertEqual(result['status'], 'review_draft')
        self.assertFalse(result['live_execution'])
        self.assertFalse(result['action_executed'])
        self.assertTrue(result['human_review_required'])
        self.assertEqual(before, self.db.read_bytes())

    def test_malformed_embeddings_rejected(self):
        for vectors, count in [([], 1), ([[0, 0]], 1), ([[float('nan')]], 1),
                               ([[True]], 1), ([[1], [1, 2]], 2), ([[1]], 2)]:
            with self.subTest(vectors=vectors):
                with self.assertRaisesRegex(BriefError, 'invalid_embeddings'):
                    checked_vectors(vectors, count)

    def test_invalid_question_before_model_call(self):
        provider = Mock()
        with self.assertRaisesRegex(BriefError, 'invalid_question'):
            run(self.db, 'O001', ' ', 'e', 'g', True, provider)
        provider.assert_not_called()

    def test_foreign_citation_rejected(self):
        def provider(endpoint, payload):
            if endpoint == '/api/embed':
                return self.provider(endpoint, payload)
            return {'done': True, 'response': json.dumps({
                'status': 'review_draft', 'findings': [{'evidence_id': 'order:O002', 'quote': 'foreign'}],
                'suggested_action': 'review_records'})}
        with self.assertRaisesRegex(BriefError, 'invalid_citation'):
            self.call(allow_local=True, transport=provider)

    def test_incomplete_generation_rejected(self):
        def provider(endpoint, payload):
            return self.provider(endpoint, payload) if endpoint == '/api/embed' else {
                'done': True, 'done_reason': 'length', 'response': '{}'}
        with self.assertRaisesRegex(BriefError, 'local_generation_incomplete'):
            self.call(allow_local=True, transport=provider)

    def test_insufficient_evidence_can_abstain(self):
        def provider(endpoint, payload):
            if endpoint == '/api/embed':
                return self.provider(endpoint, payload)
            return {'done': True, 'response': json.dumps({
                'status': 'abstained', 'findings': [], 'suggested_action': 'review_records'})}
        result = self.call(allow_local=True, transport=provider)
        self.assertEqual(result['status'], 'abstained')
        self.assertFalse(result['live_execution'])

    def test_abstention_with_action_rejected(self):
        def provider(endpoint, payload):
            if endpoint == '/api/embed':
                return self.provider(endpoint, payload)
            return {'done': True, 'response': json.dumps({
                'status': 'abstained', 'findings': [], 'suggested_action': 'confirm_receiving_window'})}
        with self.assertRaisesRegex(BriefError, 'invalid_abstention'):
            self.call(allow_local=True, transport=provider)

    def test_diagnostics_capture_rejected_output_without_relaxing_validator(self):
        diagnostics = {}
        def provider(endpoint, payload):
            if endpoint == '/api/embed':
                return self.provider(endpoint, payload)
            return {'done': True, 'response': json.dumps({
                'status': 'abstained', 'findings': [{'evidence_id': 'event:E002', 'quote': 'x'}],
                'suggested_action': 'confirm_receiving_window'})}
        with self.assertRaisesRegex(BriefError, 'invalid_abstention'):
            self.call(allow_local=True, transport=provider, diagnostics=diagnostics)
        self.assertTrue(diagnostics['generation_response_received'])
        self.assertEqual(diagnostics['abstention_violations'],
                         ['findings_must_be_empty', 'action_must_be_review_records'])
        self.assertEqual(json.loads(diagnostics['raw_generation'])['status'], 'abstained')

    def test_unknown_order_diagnostics_confirm_no_generation(self):
        diagnostics = {}
        result = run(self.db, 'UNKNOWN', 'What happened?', 'e', 'g', True,
                     transport=Mock(), diagnostics=diagnostics)
        self.assertEqual(result['status'], 'abstained')
        self.assertFalse(diagnostics['embedding_request_started'])
        self.assertFalse(diagnostics['generation_response_received'])

    def test_prompt_has_one_owner_of_abstention_decision(self):
        from local_rag import LOCAL_PROMPT, LOCAL_SCHEMA
        self.assertNotIn('application separately computes', LOCAL_PROMPT)
        self.assertIn('An abstention MUST have zero findings', LOCAL_PROMPT)
        self.assertEqual(list(LOCAL_SCHEMA['properties'])[0], 'status')
        self.assertEqual(LOCAL_SCHEMA['properties']['findings']['maxItems'], 6)
