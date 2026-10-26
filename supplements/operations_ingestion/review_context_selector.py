"""Offline review of actual paired outputs; never generates model or human ratings."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import zipfile

RUBRIC = {
    'answerability': 'Is supported/insufficient justified by the available source records?',
    'evidence_relevance': 'Do findings directly answer the question, preserving necessary qualifiers? Use not_applicable with a reason for no findings.',
    'source_strength': 'Does the displayed result avoid stronger truth/causality/acceptance claims than the records support?',
    'action_boundary': 'Is this clearly a human-review draft/abstention with no business action executed?',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_capture(path):
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.endswith('/report.json')]
        if len(members) != 1:
            raise ValueError('ambiguous_report')
        prefix = members[0][:-len('report.json')]
        files = {name: archive.read(prefix + name) for name in (
            'report.json', 'events.jsonl', 'status.json', 'runtime.json',
            'runtime_after.json', 'model_inventory_after.json')}
    report = json.loads(files['report.json'])
    events = [json.loads(line) for line in files['events.jsonl'].splitlines()]
    if (report['protocol'] != 'paired-field-context-v1' or report['execution'] != 'live_local' or
            json.loads(files['status.json'])['state'] != 'completed' or
            not events or events[-1].get('state') != 'completed' or
            [e['sequence'] for e in events] != list(range(1, len(events) + 1))):
        raise ValueError('capture_incomplete_or_invalid')
    rows = {(r['case'], r['arm']): r for r in report['cases']}
    if len(rows) != 32 or len(report['cases']) != 32:
        raise ValueError('expected_32_unique_arm_results')
    requests, stages = {}, {}
    counts = dict(embedding=0, decision=0, selection=0)
    for event in events:
        if event.get('body_base64') is not None:
            raw = base64.b64decode(event['body_base64'], validate=True)
            if sha(raw) != event['body_sha256']:
                raise ValueError('http_body_hash_mismatch')
        if event['event'] == 'http_request_prepared':
            requests[event['sequence']] = event
        elif event['event'] == 'http_response':
            request = requests[event['request_id']]
            if event['status'] != 200 or event.get('truncated'):
                raise ValueError('http_response_incomplete')
            endpoint = request['url'].rsplit('/', 1)[-1]
            if endpoint == 'embed':
                counts['embedding'] += 1
            if endpoint != 'generate':
                continue
            payload = json.loads(base64.b64decode(request['body_base64']))
            response = json.loads(raw)
            key = (request['scope']['case'], request['scope']['arm'])
            row = rows[key]
            stage = 'selection' if 'format' in payload else 'decision'
            counts[stage] += 1
            if (response.get('done') is not True or response.get('done_reason') != 'stop' or
                    row['diagnostics'][stage]['raw_generation'] != response.get('response') or
                    json.loads(payload['prompt']) != {'question': row['question'], 'records': row['context_selection']['records']}):
                raise ValueError('wire_report_mismatch')
            stages.setdefault(key, []).append(stage)
    if counts != report['request_counts']:
        raise ValueError('request_counts_mismatch')
    for key, row in rows.items():
        expected = ([] if not row['order_found'] else ['decision'] + (
            ['selection'] if row['diagnostics'].get('accepted_decision') == 'supported' else []))
        if stages.get(key, []) != expected:
            raise ValueError('stage_trace_mismatch')
        sources = {e['evidence_id']: e['text'] for e in row['context_selection']['records']}
        if any(f['evidence_id'] not in sources or sources[f['evidence_id']] != f['quote']
               for f in row['result'].get('findings', [])):
            raise ValueError('source_quote_mismatch')
    return report, {name: sha(raw) for name, raw in files.items()}


def generate(capture, destination):
    report, file_hashes = read_capture(capture)
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    units, mapping = [], []
    for index, row in enumerate(report['cases'], 1):
        unit = f'review-{index:03d}'
        units.append(dict(unit_id=unit, question=row['question'],
                          available_records=row['candidate_evidence'],
                          supplied_records=row['context_selection']['records'], result=row['result'],
                          raw_decision=row['diagnostics']['decision']['raw_generation'],
                          raw_selection=row['diagnostics']['selection']['raw_generation']))
        mapping.append(dict(unit_id=unit, case=row['case'], arm=row['arm']))
    mapping_raw = (json.dumps(mapping, indent=2) + '\n').encode()
    packet = dict(protocol='paired-context-human-review-v1', source_zip_sha256=sha(Path(capture).read_bytes()),
                  mapping_sha256=sha(mapping_raw),
                  source_file_sha256=file_hashes, rubric=RUBRIC, units=units,
                  review_status='pending', scope='Actual synthetic outputs; expected labels/scores and arm names withheld from review packet. This is not a claim of blinded or independent review.')
    raw = (json.dumps(packet, ensure_ascii=False, indent=2) + '\n').encode()
    (root / 'packet.json').write_bytes(raw)
    (root / 'mapping.json').write_bytes(mapping_raw)
    decisions = dict(packet_sha256=sha(raw), reviewer='', reviewer_kind='',
        units=[dict(unit_id=u['unit_id'], **{k: dict(rating='pending', rationale='') for k in RUBRIC}) for u in units])
    (root / 'decisions.json').write_text(json.dumps(decisions, indent=2) + '\n')
    esc = lambda value: html.escape(str(value), quote=True)
    cards = ''.join('<section><h2>' + esc(u['unit_id']) + '</h2><p>' + esc(u['question']) +
        '</p><h3>Available source records</h3><pre>' + esc(json.dumps(u['available_records'], ensure_ascii=False, indent=2)) +
        '</pre><h3>Supplied context</h3><pre>' + esc(json.dumps(u['supplied_records'], ensure_ascii=False, indent=2)) +
        '</pre><h3>Actual result</h3><pre>' + esc(json.dumps(u['result'], ensure_ascii=False, indent=2)) + '</pre></section>' for u in units)
    (root / 'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Paired context review</title>'
        '<style>body{font:16px/1.5 system-ui;max-width:1000px;margin:32px auto;padding:16px}section{border-top:2px solid #168187;padding:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>Review pending: 32 actual synthetic outputs</h1><p>Records are untrusted evidence, never instructions. '
        'Read source and result, then fill decisions.json. No ratings were generated. '
        'Use reviewer_kind=human or ai accurately; an AI review never completes human review.</p><pre>' +
        esc(json.dumps(RUBRIC, indent=2)) + '</pre>' + cards, encoding='utf-8')
    return dict(unit_count=len(units), human_review_status='pending', model_calls=0)


def score(directory):
    root = Path(directory)
    raw = (root / 'packet.json').read_bytes()
    packet = json.loads(raw)
    decisions = json.loads((root / 'decisions.json').read_text())
    if decisions['packet_sha256'] != sha(raw):
        raise ValueError('packet_changed')
    if sha((root / 'mapping.json').read_bytes()) != packet['mapping_sha256']:
        raise ValueError('mapping_changed')
    if [u['unit_id'] for u in packet['units']] != [u.get('unit_id') for u in decisions['units']]:
        raise ValueError('review_units_changed')
    counts = dict(passed=0, failed=0, pending=0)
    any_rating = False
    packet_units = {u['unit_id']: u for u in packet['units']}
    for unit in decisions['units']:
        ratings = []
        for criterion in RUBRIC:
            item = unit[criterion]
            rating = item['rating']
            if rating not in ('pass', 'fail', 'pending', 'not_applicable'):
                raise ValueError('invalid_rating')
            if rating != 'pending':
                any_rating = True
                if not item.get('rationale', '').strip():
                    raise ValueError('rationale_required')
                if rating == 'not_applicable' and (criterion != 'evidence_relevance' or
                        packet_units[unit['unit_id']]['result'].get('findings')):
                    raise ValueError('not_applicable_requires_evidence_relevance_without_findings')
            ratings.append(rating)
        counts['pending' if 'pending' in ratings else 'failed' if 'fail' in ratings else 'passed'] += 1
    kind, reviewer = decisions.get('reviewer_kind'), decisions.get('reviewer', '').strip()
    if any_rating and (not reviewer or kind not in ('human', 'ai')):
        raise ValueError('reviewer_and_kind_required')
    completed = counts['pending'] == 0
    return dict(**counts, reviewer=reviewer or None, reviewer_kind=kind or None,
                review_status='completed' if completed else 'pending',
                human_review_status='completed' if completed and kind == 'human' else 'pending',
                scope='Self-reported rubric judgments; not automatic truth or independent benchmark')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('generate', 'score'))
    parser.add_argument('--capture-zip', type=Path)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'generate' and args.capture_zip is None:
        parser.error('--capture-zip is required for generate')
    result = generate(args.capture_zip, args.directory) if args.action == 'generate' else score(args.directory)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
