"""One decision call omitting only format from a preserved due-date HTTP request."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import signal

from assistant import BriefError
from diagnose_rag_context import load_cases
from durable_rag import CapturedTransport, EvidenceRun, atomic_json
from evaluate_rag_challenge import digest
from local_rag_staged import DECISION_PROMPT, DECISION_SCHEMA, generate


def load_capture(directory):
    directory = Path(directory)
    names = ('events.jsonl', 'status.json', 'report.json', 'runtime.json',
             'runtime_after.json', 'model_inventory_after.json')
    raw = {name: (directory / name).read_bytes() for name in names}
    events = [json.loads(line) for line in raw['events.jsonl'].splitlines()]
    if [e['sequence'] for e in events] != list(range(1, len(events) + 1)):
        raise ValueError('baseline_journal_sequence_invalid')
    for event in events:
        if event['event'] in ('http_request_prepared', 'http_response') and event.get('body_base64') is not None:
            body = base64.b64decode(event['body_base64'], validate=True)
            if hashlib.sha256(body).hexdigest() != event['body_sha256']:
                raise ValueError('baseline_body_hash_mismatch')
    report = json.loads(raw['report.json'])
    if (json.loads(raw['status.json'])['state'] != 'completed' or
            events[-1].get('state') != 'completed' or
            report['protocol'] != 'durable-due-date-v1' or
            report['execution'] != 'live_local' or report['generation_requests'] != 1 or
            report.get('model_identity_unchanged') is not True):
        raise ValueError('baseline_must_be_completed_live_due_date')
    requests = [e for e in events if e['event'] == 'http_request_prepared' and
                e.get('url') == 'http://127.0.0.1:11434/api/generate']
    if len(requests) != 1:
        raise ValueError('baseline_generation_count_invalid')
    request = requests[0]
    replies = [e for e in events if e['event'] == 'http_response' and e.get('request_id') == request['sequence']]
    if len(replies) != 1 or replies[0].get('truncated') or replies[0]['status'] != 200:
        raise ValueError('baseline_response_invalid')
    response = json.loads(base64.b64decode(replies[0]['body_base64']))
    if response.get('done') is not True or response.get('done_reason') != 'stop':
        raise ValueError('baseline_generation_incomplete')
    payload = json.loads(base64.b64decode(request['body_base64']))
    baseline, cases = load_cases()
    case = next(c for c in cases if c['case'] == 'due_date_with_instruction')
    expected = dict(model=baseline['generation_model'], stream=False, format=DECISION_SCHEMA,
                    system=DECISION_PROMPT,
                    prompt=json.dumps({'question': case['question'], 'records': case['contexts']['reduced']}, ensure_ascii=False),
                    options={'temperature': 0, 'num_predict': 1600})
    if payload != expected:
        raise ValueError('baseline_request_does_not_match_frozen_due_date')
    if report['trials'][0]['diagnostics']['decision']['raw_generation'] != response.get('response'):
        raise ValueError('baseline_report_response_mismatch')
    return dict(payload=payload, runtime=json.loads(raw['runtime.json']), case=case,
                response=response,
                file_sha256={name: hashlib.sha256(data).hexdigest() for name, data in raw.items()})


def execute(directory, baseline_capture, allow_local=False, transport_factory=None):
    if not allow_local:
        raise BriefError('local_inference_disabled')
    baseline = load_capture(baseline_capture)
    model = baseline['payload']['model']
    execution = 'live_local' if transport_factory is None else 'mock_only'
    with EvidenceRun(directory, 'decision-format-ablation-v1', execution, 1) as journal:
        journal.event('experiment_config', baseline_file_sha256=baseline['file_sha256'],
                      changed_fields=['format: removed'], generation_limit=1,
                      source_sha256={p.name: digest(p) for p in Path(__file__).parent.glob('*.py')})
        transport = CapturedTransport(journal) if transport_factory is None else transport_factory(journal)
        runtime = transport.metadata([model])
        original_runtime = baseline['runtime']
        # Model identity alone does not control template changes or runtime version.
        for name in ('version',):
            if runtime[name] != original_runtime[name]:
                raise ValueError('runtime_version_differs_from_baseline')
        current, previous = runtime['models'][model], original_runtime['models'][model]
        if current['digest'] != previous['digest']:
            raise ValueError('model_digest_differs_from_baseline')
        for key in ('template', 'system', 'parameters', 'model_info', 'details', 'template_source'):
            if current['show'].get(key) != previous['show'].get(key):
                raise ValueError('model_configuration_differs_from_baseline:' + key)
        journal.scope = dict(case='due_date_with_instruction', arm='reduced_without_format')
        def omit_format(endpoint, payload):
            if endpoint != '/api/generate' or payload != baseline['payload']:
                raise ValueError('unexpected_request_difference')
            altered = dict(payload)
            del altered['format']
            journal.event('request_comparison', changed_fields=['format: removed'],
                          baseline_payload_sha256=hashlib.sha256(json.dumps(payload).encode()).hexdigest(),
                          all_remaining_fields_equal=altered == {k: v for k, v in baseline['payload'].items() if k != 'format'})
            return transport(endpoint, altered)
        trace = {'decision': dict(request_started=False, response_received=False, raw_generation=None)}
        case = baseline['case']
        journal.event('trial_started', question=case['question'], records=case['contexts']['reduced'])
        try:
            result = generate(omit_format, model, case['question'], case['contexts']['reduced'],
                              'decision', DECISION_PROMPT, DECISION_SCHEMA, trace)
            if not isinstance(result, dict) or set(result) != {'decision'} or result['decision'] not in ('supported', 'insufficient'):
                raise BriefError('invalid_decision')
            outcome, error = result['decision'], None
        except BriefError as exc:
            outcome, error = 'failed', str(exc)
        row = dict(outcome=outcome, error_code=error, diagnostics=trace,
                   semantic_review='pending; unconstrained prose is not automatically semantically wrong')
        journal.observation(row)
        atomic_json(journal.directory / 'runtime_after.json', transport.request('/api/ps'))
        inventory = transport.request('/api/tags')
        atomic_json(journal.directory / 'model_inventory_after.json', inventory)
        matches = [m for m in inventory.get('models', []) if m.get('name') == model or m.get('model') == model]
        unchanged = len(matches) == 1 and matches[0].get('digest') == current['digest']
        report = dict(protocol='decision-format-ablation-v1', execution=execution,
                      changed_fields=['format: removed'], generation_requests=1,
                      embedding_requests=0, selection_requests=0, trials=[row],
                      baseline_file_sha256=baseline['file_sha256'], model_identity_unchanged=unchanged,
                      baseline_raw_generation=baseline['response']['response'], human_review='pending',
                      limitations='One observation per condition, measured on different occasions; no causal or quality proof. Effective server defaults may differ.')
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
        parser.error('--allow-local is required')
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
    print(json.dumps(dict(execution=report['execution'], generation_requests=1,
                          outcome=report['trials'][0]['outcome'], output=str(args.output))))
    return 1 if report['trials'][0]['outcome'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
