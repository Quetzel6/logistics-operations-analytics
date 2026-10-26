"""Paired full-path development evaluation; selector never receives references."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import signal
import tempfile

from assistant import BriefError, context
from context_selector import POLICY, baseline_context, select_context
from diagnose_rag_context import load_cases
from diagnose_rag_format import check_runtime, load_capture
from durable_rag import CapturedTransport, EvidenceRun, atomic_json
from evaluate_rag_challenge import CASES, digest, make_bundle, score
from evaluate_rag_ids_v2 import NEW_CASES, make_new_bundle
from local_rag_staged import SELECTION_PROMPT
from rag_context_runtime import new_trace, rank_context, review_context
from rag_short_contract import SHORT_DECISION_PROMPT

ROOT = Path(__file__).resolve().parent


def summarize(rows):
    answerable = [r for r in rows if r['required_ids']]
    negatives = [r for r in rows if not r['required_ids'] and r['order_found']]
    gates = [r for r in rows if not r['order_found']]
    return dict(case_count=len(rows),
        reference_checks_passed=sum(r['checks']['reference_checks_passed'] for r in rows),
        answerable_count=len(answerable),
        answerable_reference_passed=sum(r['checks']['reference_checks_passed'] for r in answerable),
        answerable_decision_supported=sum(r['diagnostics'].get('accepted_decision') == 'supported' for r in answerable),
        false_abstentions=sum(r['diagnostics'].get('accepted_decision') == 'insufficient' for r in answerable),
        exact_required_ids_passed=sum(r['checks']['exact_required_ids'] for r in answerable),
        model_abstention_count=len(negatives),
        model_abstention_decision_requests=sum(r['diagnostics']['decision']['request_started'] for r in negatives),
        model_abstention_insufficient_decisions=sum(r['diagnostics'].get('accepted_decision') == 'insufficient' for r in negatives),
        model_abstention_reference_passed=sum(r['checks']['reference_checks_passed'] for r in negatives),
        false_support=sum(r['diagnostics'].get('accepted_decision') == 'supported' for r in negatives),
        application_gate_count=len(gates),
        application_gate_passed=sum(r['checks']['reference_checks_passed'] and
            not r['diagnostics']['generation_request_started'] for r in gates),
        failures_by_stage=dict(Counter(r['result']['failure_stage'] for r in rows if r['result']['status'] == 'failed')),
        errors=dict(Counter(r['result']['error_code'] for r in rows if r['result']['status'] == 'failed')),
        decision_requests=sum(r['diagnostics']['decision']['request_started'] for r in rows),
        selection_requests=sum(r['diagnostics']['selection']['request_started'] for r in rows),
        extra_selected_ids=sum(len(r['checks']['selected_extra_ids']) for r in rows),
        human_review='pending')


def evaluate(model, embedding_model, call, journal):
    rows, cohorts = [], []
    index = 0
    for cohort, cases, builder in [('regression', CASES, make_bundle),
                                   ('prior_new_cases', NEW_CASES, make_new_bundle)]:
        with tempfile.TemporaryDirectory(prefix='selector-pair-') as td:
            root = Path(td)
            builder(root / 'bundle')
            db = root / 'db.sqlite'
            ingestion = ingest_fixture(root / 'bundle', db)
            before = digest(db)
            for authored_case in cases:
                # References are not unpacked or consulted until both arm outputs exist.
                name, oid, question = authored_case[:3]
                ctx = context(db, oid)
                journal.scope = dict(cohort=cohort, case=name, arm='shared')
                journal.event('case_started', order_id=oid, question=question,
                              candidate_evidence=ctx['evidence'], order_found=ctx['found'])
                retrieval_error = None
                try:
                    ranking = rank_context(ctx, question, embedding_model, call, True)
                    journal.event('shared_ranking', **ranking)
                except BriefError as exc:
                    retrieval_error = str(exc)
                    ranking = dict(ranked_ids=[], scores=[])
                    journal.event('shared_retrieval_failed', error_code=retrieval_error)
                arm_order = ('B', 'C') if index % 2 == 0 else ('C', 'B')
                index += 1
                pair = []
                for arm in arm_order:
                    journal.scope = dict(cohort=cohort, case=name, arm=arm)
                    trace = new_trace()
                    selected = dict(records=[], route='not_selected', rationale='retrieval_failed')
                    if retrieval_error is not None:
                        result = dict(status='failed', error_code=retrieval_error, failure_stage='retrieval')
                    else:
                        try:
                            trace['failure_stage'] = 'context_selection'
                            selected = (baseline_context(ctx['evidence'], ranking['ranked_ids']) if arm == 'B'
                                        else select_context(question, ctx['evidence'], ranking['ranked_ids']))
                            trace['retrieved_ids'] = [r['evidence_id'] for r in selected['records']]
                            journal.event('context_selected', **selected)
                            result = review_context(ctx, question, selected['records'], model, call, trace, True)
                        except BriefError as exc:
                            result = dict(status='failed', error_code=str(exc),
                                          failure_stage=trace.get('failure_stage', 'context_selection'))
                    result['live_execution'] = journal.state['execution'] == 'live_local' and trace['generation_request_started']
                    row = dict(case=name, cohort=cohort, order_id=oid, question=question,
                               arm=arm, arm_order=list(arm_order), order_found=ctx['found'],
                               candidate_count=len(ctx['evidence']), candidate_evidence=ctx['evidence'],
                               context_selection=selected, ranking=ranking, diagnostics=trace, result=result)
                    journal.observation(row)  # Durable raw output before reference scoring.
                    pair.append(row)
                for row in pair:
                    row['expected_status'], row['required_ids'] = authored_case[3:]
                    checks = score(authored_case, row['result'], row['diagnostics'],
                                   [r['evidence_id'] for r in ctx['evidence']])
                    selected_ids = {r['evidence_id'] for r in row['result'].get('findings', [])}
                    checks['exact_required_ids'] = bool(row['required_ids']) and (
                        row['result'].get('status') == 'review_draft' and selected_ids == set(row['required_ids']))
                    row['checks'] = checks
                    journal.scope = dict(cohort=cohort, case=name, arm=row['arm'])
                    journal.event('case_scored', expected_status=row['expected_status'],
                                  required_ids=row['required_ids'], checks=checks)
                    rows.append(row)
            cohort_result = dict(cohort=cohort, fixture_fingerprint=ingestion['fingerprint'],
                                 database_unchanged=before == digest(db))
            journal.event('cohort_finished', **cohort_result)
            cohorts.append(cohort_result)
    return dict(cases=rows, cohorts=cohorts,
                arms={arm: summarize([r for r in rows if r['arm'] == arm]) for arm in ('B', 'C')},
                database_unchanged=all(c['database_unchanged'] for c in cohorts))


def ingest_fixture(bundle, db):
    from ingest import ingest
    result = ingest(bundle, db)
    if result['status'] != 'committed':
        raise ValueError('fixture_ingestion_failed')
    return result


def execute(directory, baseline_capture, allow_local=False, transport_factory=None,
            embedding_model='nomic-embed-text:v1.5'):
    if not allow_local:
        raise BriefError('local_inference_disabled')
    load_cases()  # Frozen historical-source checks; no historical contexts supplied to selector.
    baseline = load_capture(baseline_capture, 'abstention-controls')
    model = baseline['payload']['model']
    inventory = baseline['runtime']['inventory'].get('models', [])
    original_embeddings = [m for m in inventory if m.get('name') == embedding_model or m.get('model') == embedding_model]
    if len(original_embeddings) != 1 or not original_embeddings[0].get('digest'):
        raise ValueError('baseline_embedding_identity_unavailable')
    execution = 'live_local' if transport_factory is None else 'mock_only'
    with EvidenceRun(directory, 'paired-field-context-v1', execution, 32) as journal:
        sources = {p.name: digest(p) for p in ROOT.glob('*.py')}
        journal.event('experiment_config', baseline_file_sha256=baseline['file_sha256'],
                      selector_policy=POLICY, selector_sha256=digest(ROOT / 'context_selector.py'),
                      short_system_sha256=hashlib.sha256(SHORT_DECISION_PROMPT.encode()).hexdigest(),
                      selection_prompt_sha256=hashlib.sha256(SELECTION_PROMPT.encode()).hexdigest(),
                      source_sha256=sources, embedding_limit=15, decision_limit=30,
                      selection_limit=30, generation_limit=60,
                      scope_note='Observed development cases, no held-out quality claim')
        client = CapturedTransport(journal) if transport_factory is None else transport_factory(journal)
        runtime = client.metadata([model, embedding_model])
        check_runtime(runtime, baseline['runtime'], model)
        if runtime['models'][embedding_model]['digest'] != original_embeddings[0]['digest']:
            raise ValueError('embedding_digest_differs_from_baseline')
        counts = dict(embedding=0, decision=0, selection=0)
        limits = dict(embedding=15, decision=30, selection=30)
        def call(endpoint, payload):
            stage = 'embedding' if endpoint == '/api/embed' else ('decision' if 'format' not in payload else 'selection')
            if endpoint not in ('/api/embed', '/api/generate') or counts[stage] >= limits[stage]:
                raise BriefError('request_budget_exceeded')
            counts[stage] += 1
            journal.event('inference_dispatch', stage=stage, counters=dict(counts))
            return client(endpoint, payload)
        report = evaluate(model, embedding_model, call, journal)
        atomic_json(journal.directory / 'runtime_after.json', client.request('/api/ps'))
        after = client.request('/api/tags')
        atomic_json(journal.directory / 'model_inventory_after.json', after)
        unchanged = all(len(matches := [m for m in after.get('models', [])
                        if m.get('name') == name or m.get('model') == name]) == 1 and
                        matches[0].get('digest') == details['digest']
                        for name, details in runtime['models'].items())
        report.update(protocol=journal.state['protocol'], execution=execution,
                      generation_model=model, embedding_model=embedding_model,
                      selector_policy=POLICY, source_sha256=sources,
                      baseline_file_sha256=baseline['file_sha256'], model_identity_unchanged=unchanged,
                      request_counts=counts, generation_requests=counts['decision'] + counts['selection'],
                      historical_reference_checks='13/16 unchanged; not a controlled comparator',
                      human_review='pending', scope='Paired full-path development comparison B vs C; no oracle context')
        atomic_json(journal.directory / 'report.json', report)
        if not unchanged:
            raise BriefError('runtime_model_identity_changed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-local', action='store_true')
    args = parser.parse_args()
    if not args.allow_local:
        parser.error('--allow-local is required; up to 15 embedding and 60 generation calls')
    previous = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        raise KeyboardInterrupt('SIGTERM')
    signal.signal(signal.SIGTERM, terminate)
    try:
        report = execute(args.output, args.baseline_capture, True)
    except KeyboardInterrupt:
        return 130
    except (BriefError, ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps(dict(status='failed', error_type=type(error).__name__, error_code=str(error))))
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps({k: report[k] for k in ('execution', 'request_counts', 'arms', 'database_unchanged')}, indent=2))
    return 0 if report['database_unchanged'] and all(a['reference_checks_passed'] == 16 for a in report['arms'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
