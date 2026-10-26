"""Validate/build preregistered synthetic data without any provider calls."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import tempfile

from assistant import context
from ingest import ingest

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'prospective_evaluation_v1'


def validate_lock():
    manifest = json.loads((DATA / 'manifest.json').read_text())
    for name, expected in manifest['data_sha256'].items():
        if Path(name).name != name or hashlib.sha256((DATA / name).read_bytes()).hexdigest() != expected:
            raise ValueError('prospective_data_changed')
    for name, expected in manifest['frozen_runtime_sha256'].items():
        if Path(name).name != name or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('frozen_candidate_changed:' + name)
    return manifest


def build(destination):
    validate_lock()
    source = json.loads((DATA / 'bundle.json').read_text())
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    with (root / 'orders.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['order_id', 'due_date', 'quantity'], lineterminator='\n')
        writer.writeheader()
        writer.writerows(source['orders'])
    (root / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in source['events']) + '\n', encoding='utf-8')
    entries = []
    for index, note in enumerate(source['notes']):
        name = f'note-{index:02d}.txt'
        (root / name).write_text(note['text'], encoding='utf-8')
        entries.append(dict(note_id=note['note_id'], order_id=note['order_id'], path=name))
    (root / 'manifest.json').write_text(json.dumps(dict(contract='operations-bundle-v1',
        orders='orders.csv', events='events.jsonl', notes=entries)), encoding='utf-8')
    return root


def verify():
    manifest = validate_lock()
    cases = json.loads((DATA / 'cases.json').read_text())
    if len(cases) != 16 or len({c['case'] for c in cases}) != 16:
        raise ValueError('prospective_case_count_invalid')
    with tempfile.TemporaryDirectory(prefix='prospective-check-') as td:
        root = Path(td)
        build(root / 'bundle')
        result = ingest(root / 'bundle', root / 'db.sqlite')
        if result['status'] != 'committed':
            raise ValueError('prospective_ingestion_failed')
        answerable = negatives = gates = 0
        for case in cases:
            ctx = context(root / 'db.sqlite', case['order_id'])
            available = {r['evidence_id'] for r in ctx['evidence']}
            if not set(case['required_ids']) <= available:
                raise ValueError('prospective_reference_unavailable')
            if not case['required_ids'] and case['expected_status'] != 'abstained':
                raise ValueError('prospective_reference_status_invalid')
            if case['required_ids']:
                answerable += 1
                if case['expected_status'] != 'review_draft':
                    raise ValueError('prospective_reference_status_invalid')
            elif ctx['found']:
                negatives += 1
            else:
                gates += 1
        if (answerable, negatives, gates) != (8, 7, 1):
            raise ValueError('prospective_cohorts_invalid')
    return dict(status='software_validation_passed', cases=16, answerable=8,
                model_abstention_cases=7, application_gate_cases=1,
                fixture_fingerprint=result['fingerprint'], model_calls=0,
                candidate_freeze_commit=manifest['candidate_freeze_commit'],
                human_reference_review='pending', first_model_run='not_performed_by_this_tool',
                scope='Developer-authored prospective generalization set; not independently authored or a secret held-out benchmark')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'build'))
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    if args.action == 'build':
        if args.directory is None:
            parser.error('--directory is required for build')
        print(json.dumps(dict(bundle=str(build(args.directory)), model_calls=0)))
    else:
        print(json.dumps(verify(), indent=2))


if __name__ == '__main__':
    main()
