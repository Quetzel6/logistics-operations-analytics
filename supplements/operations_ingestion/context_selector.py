"""field-aware-context-v1: narrow schema routing, never an answerability rule."""
from assistant import BriefError

POLICY = 'field-aware-context-v1'
# Public query grammar, frozen before live measurement. No case IDs or values.
QUESTION_FIELDS = {
    'what quantity is recorded for this order': 'quantity',
    'what due date is recorded for this order': 'due_date',
    'what is the recorded quantity': 'quantity',
    'what is the recorded due date': 'due_date',
    'how many units are recorded for this order': 'quantity',
}


def _validate(candidates, ranked_ids):
    if not isinstance(candidates, list) or not isinstance(ranked_ids, list):
        raise BriefError('invalid_candidate_ranking')
    if any(not isinstance(r, dict) or not isinstance(r.get('evidence_id'), str)
           or not isinstance(r.get('text'), str) or not isinstance(r.get('kind'), str)
           for r in candidates):
        raise BriefError('invalid_candidates')
    ids = [r['evidence_id'] for r in candidates]
    if (any(not isinstance(eid, str) for eid in ranked_ids) or len(set(ids)) != len(ids)
            or len(ranked_ids) != len(ids) or set(ranked_ids) != set(ids)):
        raise BriefError('invalid_candidate_ranking')


def baseline_context(candidates, ranked_ids):
    _validate(candidates, ranked_ids)
    sources = {r['evidence_id']: r for r in candidates}
    chosen = [r for r in candidates if r['kind'] == 'order'][:1]
    for eid in ranked_ids:
        if sources[eid] not in chosen and len(chosen) < 6:
            chosen.append(sources[eid])
    return dict(records=chosen, route='fallback', rationale='pinned_order_cosine_top_six',
                policy='original-top-six')


def select_context(question, candidates, ranked_ids):
    fallback = baseline_context(candidates, ranked_ids)
    if not isinstance(question, str):
        raise BriefError('invalid_question')
    normalized = question.strip().casefold()
    if normalized.endswith('?'):
        normalized = normalized[:-1].rstrip()
    field = QUESTION_FIELDS.get(normalized)
    orders = [r for r in candidates if r['kind'] == 'order']
    if field is not None and len(orders) == 1:
        return dict(records=orders, route=field, rationale='single_current_order_schema_field',
                    policy=POLICY)
    return dict(fallback, policy=POLICY)
