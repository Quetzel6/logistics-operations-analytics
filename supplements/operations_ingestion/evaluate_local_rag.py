"""Run three authored live smoke cases; retain failures, require human review."""
import argparse
import json
import platform
from local_rag import run
from assistant import BriefError

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--database', required=True)
p.add_argument('--embedding-model', required=True)
p.add_argument('--model', required=True)
p.add_argument('--allow-local', action='store_true')
p.add_argument('--diagnostics-synthetic', action='store_true',
               help='Explicitly permit raw model output in this report; synthetic fixtures only')
a = p.parse_args()
cases = [
    ('exception', 'O001', 'Which exception was recorded for this order?', 'review_draft'),
    ('unknown_order', 'UNKNOWN', 'Which exception was recorded?', 'abstained'),
    ('unverified_cause', 'O001', 'What was the confirmed root cause of the exception?', 'abstained'),
]
results = []
for name, order, question, expected in cases:
    diagnostics = {} if a.diagnostics_synthetic else None
    try:
        result = run(a.database, order, question, a.embedding_model, a.model, a.allow_local, diagnostics=diagnostics)
    except BriefError as exc:
        result = {'status': 'failed', 'error_code': str(exc)}
    results.append({'case': name, 'question': question, 'expected_status': expected,
                    'status_matches': result['status'] == expected, 'result': result,
                    **({'diagnostics': diagnostics} if diagnostics is not None else {})})
print(json.dumps({'scope': 'Three authored smoke cases, not independent model-quality evaluation',
                  'embedding_model': a.embedding_model, 'generation_model': a.model,
                  'diagnostic_scope': 'Raw model output explicitly enabled for synthetic data' if a.diagnostics_synthetic else 'Raw output disabled',
                  'python': platform.python_version(), 'platform': platform.system(),
                  'human_review': 'pending', 'cases': results}, indent=2))
raise SystemExit(0 if all(c['status_matches'] for c in results) else 1)
