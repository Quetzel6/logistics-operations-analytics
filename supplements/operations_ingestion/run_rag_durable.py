"""Versioned synthetic runner; preserves frozen evaluators and all old reports."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import signal
import tempfile

from assistant import BriefError, context
from diagnose_rag_context import load_cases, schedule
from durable_rag import CapturedTransport, EvidenceRun, atomic_json
from evaluate_rag_challenge import CASES, digest, make_bundle, score
from evaluate_rag_ids_v2 import NEW_CASES, make_new_bundle
from local_rag_staged import DECISION_PROMPT, DECISION_SCHEMA, PROMPT_SHA, generate, run
from ingest import ingest

ROOT = Path(__file__).resolve().parent


def staged(model, embedding_model, call, journal):
    rows, cohorts = [], []
    for cohort, cases, builder in [('regression', CASES, make_bundle),
                                   ('prior_new_cases', NEW_CASES, make_new_bundle)]:
        with tempfile.TemporaryDirectory(prefix='durable-rag-') as td:
            root = Path(td)
            builder(root / 'bundle')
            db = root / 'db.sqlite'
            ingestion = ingest(root / 'bundle', db)
            if ingestion['status'] != 'committed':
                raise ValueError('fixture_ingestion_failed')
            before = digest(db)
            group = []
            for case in cases:
                name, oid, question, expected, required = case
                journal.scope = dict(cohort=cohort, case=name)
                ctx, trace = context(db, oid), {}
                journal.event('case_started', question=question, candidate_evidence=ctx['evidence'])
                try:
                    result = run(db, oid, question, embedding_model, model, True,
                                 transport=call, diagnostics=trace)
                except BriefError as error:
                    result = dict(status='failed', error_code=str(error), failure_stage=(
                        'selection' if trace.get('selection', {}).get('request_started') else
                        'decision' if trace.get('decision', {}).get('request_started') else 'retrieval'))
                # Dependency injection makes frozen run() label live_execution False.
                # Only this runner knows whether call is the actual captured HTTP client.
                result['live_execution'] = journal.state['execution'] == 'live_local' and bool(
                    trace.get('generation_request_started'))
                row = dict(case=name, cohort=cohort, order_id=oid, question=question,
                           expected_status=expected, required_ids=required,
                           candidate_count=len(ctx['evidence']), candidate_evidence=ctx['evidence'],
                           checks=score(case, result, trace, [e['evidence_id'] for e in ctx['evidence']]),
                           result=result, diagnostics=trace)
                journal.observation(row)
                group.append(row)
            cohorts.append(dict(cohort=cohort, fixture_fingerprint=ingestion['fingerprint'],
                                database_unchanged=before == digest(db)))
            rows.extend(group)
    return dict(cases=rows, cohorts=cohorts, case_count=len(rows),
                reference_checks_passed=sum(r['checks']['reference_checks_passed'] for r in rows),
                generation_requests=sum(bool(r['diagnostics'][s]['request_started'])
                                        for r in rows for s in ('decision', 'selection')),
                answerable_passed=sum(r['checks']['reference_checks_passed'] for r in rows if r['required_ids']),
                answerable_count=sum(bool(r['required_ids']) for r in rows),
                model_abstention_passed=sum(r['checks']['reference_checks_passed'] for r in rows
                    if not r['required_ids'] and r['diagnostics']['generation_request_started']),
                model_abstention_count=sum(not r['required_ids'] and r['diagnostics']['generation_request_started'] for r in rows),
                application_gate_count=sum(not r['diagnostics']['generation_request_started'] for r in rows),
                database_unchanged=all(c['database_unchanged'] for c in cohorts))


def decisions(model, mode, call, journal):
    _, cases = load_cases()
    if mode == 'due-date':
        case = next(c for c in cases if c['case'] == 'due_date_with_instruction')
        trials = [(1, case, 'reduced')]
    else:
        trials = schedule(cases)
    rows = []
    for repetition, case, arm in trials:
        records = case['contexts'][arm]
        journal.scope = dict(case=case['case'], arm=arm, repetition=repetition)
        trace = {'decision': dict(request_started=False, response_received=False, raw_generation=None)}
        journal.event('trial_started', question=case['question'], records=records)
        try:
            result = generate(call, model, case['question'], records, 'decision',
                              DECISION_PROMPT, DECISION_SCHEMA, trace)
            if not isinstance(result, dict) or set(result) != {'decision'} or result['decision'] not in ('supported', 'insufficient'):
                raise BriefError('invalid_decision')
            outcome, error = result['decision'], None
        except BriefError as exc:
            outcome, error = 'failed', str(exc)
        row = dict(sequence=len(rows) + 1, repetition=repetition, case=case['case'], arm=arm,
                   outcome=outcome, error_code=error, diagnostics=trace,
                   records_sha256=hashlib.sha256(json.dumps(records, ensure_ascii=False).encode()).hexdigest())
        journal.observation(row)
        rows.append(row)
    return dict(trials=rows, outcomes=dict(Counter(r['outcome'] for r in rows)),
                generation_requests=len(rows), embedding_requests=0, selection_requests=0,
                scope='Reference-assisted decision-only diagnostic; no end-to-end quality claim')


def execute(directory, mode, model, embedding_model, transport=None):
    # Frozen source/prompt verification precedes output creation or any provider call.
    baseline, _ = load_cases()
    if model != baseline['generation_model']:
        raise ValueError('model_must_match_baseline')
    if mode not in ('staged', 'context', 'due-date'):
        raise ValueError('invalid_protocol')
    if mode == 'staged' and embedding_model != baseline['embedding_model']:
        raise ValueError('embedding_model_must_match_baseline')
    execution = 'live_local' if transport is None else 'mock_only'
    with EvidenceRun(directory, 'durable-' + mode + '-v1', execution,
                     {'staged': 16, 'context': 24, 'due-date': 1}[mode]) as journal:
        sources = {p.name: digest(p) for p in ROOT.glob('*.py')}
        journal.event('experiment_config', model=model, embedding_model=embedding_model,
                      prompt_sha256=PROMPT_SHA, source_sha256=sources,
                      baseline_report_sha256=digest(ROOT / 'evidence/local_rag_staged_mac/report.json'))
        if transport is None:
            call = CapturedTransport(journal)
            runtime = call.metadata([model, embedding_model] if mode == 'staged' else [model])
        else:
            # Mock tests never produce artifacts labeled as live HTTP evidence.
            def call(endpoint, payload):
                request_id = journal.event('mock_request', endpoint=endpoint, payload=payload)
                response = transport(endpoint, payload)
                journal.event('mock_response', request_id=request_id, response=response)
                return response
        report = staged(model, embedding_model, call, journal) if mode == 'staged' else decisions(model, mode, call, journal)
        report.update(protocol=journal.state['protocol'], execution=execution, human_review='pending',
                      prompt_sha256=PROMPT_SHA, source_sha256=sources,
                      generation_model=model, embedding_model=embedding_model if mode == 'staged' else None)
        if transport is None:
            # Runtime load state is observational, not an attestation of every default.
            atomic_json(journal.directory / 'runtime_after.json', call.request('/api/ps'))
            inventory_after = call.request('/api/tags')
            atomic_json(journal.directory / 'model_inventory_after.json', inventory_after)
            report['model_identity_unchanged'] = all(
                len(matches := [m for m in inventory_after.get('models', [])
                    if m.get('name') == name or m.get('model') == name]) == 1
                and matches[0].get('digest') == details['digest']
                for name, details in runtime['models'].items())
        atomic_json(journal.directory / 'report.json', report)
        journal.event('report_saved')
        if report.get('model_identity_unchanged') is False:
            raise BriefError('runtime_model_identity_changed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', choices=('staged', 'context', 'due-date'), default='due-date')
    parser.add_argument('--model', default='qwen2.5:3b')
    parser.add_argument('--embedding-model', default='nomic-embed-text:v1.5')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-local', action='store_true')
    args = parser.parse_args()
    if not args.allow_local:
        parser.error('--allow-local is required; captures synthetic data only')
    previous = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        raise KeyboardInterrupt('SIGTERM')
    signal.signal(signal.SIGTERM, terminate)
    try:
        report = execute(args.output, args.protocol, args.model, args.embedding_model)
    except KeyboardInterrupt:
        return 130
    except (BriefError, ValueError, OSError) as error:
        print(json.dumps(dict(status='failed', error_type=type(error).__name__, error_code=str(error))))
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps(dict(protocol=report['protocol'], execution=report['execution'],
                          generation_requests=report['generation_requests'], output=str(args.output))))
    if args.protocol == 'staged':
        return 0 if report['database_unchanged'] and report['reference_checks_passed'] == report['case_count'] else 1
    return 1 if report['outcomes'].get('failed') else 0


if __name__ == '__main__':
    raise SystemExit(main())
