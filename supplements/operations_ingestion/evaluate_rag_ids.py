"""Evaluate ID selection on the unchanged eight-case regression set."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import tempfile

from assistant import BriefError, context
from ingest import ingest
from local_rag_ids import LOCAL_PROMPT, run

PROMPT_SHA = '1b0f3d8243bfe729b4fb1b0ff17dfb07ae5c8e0f9f248df7448936d022c1ff91'
# Reuse the exact previous cases, fixture and scoring. They are now regression cases.
from evaluate_rag_challenge import CASES, digest, make_bundle, score, render


def evaluate(embedding_model, model, transport=None):
    if hashlib.sha256(LOCAL_PROMPT.encode()).hexdigest() != PROMPT_SHA:
        raise ValueError('prompt_changed: create a separately versioned evaluation')
    rows = []
    with tempfile.TemporaryDirectory(prefix='rag-challenge-') as temp:
        root = Path(temp)
        bundle, db = root / 'bundle', root / 'challenge.sqlite'
        make_bundle(bundle)
        ingestion = ingest(bundle, db)
        if ingestion['status'] != 'committed':
            raise ValueError('challenge_ingestion_failed')
        before = digest(db)
        for case in CASES:
            name, oid, question, expected, required = case
            ctx = context(db, oid)
            diagnostics = {}
            try:
                result = run(db, oid, question, embedding_model, model, True,
                             transport=transport, diagnostics=diagnostics)
            except BriefError as exc:
                result = dict(status='failed', error_code=str(exc))
            # This evaluator creates its own synthetic data; raw output cannot include user notes.
            rows.append(dict(case=name, order_id=oid, question=question,
                             expected_status=expected, required_ids=required,
                             candidate_count=len(ctx['evidence']), candidate_evidence=ctx['evidence'],
                             checks=score(case, result, diagnostics,
                                          [e['evidence_id'] for e in ctx['evidence']]),
                             result=result, diagnostics=diagnostics))
        unchanged = digest(db) == before
    return dict(
        scope='Eight development regression cases used to diagnose v3; not held-out model evaluation',
        protocol='rag-ids-regression-v1', prompt_sha256=PROMPT_SHA,
        source_sha256={name: digest(Path(__file__).with_name(name)) for name in
                       ('evaluate_rag_ids.py', 'evaluate_rag_challenge.py', 'local_rag_ids.py', 'assistant.py', 'ingest.py')},
        fixture_fingerprint=ingestion['fingerprint'],
        embedding_model=embedding_model, generation_model=model,
        python=platform.python_version(), platform=platform.system(),
        execution='live_local' if transport is None else 'mock_only',
        database_unchanged=unchanged, human_review='pending',
        case_count=len(rows), reference_checks_passed=sum(r['checks']['reference_checks_passed'] for r in rows),
        generation_requests=sum(bool(r['diagnostics'].get('generation_request_started')) for r in rows),
        cases=rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--embedding-model', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--allow-local', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.allow_local:
        parser.error('--allow-local is required; uses local Ollama only')
    # Never overwrite earlier observations, including failed runs.
    args.output.mkdir(parents=True, exist_ok=False)
    report = evaluate(args.embedding_model, args.model)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (args.output / 'report.html').write_text(render(report), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('execution', 'case_count', 'reference_checks_passed',
                                           'generation_requests', 'database_unchanged', 'human_review')}, indent=2))
    return 0 if report['database_unchanged'] and report['reference_checks_passed'] == len(CASES) else 1


if __name__ == '__main__':
    raise SystemExit(main())
