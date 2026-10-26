"""Offline review of six uploaded synthetic ZIPs; no model/network calls or edits.

--captures is a JSON mapping: schema, no_format, short_system, negative_controls,
full_context, reduced_context -> local ZIP paths. --output must be a new directory.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zipfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_capture(path):
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        statuses = [n for n in archive.namelist() if n.endswith('/status.json')]
        assert len(statuses) == 1, 'ambiguous capture directory'
        prefix = statuses[0][:-len('status.json')]
        names = ('events.jsonl', 'status.json', 'report.json', 'runtime.json',
                 'runtime_after.json', 'model_inventory_after.json')
        files = {n: archive.read(prefix + n) for n in names}
    events = [json.loads(line) for line in files['events.jsonl'].splitlines()]
    assert [e['sequence'] for e in events] == list(range(1, len(events) + 1))
    assert json.loads(files['status.json'])['state'] == events[-1]['state'] == 'completed'
    requests, generations = {}, []
    for event in events:
        if event.get('body_base64') is not None:
            body = base64.b64decode(event['body_base64'], validate=True)
            assert sha(body) == event['body_sha256']
        if event['event'] == 'http_request_prepared':
            requests[event['sequence']] = event
        elif event['event'] == 'http_response':
            request = requests[event['request_id']]
            assert event['status'] == 200 and not event.get('truncated')
            if request['url'] == 'http://127.0.0.1:11434/api/generate':
                payload = json.loads(base64.b64decode(request['body_base64']))
                response = json.loads(base64.b64decode(event['body_base64']))
                assert request['method'] == 'POST'
                assert response['done'] is True and response['done_reason'] == 'stop'
                decision = json.loads(response['response'])
                assert set(decision) == {'decision'} and decision['decision'] in ('supported', 'insufficient')
                generations.append(dict(case=request['scope']['case'], payload=payload,
                                        response=response, decision=decision['decision']))
    report = json.loads(files['report.json'])
    assert report['execution'] == 'live_local' and report['model_identity_unchanged'] is True
    assert len(generations) == report['generation_requests'] == len(report['trials'])
    assert json.loads(files['status.json'])['completed_observations'] == len(generations)
    assert sum(r['url'].endswith('/api/generate') for r in requests.values()) == len(generations)
    assert report['embedding_requests'] == report['selection_requests'] == 0
    for generation, trial in zip(generations, report['trials']):
        assert trial['outcome'] == generation['decision']
        assert trial['diagnostics']['decision']['raw_generation'] == generation['response']['response']
    runtime = json.loads(files['runtime.json'])
    inventory = json.loads(files['model_inventory_after.json'])['models']
    for model, details in runtime['models'].items():
        assert [m['digest'] for m in inventory if m['name'] == model] == [details['digest']]
    return dict(archive=path.name, archive_sha256=sha(path.read_bytes()), files=files,
                file_sha256={n: sha(b) for n, b in files.items()}, report=report,
                runtime=runtime, generations=generations)


def verify(paths, historical_path):
    order = ('schema', 'no_format', 'short_system', 'negative_controls', 'full_context', 'reduced_context')
    assert set(paths) == set(order)
    captures = {name: read_capture(paths[name]) for name in order}
    for child, parent in (('no_format', 'schema'), ('short_system', 'no_format'),
                          ('negative_controls', 'short_system'), ('full_context', 'short_system'),
                          ('reduced_context', 'short_system')):
        assert captures[child]['report']['baseline_file_sha256'] == captures[parent]['file_sha256']
    assert captures['reduced_context']['report']['full_context_file_sha256'] == captures['full_context']['file_sha256']
    reference = captures['schema']['files']['runtime.json']
    assert all(c['files']['runtime.json'] == reference for c in captures.values())
    original = captures['schema']['generations'][0]['payload']
    no_format = captures['no_format']['generations'][0]['payload']
    short = captures['short_system']['generations'][0]['payload']
    assert no_format == {k: v for k, v in original.items() if k != 'format'}
    assert short != no_format and dict(short, system=no_format['system']) == no_format
    historical_raw = Path(historical_path).read_bytes()
    assert sha(historical_raw) == '74ea129d8f2f5abc459f906e4662fcaabdeaa1dbaecac05b045bc2095a7598a8'
    historical = json.loads(historical_raw)
    indexed = {r['case']: r for r in historical['cases']}
    for name in ('negative_controls', 'full_context', 'reduced_context'):
        for trial in captures[name]['generations']:
            payload = trial['payload']
            assert set(payload) == set(short)
            assert dict(payload, prompt=short['prompt']) == short
            inputs = json.loads(payload['prompt'])
            assert set(inputs) == {'question', 'records'}
            if trial['case'] == 'due_date_reduced_positive_control':
                assert payload == short
                continue
            row = indexed[trial['case']]
            assert inputs['question'] == row['question']
            sources = {r['evidence_id']: r for r in row['candidate_evidence']}
            records = [sources[eid] for eid in row['diagnostics']['retrieved_ids']]
            if name == 'reduced_context':
                keep = set(row['required_ids']) | {'order:' + row['order_id']}
                records = [r for r in records if r['evidence_id'] in keep]
            assert inputs['records'] == records
    assert len(captures['negative_controls']['generations']) == 8
    assert {g['case'] for g in captures['negative_controls']['generations'][:-1]} == {
        r['case'] for r in historical['cases'] if r['expected_status'] == 'abstained' and
        r['diagnostics']['generation_request_started']}
    full = {g['case']: g for g in captures['full_context']['generations']}
    reduced = {g['case']: g for g in captures['reduced_context']['generations']}
    assert set(full) == set(reduced) == {'receiving_window', 'quantity_with_cause_context'}
    for name in full:
        before, after = full[name]['payload'], reduced[name]['payload']
        assert dict(after, prompt=before['prompt']) == before
        assert json.loads(after['prompt'])['question'] == json.loads(before['prompt'])['question']
    summary = {}
    for name, capture in captures.items():
        summary[name] = dict(archive=capture['archive'], archive_sha256=capture['archive_sha256'],
            file_sha256=capture['file_sha256'], protocol=capture['report']['protocol'],
            started_utc=json.loads(capture['files']['status.json'])['started_utc'],
            decisions=[dict(case=g['case'], decision=g['decision'],
                record_count=len(json.loads(g['payload']['prompt'])['records']),
                prompt_eval_count=g['response']['prompt_eval_count']) for g in capture['generations']])
    return dict(verification='passed', captures=summary,
                runtime_version=captures['schema']['runtime']['version'],
                model_digests={n: m['digest'] for n, m in captures['schema']['runtime']['models'].items()},
                verified_live_decisions=sum(len(c['generations']) for c in captures.values()),
                live_calls_by_this_verifier=0,
                scope='Offline integrity and controlled-request comparisons; not independent runtime attestation, held-out accuracy or end-to-end scoring')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--historical-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(json.loads(args.captures.read_text()), args.historical_report)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'verified_summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Verified six captures and', result['verified_live_decisions'], 'recorded decisions; no live calls')


if __name__ == '__main__':
    main()
