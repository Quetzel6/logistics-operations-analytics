"""Recompute a captured development run using stored responses, never Ollama."""
import argparse
import base64
import json
from pathlib import Path
import zipfile

from durable_rag import EvidenceRun, atomic_json
from evaluate_context_selector import evaluate
from review_context_selector import read_capture, sha


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items() if k not in ('latency_ms', 'live_execution')}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return round(value, 12) if isinstance(value, float) else value


def replay(capture, destination):
    original, file_hashes = read_capture(capture)
    source = Path(__file__).resolve().parent
    for name, expected in original['source_sha256'].items():
        if Path(name).name != name or not name.endswith('.py') or sha((source / name).read_bytes()) != expected:
            raise ValueError('captured_source_changed:' + name)
    with zipfile.ZipFile(capture) as archive:
        path = next(n for n in archive.namelist() if n.endswith('/events.jsonl'))
        events = [json.loads(line) for line in archive.read(path).splitlines()]
    requests = [e for e in events if e['event'] == 'http_request_prepared' and
                e['url'].rsplit('/', 1)[-1] in ('embed', 'generate')]
    responses = {e['request_id']: e for e in events if e['event'] == 'http_response'}
    position = 0
    with EvidenceRun(destination, 'offline-paired-replay-v1', 'replay_only', 32) as journal:
        def stored_call(endpoint, payload):
            nonlocal position
            if position >= len(requests):
                raise ValueError('unexpected_extra_replay_request')
            request = requests[position]
            if (not request['url'].endswith(endpoint) or
                    payload != json.loads(base64.b64decode(request['body_base64']))):
                raise ValueError('replay_payload_mismatch')
            position += 1
            journal.event('stored_response_replayed', original_request_id=request['sequence'])
            return json.loads(base64.b64decode(responses[request['sequence']]['body_base64']))
        result = evaluate(original['generation_model'], original['embedding_model'], stored_call, journal)
        if position != len(requests):
            raise ValueError('unconsumed_replay_requests')
        for key in ('cases', 'cohorts', 'arms', 'database_unchanged'):
            if normalized(result[key]) != normalized(original[key]):
                raise ValueError('replay_result_mismatch:' + key)
        verification = dict(status='offline_replay_verified', source_zip_sha256=sha(Path(capture).read_bytes()),
            source_file_sha256=file_hashes, replayed_inference_requests=position,
            source_request_counts=original['request_counts'], verified_arms=result['arms'],
            live_model_calls=0, independent_new_observations=0,
            comparison='All inference payloads exact; rankings/results rescored; cosine floats rounded to 12 decimal places; latency and live_execution provenance excluded (replay is not live)',
            scope='Reproduction of the captured development run, not a new evaluation')
        atomic_json(journal.directory / 'verification.json', verification)
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-zip', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = replay(args.capture_zip, args.output)
    print(json.dumps({k: result[k] for k in ('status', 'replayed_inference_requests', 'live_model_calls')}, indent=2))


if __name__ == '__main__':
    main()
