"""Label-free runtime pieces for a paired, short-prompt context experiment."""
import time

from assistant import BriefError
from local_rag import checked_vectors, cosine
from local_rag_ids import materialize
from local_rag_staged import DECISION_SCHEMA, SELECTION_PROMPT, generate
from rag_short_contract import SHORT_DECISION_PROMPT


def new_trace():
    return dict(generation_request_started=False, retrieved_ids=[],
                decision=dict(request_started=False, response_received=False, raw_generation=None),
                selection=dict(request_started=False, response_received=False, raw_generation=None))


def rank_context(ctx, question, embedding_model, call, allow_local=False):
    if not allow_local:
        raise BriefError('local_inference_disabled')
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
        raise BriefError('invalid_question')
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise BriefError('model_required')
    if not ctx['found']:
        return dict(ranked_ids=[], scores=[])
    evidence = ctx['evidence']
    inputs = [question] + [r['text'] for r in evidence]
    if embedding_model.split(':')[0] == 'nomic-embed-text':
        inputs = ['search_query: ' + question] + ['search_document: ' + r['text'] for r in evidence]
    response = call('/api/embed', dict(model=embedding_model, truncate=False, input=inputs))
    vectors = checked_vectors(response.get('embeddings'), len(evidence) + 1)
    scores = sorted([dict(evidence_id=r['evidence_id'], cosine=cosine(vectors[0], v))
                     for r, v in zip(evidence, vectors[1:])],
                    key=lambda r: (-r['cosine'], r['evidence_id']))
    return dict(ranked_ids=[r['evidence_id'] for r in scores], scores=scores)


def review_context(ctx, question, records, model, call, trace, allow_local=False):
    if not allow_local:
        raise BriefError('local_inference_disabled')
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
        raise BriefError('invalid_question')
    if not isinstance(model, str) or not model.strip():
        raise BriefError('model_required')
    base = dict(order_id=ctx['order_id'], human_review_required=True, action_executed=False,
                warnings=ctx['warnings'], record_status=ctx['record_status'])
    if not ctx['found']:
        trace.pop('failure_stage', None)
        return dict(base, status='abstained', reason='order_not_found', findings=[])
    trace['failure_stage'] = 'validation'
    if (not isinstance(records, list) or not 1 <= len(records) <= 6 or
            any(r not in ctx['evidence'] for r in records)):
        raise BriefError('invalid_selected_context')
    ids = [r['evidence_id'] for r in records]
    if len(set(ids)) != len(ids):
        raise BriefError('duplicate_citation')
    trace['retrieved_ids'] = ids
    started = time.monotonic()
    trace['failure_stage'] = 'decision'
    def without_format(endpoint, payload):
        payload = dict(payload)
        del payload['format']
        return call(endpoint, payload)
    decision = generate(without_format, model, question, records, 'decision',
                        SHORT_DECISION_PROMPT, DECISION_SCHEMA, trace)
    if not isinstance(decision, dict) or set(decision) != {'decision'} or decision['decision'] not in ('supported', 'insufficient'):
        raise BriefError('invalid_decision')
    trace['accepted_decision'] = decision['decision']
    if decision['decision'] == 'insufficient':
        selected = dict(status='abstained', findings=[], suggested_action='review_records')
    else:
        schema = dict(type='object', properties={'evidence_ids': dict(type='array',
            items=dict(type='string', enum=ids), minItems=1, maxItems=6, uniqueItems=True)},
            required=['evidence_ids'], additionalProperties=False)
        trace['failure_stage'] = 'selection'
        selection = generate(call, model, question, records, 'selection',
                             SELECTION_PROMPT, schema, trace)
        trace['failure_stage'] = 'validation'
        if not isinstance(selection, dict) or set(selection) != {'evidence_ids'}:
            raise BriefError('invalid_output_schema')
        selected = materialize(dict(status='review_draft', evidence_ids=selection['evidence_ids']), records)
    trace.pop('failure_stage', None)
    return dict(base, **selected, latency_ms=round((time.monotonic() - started) * 1000, 2),
                verification_scope='Validated source IDs and exact copied text; answerability/relevance/truth require human review.')
