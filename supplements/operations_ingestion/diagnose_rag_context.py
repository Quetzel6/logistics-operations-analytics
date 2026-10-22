"""Fixed-prompt decision-only ablation of three observed false abstentions."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform

from assistant import BriefError
from local_rag import post
from local_rag_staged import DECISION_PROMPT, DECISION_SCHEMA, PROMPT_SHA, generate

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'evidence/local_rag_staged_mac/report.json'
SOURCE_SHA = '74ea129d8f2f5abc459f906e4662fcaabdeaa1dbaecac05b045bc2095a7598a8'
FROZEN_PROMPT_SHA = '3793279128e0a58554613e214c15493563c2a700ec804f2ccecc748d23ccd8dc'
CASE_NAMES = ('receiving_window', 'quantity_with_cause_context', 'due_date_with_instruction')
REPETITIONS = 4


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_cases(path=SOURCE):
    raw = Path(path).read_bytes()
    if sha(raw) != SOURCE_SHA:
        raise ValueError('baseline_report_changed')
    report = json.loads(raw)
    if PROMPT_SHA != FROZEN_PROMPT_SHA or report['prompt_sha256'] != PROMPT_SHA:
        raise ValueError('prompt_changed')
    # All recorded runtime dependencies must still match the measured baseline.
    for name, expected in report['source_sha256'].items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise ValueError('baseline_source_changed:' + name)
    indexed = {case['case']: case for case in report['cases']}
    cases = []
    for name in CASE_NAMES:
        row = indexed[name]
        sources = {item['evidence_id']: item for item in row['candidate_evidence']}
        full = [sources[eid] for eid in row['diagnostics']['retrieved_ids']]
        keep = set(row['required_ids']) | {'order:' + row['order_id']}
        reduced = [item for item in full if item['evidence_id'] in keep]
        if not keep <= {item['evidence_id'] for item in reduced} or not len(reduced) < len(full):
            raise ValueError('invalid_reduced_context')
        cases.append(dict(case=name, question=row['question'],
                          contexts={'full': full, 'reduced': reduced}))
    return report, cases


def schedule(cases):
    """Each case has two full-first and two reduced-first pairs; no hidden retries."""
    for repetition in range(REPETITIONS):
        for case in cases:
            arms = ('full', 'reduced') if repetition % 2 == 0 else ('reduced', 'full')
            for arm in arms:
                yield repetition + 1, case, arm


def evaluate(model, allow_local=False, transport=None):
    if not allow_local:
        raise BriefError('local_inference_disabled')
    baseline, cases = load_cases()
    if model != baseline['generation_model']:
        raise ValueError('model_must_match_baseline')
    call = transport if transport is not None else post
    trials = []
    for repetition, case, arm in schedule(cases):
        records = case['contexts'][arm]
        trace = {'decision': dict(request_started=False, response_received=False, raw_generation=None)}
        try:
            result = generate(call, model, case['question'], records, 'decision',
                              DECISION_PROMPT, DECISION_SCHEMA, trace)
            if (not isinstance(result, dict) or set(result) != {'decision'} or
                    result['decision'] not in ('supported', 'insufficient')):
                raise BriefError('invalid_decision')
            outcome = result['decision']
            error = None
        except BriefError as exc:
            outcome, error = 'failed', str(exc)
        trials.append(dict(sequence=len(trials) + 1, repetition=repetition,
                           case=case['case'], arm=arm, outcome=outcome, error_code=error,
                           records_sha256=sha(json.dumps(records, ensure_ascii=False).encode()),
                           diagnostics=trace))
    summaries = []
    for case in cases:
        row = dict(case=case['case'], question=case['question'])
        for arm in ('full', 'reduced'):
            count = Counter(t['outcome'] for t in trials if t['case'] == case['case'] and t['arm'] == arm)
            row[arm] = {key: count[key] for key in ('supported', 'insufficient', 'failed')}
        summaries.append(row)
    return dict(protocol='decision-context-ablation-v1',
        scope='Oracle-assisted context reduction on three selected failures; not end-to-end evaluation',
        execution='live_local' if transport is None else 'mock_only',
        started_note='Trials run sequentially with alternating arm order; repeated observations are correlated',
        finished_utc=datetime.now(timezone.utc).isoformat(),
        generation_model=model, prompt_sha256=PROMPT_SHA, source_report_sha256=SOURCE_SHA,
        source_sha256={name: sha((ROOT / name).read_bytes()) for name in
                      ('diagnose_rag_context.py', 'local_rag_staged.py', 'local_rag.py')},
        python=platform.python_version(), platform=platform.system(),
        generation_requests=sum(t['diagnostics']['decision']['request_started'] for t in trials),
        embedding_requests=0, selection_requests=0, repetitions=REPETITIONS,
        human_review='pending', cases=cases, summaries=summaries, trials=trials)


def render(report):
    esc = lambda value: html.escape(json.dumps(value, indent=2, ensure_ascii=False))
    return ('<!doctype html><meta charset="utf-8"><title>Context sensitivity diagnostic</title>'
            '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px}</style>'
            '<h1>Context sensitivity diagnostic</h1><p>Selected-failure analysis only. '
            'Reduced context uses reference labels. This does not replace the 13/16 baseline.</p>'
            '<h2>Execution</h2><pre>' + esc(report['execution']) + '</pre>'
            '<h2>Decision counts by context</h2><pre>' + esc(report['summaries']) + '</pre>'
            '<h2>Exact input records</h2><pre>' + esc(report['cases']) + '</pre>'
            '<details><summary>All trials, including failures</summary><pre>' +
            esc(report['trials']) + '</pre></details>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--allow-local', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.allow_local:
        parser.error('--allow-local is required')
    # Validate source, prompt and model before creating output or calling a provider.
    baseline, _ = load_cases()
    if args.model != baseline['generation_model']:
        parser.error('--model must match the preserved baseline')
    args.output.mkdir(parents=True, exist_ok=False)
    report = evaluate(args.model, True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (args.output / 'report.html').write_text(render(report), encoding='utf-8')
    print(json.dumps(dict(execution=report['execution'], generation_requests=report['generation_requests'],
                         summaries=report['summaries']), indent=2))
    # Either valid decision is an observation, not a pass/fail quality score.
    return 1 if any(t['outcome'] == 'failed' for t in report['trials']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
