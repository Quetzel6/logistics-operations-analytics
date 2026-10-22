"""Read preserved evidence; no network or model calls. Writes only this audit directory."""
import collections
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='pr5-audit-'))
OUT.mkdir(parents=True, exist_ok=True)
SRC = ROOT / 'supplements/operations_ingestion'
sys.path.insert(0, str(SRC))
import diagnose_rag_context as diagnostic
import evaluate_rag_staged as staged_eval
from evaluate_rag_challenge import CASES, make_bundle, score
from evaluate_rag_ids_v2 import NEW_CASES, make_new_bundle
from assistant import context
from ingest import ingest
from local_rag_staged import DECISION_PROMPT, DECISION_SCHEMA, generate

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

baseline, cases = diagnostic.load_cases()
reports = {}
raw_hashes = {}
for p in sorted((SRC / 'evidence').glob('*/report.json')):
    raw_hashes[str(p.relative_to(ROOT))] = sha(p)
    d = json.loads(p.read_bytes())
    mismatches = [name for name, expected in d.get('source_sha256', {}).items()
                  if sha(SRC / name) != expected]
    reports[p.parent.name] = {'sha256': sha(p), 'source_hash_mismatches': mismatches}
    assert not mismatches, (p, mismatches)

for row in baseline['cases']:
    case = (row['case'], row['order_id'], row['question'], row['expected_status'], row['required_ids'])
    assert score(case, row['result'], row['diagnostics'],
                 [e['evidence_id'] for e in row['candidate_evidence']]) == row['checks']
    trace = row['diagnostics']
    if trace['decision']['request_started']:
        assert json.loads(trace['decision']['raw_generation'])['decision'] == trace['accepted_decision']
        assert trace['selection']['request_started'] == (trace['accepted_decision'] == 'supported')
    if row['result']['status'] == 'review_draft':
        sources = {e['evidence_id']: e['text'] for e in row['candidate_evidence']}
        assert all(f['quote'] == sources[f['evidence_id']] for f in row['result']['findings'])
assert sum(r['checks']['reference_checks_passed'] for r in baseline['cases']) == 13
assert sum(r['diagnostics'][stage]['request_started'] for r in baseline['cases']
           for stage in ('decision', 'selection')) == 20

# Independently rebuild source bundles in temporary SQLite, compare every candidate and fingerprint.
for cohort, fixtures, builder in [('regression', CASES, make_bundle),
                                   ('prior_new_cases', NEW_CASES, make_new_bundle)]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        builder(root / 'bundle')
        ingestion = ingest(root / 'bundle', root / 'db.sqlite')
        recorded = next(c for c in baseline['cohorts'] if c['cohort'] == cohort)
        assert ingestion['fingerprint'] == recorded['fixture_fingerprint']
        for name, oid, question, expected, required in fixtures:
            row = next(r for r in baseline['cases'] if r['case'] == name)
            assert context(root / 'db.sqlite', oid)['evidence'] == row['candidate_evidence']
            assert (question, expected, required) == (row['question'], row['expected_status'], row['required_ids'])

d = json.loads((SRC / 'evidence/local_rag_context_mac/report.json').read_bytes())
assert d['cases'] == cases
schedule = list(diagnostic.schedule(cases))
assert len(d['trials']) == len(schedule) == 24
requests = []
for trial, (repetition, case, arm) in zip(d['trials'], schedule):
    assert (trial['sequence'], trial['repetition'], trial['case'], trial['arm']) == (len(requests)+1, repetition, case['case'], arm)
    records = case['contexts'][arm]
    assert trial['records_sha256'] == hashlib.sha256(json.dumps(records, ensure_ascii=False).encode()).hexdigest()
    assert json.loads(trial['diagnostics']['decision']['raw_generation'])['decision'] == trial['outcome']
    def capture(endpoint, payload):
        requests.append({'sequence': trial['sequence'], 'case': case['case'], 'arm': arm,
                         'classification': 'reconstructed_from_code_not_historical_wire_capture',
                         'endpoint': endpoint, 'payload': payload})
        return {'done': True, 'done_reason': 'stop', 'response': trial['diagnostics']['decision']['raw_generation']}
    generate(capture, d['generation_model'], case['question'], records, 'decision',
             DECISION_PROMPT, DECISION_SCHEMA, {'decision': {}})
for summary in d['summaries']:
    for arm in ('full', 'reduced'):
        counts = collections.Counter(t['outcome'] for t in d['trials'] if t['case'] == summary['case'] and t['arm'] == arm)
        assert summary[arm] == {k: counts[k] for k in ('supported', 'insufficient', 'failed')}

# Reproduce lost completed observations on interruption without calling transport or a model.
with tempfile.TemporaryDirectory() as td:
    destination = Path(td) / 'interrupted'
    def interrupted(*args):
        completed_observation = {'raw_generation': '{"decision":"supported"}'}
        raise KeyboardInterrupt()
    with patch.object(sys, 'argv', ['evaluate_rag_staged.py', '--embedding-model', 'mock',
                                  '--model', 'mock', '--allow-local', '--output', str(destination)]), patch.object(staged_eval, 'evaluate', interrupted):
        try:
            staged_eval.main()
        except KeyboardInterrupt:
            pass
    assert destination.is_dir() and not list(destination.iterdir())

with tempfile.TemporaryDirectory() as td:
    destination = Path(td) / 'interrupted-diagnostic'
    completions = []
    def finish_one_then_interrupt(*args):
        if completions:
            raise KeyboardInterrupt()
        completions.append({'decision': 'supported'})
        return completions[0]
    with patch.object(sys, 'argv', ['diagnose_rag_context.py', '--model', 'qwen2.5:3b',
                                  '--allow-local', '--output', str(destination)]), patch.object(diagnostic, 'generate', finish_one_then_interrupt):
        try:
            diagnostic.main()
        except KeyboardInterrupt:
            pass
    assert len(completions) == 1 and destination.is_dir() and not list(destination.iterdir())

(OUT / 'reconstructed_requests.json').write_text(json.dumps(requests, indent=2, ensure_ascii=False)+'\n')
(OUT / 'raw_report_hashes.json').write_text(json.dumps(raw_hashes, indent=2)+'\n')
(OUT / 'verification.json').write_text(json.dumps({
    'target_commit': '35468f2d34d17363f5b1476dd030318052010a45',
    'reports': reports, 'baseline_rescored': '13/16; 20 generation attempts',
    'fixtures_and_fingerprints_match': True, 'diagnostic_trials_verified': 24,
    'payload_classification': 'reconstructed, not historical HTTP capture',
    'interruption_leaves_empty_output_directory_reproduced': True,
    'live_model_calls': 0}, indent=2)+'\n')
print('PASS: hashes, fixtures, scores, routing, copied quotes, 24 diagnostic trials; interruption reproduction; zero live calls')

print('Derived audit outputs:', OUT)
