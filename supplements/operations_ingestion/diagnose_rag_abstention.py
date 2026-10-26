"""Frozen short-prompt decision-only controls: seven negatives and one positive."""
import argparse
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


def plan(baseline):
    original, _ = load_cases()  # Verifies frozen original report and source hashes.
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


def execute(directory, baseline_capture, allow_local=False, transport_factory=None):
    if not allow_local:
        raise BriefError('local_inference_disabled')
    baseline = load_capture(baseline_capture, 'abstention-controls')
    cases = plan(baseline)
    model = baseline['payload']['model']
    execution = 'live_local' if transport_factory is None else 'mock_only'
    with EvidenceRun(directory, 'short-system-abstention-controls-v1', execution, 8) as journal:
        journal.event('experiment_config', baseline_file_sha256=baseline['file_sha256'],
                      original_staged_report_sha256=SOURCE_SHA, generation_limit=8,
                      short_system_sha256=hashlib.sha256(SHORT_DECISION_PROMPT.encode()).hexdigest(),
                      case_plan=cases,
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
                      generation_requests=8, embedding_requests=0, selection_requests=0,
                      negative_controls=dict(count=7, correct_insufficient=negative['insufficient'],
                          false_support=negative['supported'], failed=negative['failed']),
                      positive_control=dict(count=1, correct_supported=positive['supported'],
                          false_abstention=positive['insufficient'], failed=positive['failed']),
                      baseline_file_sha256=baseline['file_sha256'], model_identity_unchanged=unchanged,
                      human_review='pending', scope='Decision-only on observed development cases with preserved historical retrieved records; no new retrieval, ID selection or end-to-end score')
        atomic_json(journal.directory / 'report.json', report)
        if not unchanged:
            raise BriefError('runtime_model_identity_changed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-capture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--allow-local', action='store_true')
    args = parser.parse_args()
    if not args.allow_local:
        parser.error('--allow-local is required; eight decision calls, no retries')
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
    print(json.dumps({k: report[k] for k in ('execution', 'generation_requests', 'negative_controls', 'positive_control')}))
    return 0 if all(r['decision_matches_reference'] for r in report['trials']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
