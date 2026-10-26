"""Frozen short-prompt decision diagnostics using historical retrieved records."""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import signal

from assistant import BriefError
from diagnose_rag_context import load_cases, SOURCE_SHA
from diagnose_rag_format import SHORT_DECISION_PROMPT, check_runtime, load_capture
from durable_rag import CapturedTransport, EvidenceRun, atomic_json
from evaluate_rag_challenge import digest
from local_rag_staged import DECISION_SCHEMA, generate


def plan(baseline, suite='abstention-controls'):
    if suite not in ('abstention-controls', 'false-abstentions', 'reduced-false-abstentions'):
        raise ValueError('invalid_suite')
    original, context_cases = load_cases()  # Verifies frozen original report and source hashes.
    if suite in ('false-abstentions', 'reduced-false-abstentions'):
        indexed = {row['case']: row for row in original['cases']}
        selected = []
        for name in ('receiving_window', 'quantity_with_cause_context'):
            row = indexed[name]
            sources = {e['evidence_id']: e for e in row['candidate_evidence']}
            records = [sources[eid] for eid in row['diagnostics']['retrieved_ids']]
            if (row['expected_status'] != 'review_draft' or not row['required_ids'] or
                    row['diagnostics']['accepted_decision'] != 'insufficient' or
                    not set(row['required_ids']) <= {r['evidence_id'] for r in records}):
                raise ValueError('false_abstention_reference_changed')
            if suite == 'reduced-false-abstentions':
                reduced = next(c for c in context_cases if c['case'] == name)['contexts']['reduced']
                if not len(reduced) < len(records) or not all(r in records for r in reduced):
                    raise ValueError('invalid_reduced_records')
                records = reduced
            selected.append(dict(case=name, question=row['question'], records=records,
                                 expected_decision='supported', group='positive'))
        return selected
    cases = []
    for row in original['cases']:
        if row['expected_status'] != 'abstained' or not row['diagnostics']['generation_request_started']:
            continue  # Unknown-order application gate is never counted as model abstention.
        if row['required_ids']:
            raise ValueError('invalid_negative_reference')
        sources = {e['evidence_id']: e for e in row['candidate_evidence']}
        records = [sources[eid] for eid in row['diagnostics']['retrieved_ids']]
        if not records:
            raise ValueError('missing_negative_records')
        cases.append(dict(case=row['case'], question=row['question'], records=records,
                          expected_decision='insufficient', group='negative'))
    if len(cases) != 7:
        raise ValueError('negative_case_count_changed')
    positive = json.loads(baseline['payload']['prompt'])
    cases.append(dict(case='due_date_reduced_positive_control', **positive,
                      expected_decision='supported', group='positive'))
    return cases


def load_full_capture(directory, baseline):
    """Validate the actual two-case full-context control before a records-only change."""
    if directory is None:
        raise ValueError('full_context_capture_required')
    names = ('events.jsonl', 'status.json', 'report.json', 'runtime.json',
             'runtime_after.json', 'model_inventory_after.json')
    raw = {name: (Path(directory) / name).read_bytes() for name in names}
    events = [json.loads(line) for line in raw['events.jsonl'].splitlines()]
    if [e['sequence'] for e in events] != list(range(1, len(events) + 1)):
        raise ValueError('full_capture_sequence_invalid')
    for e in events:
        if e.get('body_base64') is not None:
            body = base64.b64decode(e['body_base64'], validate=True)
            if hashlib.sha256(body).hexdigest() != e['body_sha256']:
                raise ValueError('full_capture_body_hash_mismatch')
    report = json.loads(raw['report.json'])
    if report.get('baseline_file_sha256') != baseline['file_sha256']:
        raise ValueError('full_capture_baseline_hashes_mismatch')
    if (json.loads(raw['status.json'])['state'] != 'completed' or
            events[-1].get('state') != 'completed' or
            report['protocol'] != 'short-system-false-abstentions-v1' or
            report['execution'] != 'live_local' or report['generation_requests'] != 2 or
            report.get('model_identity_unchanged') is not True):
        raise ValueError('full_capture_must_be_completed_live_two_case_run')
    check_runtime(json.loads(raw['runtime.json']), baseline['runtime'], baseline['payload']['model'])
    requests = [e for e in events if e['event'] == 'http_request_prepared' and
                e.get('url') == 'http://127.0.0.1:11434/api/generate']
    full_plan = plan(baseline, 'false-abstentions')
    if len(requests) != len(full_plan):
        raise ValueError('full_capture_generation_count_invalid')
    payloads = {}
    for request, case in zip(requests, full_plan):
        payload = json.loads(base64.b64decode(request['body_base64']))
        expected = dict(baseline['payload'])
        expected['prompt'] = json.dumps({'question': case['question'], 'records': case['records']}, ensure_ascii=False)
        if payload != expected or request['scope']['case'] != case['case']:
            raise ValueError('full_capture_request_mismatch')
        replies = [e for e in events if e['event'] == 'http_response' and e.get('request_id') == request['sequence']]
        if len(replies) != 1 or replies[0].get('truncated') or replies[0]['status'] != 200:
            raise ValueError('full_capture_response_invalid')
        response = json.loads(base64.b64decode(replies[0]['body_base64']))
        if response.get('done') is not True or response.get('done_reason') != 'stop':
            raise ValueError('full_capture_generation_incomplete')
        if next(r for r in report['trials'] if r['case'] == case['case'])['diagnostics']['decision']['raw_generation'] != response.get('response'):
            raise ValueError('full_capture_report_mismatch')
        payloads[case['case']] = payload
    return dict(payloads=payloads, file_sha256={n: hashlib.sha256(b).hexdigest() for n, b in raw.items()})


def execute(directory, baseline_capture, allow_local=False, transport_factory=None,
            suite='abstention-controls', full_context_capture=None):
    if not allow_local:
        raise BriefError('local_inference_disabled')
    baseline = load_capture(baseline_capture, 'abstention-controls')
    cases = plan(baseline, suite)
    full_capture = load_full_capture(full_context_capture, baseline) if suite == 'reduced-false-abstentions' else None
    protocol = {'abstention-controls': 'short-system-abstention-controls-v1',
                'false-abstentions': 'short-system-false-abstentions-v1',
                'reduced-false-abstentions': 'short-system-reduced-false-abstentions-v1'}[suite]
    model = baseline['payload']['model']
    execution = 'live_local' if transport_factory is None else 'mock_only'
    with EvidenceRun(directory, protocol, execution, len(cases)) as journal:
        journal.event('experiment_config', baseline_file_sha256=baseline['file_sha256'],
                      original_staged_report_sha256=SOURCE_SHA, generation_limit=len(cases),
                      suite=suite,
                      short_system_sha256=hashlib.sha256(SHORT_DECISION_PROMPT.encode()).hexdigest(),
                      case_plan=cases,
                      full_context_file_sha256=full_capture['file_sha256'] if full_capture else None,
                      reference_assisted_context_reduction=full_capture is not None,
                      source_sha256={p.name: digest(p) for p in Path(__file__).parent.glob('*.py')})
        transport = CapturedTransport(journal) if transport_factory is None else transport_factory(journal)
        runtime = transport.metadata([model])
        current = check_runtime(runtime, baseline['runtime'], model)
        rows = []
        for case in cases:
            journal.scope = dict(case=case['case'], group=case['group'])
            trace = {'decision': dict(request_started=False, response_received=False, raw_generation=None)}
            journal.event('trial_started', question=case['question'], records=case['records'])
            expected = dict(baseline['payload'])
            expected['prompt'] = json.dumps({'question': case['question'], 'records': case['records']}, ensure_ascii=False)
            def dispatch(endpoint, payload):
                altered = dict(payload)
                del altered['format']
                if endpoint != '/api/generate' or altered != expected:
                    raise ValueError('unexpected_control_request')
                if full_capture:
                    previous = full_capture['payloads'][case['case']]
                    current_input, previous_input = json.loads(altered['prompt']), json.loads(previous['prompt'])
                    restored = dict(altered, prompt=previous['prompt'])
                    if restored != previous or current_input['question'] != previous_input['question']:
                        raise ValueError('unexpected_non_records_difference')
                    journal.event('context_comparison', only_records_changed=True,
                                  full_record_count=len(previous_input['records']),
                                  reduced_record_count=len(current_input['records']),
                                  full_payload_sha256=hashlib.sha256(json.dumps(previous).encode()).hexdigest())
                journal.event('request_comparison', fixed_system_options_model=True,
                              format_absent=True, reference_labels_sent=False)
                return transport(endpoint, altered)
            try:
                result = generate(dispatch, model, case['question'], case['records'],
                                  'decision', SHORT_DECISION_PROMPT, DECISION_SCHEMA, trace)
                if not isinstance(result, dict) or set(result) != {'decision'} or result['decision'] not in ('supported', 'insufficient'):
                    raise BriefError('invalid_decision')
                outcome, error = result['decision'], None
            except BriefError as exc:
                outcome, error = 'failed', str(exc)
            row = dict(case=case['case'], group=case['group'], expected_decision=case['expected_decision'],
                       outcome=outcome, error_code=error, diagnostics=trace,
                       decision_matches_reference=outcome == case['expected_decision'],
                       semantic_review='pending; parse failure does not determine semantic correctness')
            journal.observation(row)
            rows.append(row)
        atomic_json(journal.directory / 'runtime_after.json', transport.request('/api/ps'))
        inventory = transport.request('/api/tags')
        atomic_json(journal.directory / 'model_inventory_after.json', inventory)
        matches = [m for m in inventory.get('models', []) if m.get('name') == model or m.get('model') == model]
        unchanged = len(matches) == 1 and matches[0].get('digest') == current['digest']
        negative = Counter(r['outcome'] for r in rows if r['group'] == 'negative')
        positive = Counter(r['outcome'] for r in rows if r['group'] == 'positive')
        report = dict(protocol=journal.state['protocol'], execution=execution, trials=rows,
                      suite=suite, generation_requests=len(rows), embedding_requests=0, selection_requests=0,
                      negative_controls=dict(count=sum(r['group'] == 'negative' for r in rows), correct_insufficient=negative['insufficient'],
                          false_support=negative['supported'], failed=negative['failed']),
                      positive_control=dict(count=sum(r['group'] == 'positive' for r in rows), correct_supported=positive['supported'],
                          false_abstention=positive['insufficient'], failed=positive['failed']),
                      baseline_file_sha256=baseline['file_sha256'], model_identity_unchanged=unchanged,
                      full_context_file_sha256=full_capture['file_sha256'] if full_capture else None,
                      reference_assisted_context_reduction=full_capture is not None,
                      human_review='pending', scope='Decision-only on observed development cases with preserved historical retrieved records; no new retrieval, ID selection or end-to-end score')
        atomic_json(journal.directory / 'report.json', report)
        if not unchanged:
            raise BriefError('runtime_model_identity_changed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('abstention-controls', 'false-abstentions', 'reduced-false-abstentions'),
                        default='abstention-controls')
    parser.add_argument('--full-context-capture', type=Path)
    parser.add_argument('--baseline-capture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--allow-local', action='store_true')
    args = parser.parse_args()
    if not args.allow_local:
        parser.error('--allow-local is required; fixed decision batch, no retries')
    previous = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        raise KeyboardInterrupt('SIGTERM')
    signal.signal(signal.SIGTERM, terminate)
    try:
        report = execute(args.output, args.baseline_capture, True, suite=args.suite,
                         full_context_capture=args.full_context_capture)
    except KeyboardInterrupt:
        return 130
    except (BriefError, ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps(dict(status='failed', error_type=type(error).__name__, error_code=str(error))))
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps({k: report[k] for k in ('execution', 'generation_requests', 'negative_controls', 'positive_control')}))
    return 0 if all(r['decision_matches_reference'] for r in report['trials']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
