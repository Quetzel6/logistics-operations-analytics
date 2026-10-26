import json
import unittest
from unittest.mock import Mock

from assistant import BriefError
from rag_context_runtime import new_trace, rank_context, review_context


class ContextRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.record = dict(evidence_id='o-X', kind='order', text='complete text\n')
        self.ctx = dict(found=True, order_id='X', warnings=[], record_status='no_events', evidence=[self.record])

    def response(self, value):
        return dict(done=True, done_reason='stop', response=json.dumps(value))

    def test_supported_selection_uses_same_context_and_original_exact_text(self):
        call = Mock(side_effect=[self.response({'decision': 'supported'}), self.response({'evidence_ids': ['o-X']})])
        trace = new_trace()
        result = review_context(self.ctx, 'What is the recorded quantity?', [self.record], 'm', call, trace, True)
        first, second = [c.args[1] for c in call.call_args_list]
        self.assertNotIn('format', first)
        self.assertIn('format', second)
        self.assertEqual(first['prompt'], second['prompt'])
        self.assertEqual(second['format']['properties']['evidence_ids']['items']['enum'], ['o-X'])
        self.assertEqual(result['findings'], [dict(evidence_id='o-X', quote='complete text\n')])
        self.assertTrue(result['human_review_required'])
        self.assertFalse(result['action_executed'])

    def test_insufficient_is_not_overridden_for_structured_question(self):
        call = Mock(return_value=self.response({'decision': 'insufficient'}))
        trace = new_trace()
        result = review_context(self.ctx, 'What is the recorded quantity?', [self.record], 'm', call, trace, True)
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(call.call_count, 1)
        self.assertFalse(trace['selection']['request_started'])

    def test_foreign_duplicate_and_malformed_selection_fail_validation(self):
        for ids in [['foreign'], ['o-X', 'o-X'], []]:
            call = Mock(side_effect=[self.response({'decision': 'supported'}), self.response({'evidence_ids': ids})])
            trace = new_trace()
            with self.assertRaises(BriefError):
                review_context(self.ctx, 'Question?', [self.record], 'm', call, trace, True)
            self.assertEqual(trace['failure_stage'], 'validation')

    def test_incomplete_duplicate_keys_and_altered_context_are_rejected(self):
        for response in [dict(done=False, response='{}'),
                         dict(done=True, response='{"decision":"supported","decision":"insufficient"}')]:
            with self.assertRaises(BriefError):
                review_context(self.ctx, 'Question?', [self.record], 'm', Mock(return_value=response), new_trace(), True)
        provider = Mock()
        with self.assertRaisesRegex(BriefError, 'invalid_selected_context'):
            review_context(self.ctx, 'Question?', [dict(self.record, text='altered')], 'm', provider, new_trace(), True)
        provider.assert_not_called()

    def test_opt_in_unknown_order_and_embedding_prefixes(self):
        call = Mock()
        with self.assertRaisesRegex(BriefError, 'local_inference_disabled'):
            rank_context(self.ctx, 'Question?', 'e', call)
        unknown = dict(self.ctx, found=False, evidence=[])
        self.assertEqual(rank_context(unknown, 'Question?', 'e', call, True)['ranked_ids'], [])
        result = review_context(unknown, 'Question?', [], 'm', call, new_trace(), True)
        self.assertEqual(result['reason'], 'order_not_found')
        call.assert_not_called()
        call.return_value = {'embeddings': [[1, 0], [1, 0]]}
        ranking = rank_context(self.ctx, 'Question?', 'nomic-embed-text:v1.5', call, True)
        self.assertEqual(call.call_args.args[1]['input'], ['search_query: Question?', 'search_document: complete text\n'])
        self.assertEqual(ranking['scores'], [dict(evidence_id='o-X', cosine=1.0)])
