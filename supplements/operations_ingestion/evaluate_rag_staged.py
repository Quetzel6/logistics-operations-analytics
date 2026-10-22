"""Evaluate the two-stage protocol on the two previously observed cohorts."""
import argparse
import json
from pathlib import Path
import platform
import tempfile

from assistant import BriefError, context
from evaluate_rag_challenge import CASES, digest, make_bundle, render, score
from ingest import ingest
from local_rag_staged import PROMPT_SHA as CURRENT_PROMPT_SHA, run
from evaluate_rag_ids_v2 import NEW_CASES, make_new_bundle

PROMPT_SHA = '3793279128e0a58554613e214c15493563c2a700ec804f2ccecc748d23ccd8dc'


def evaluate(embedding_model, model, transport=None):
    if CURRENT_PROMPT_SHA != PROMPT_SHA:
        raise ValueError('prompt_changed: version the evaluation before running')
    rows, cohorts = [], []
    for cohort, cases, builder in [('regression', CASES, make_bundle),
                                   ('prior_new_cases', NEW_CASES, make_new_bundle)]:
        with tempfile.TemporaryDirectory(prefix='rag-ids-v2-') as temp:
            root = Path(temp)
            builder(root / 'bundle')
            db = root / 'data.sqlite'
            ingestion = ingest(root / 'bundle', db)
            if ingestion['status'] != 'committed':
                raise ValueError('fixture_ingestion_failed')
            before = digest(db)
            group = []
            for case in cases:
                name, oid, question, expected, required = case
                ctx, diagnostics = context(db, oid), {}
                try:
                    result = run(db, oid, question, embedding_model, model, True,
                                 transport=transport, diagnostics=diagnostics)
                except BriefError as exc:
                    result = dict(status='failed', error_code=str(exc),
                        failure_stage='selection' if diagnostics.get('selection', {}).get('request_started')
                        else 'decision' if diagnostics.get('decision', {}).get('request_started') else 'retrieval')
                group.append(dict(case=name, cohort=cohort, order_id=oid, question=question,
                    expected_status=expected, required_ids=required,
                    candidate_count=len(ctx['evidence']), candidate_evidence=ctx['evidence'],
                    checks=score(case, result, diagnostics, [e['evidence_id'] for e in ctx['evidence']]),
                    result=result, diagnostics=diagnostics))
            cohorts.append(dict(cohort=cohort, case_count=len(group),
                reference_checks_passed=sum(r['checks']['reference_checks_passed'] for r in group),
                answerable_passed=sum(r['checks']['reference_checks_passed'] for r in group if r['required_ids']),
                answerable_count=sum(bool(r['required_ids']) for r in group),
                abstention_passed=sum(r['checks']['reference_checks_passed'] for r in group if not r['required_ids']),
                abstention_count=sum(not r['required_ids'] for r in group),
                model_abstention_count=sum(not r['required_ids'] and r['diagnostics'].get('generation_request_started', False) for r in group),
                model_abstention_passed=sum(r['checks']['reference_checks_passed'] for r in group if not r['required_ids'] and r['diagnostics'].get('generation_request_started')),
                pre_inference_cases=sum(not r['diagnostics'].get('generation_request_started', False) for r in group),
                database_unchanged=digest(db) == before, fixture_fingerprint=ingestion['fingerprint']))
            rows.extend(group)
    report = dict(protocol='rag-two-stage-v1-two-regression-cohorts',
        scope='Two previously observed development cohorts; no held-out performance claim',
        execution='live_local' if transport is None else 'mock_only',
        prompt_sha256=PROMPT_SHA,
        source_sha256={n: digest(Path(__file__).with_name(n)) for n in
            ('evaluate_rag_staged.py', 'evaluate_rag_ids_v2.py', 'evaluate_rag_challenge.py',
             'local_rag_staged.py', 'local_rag.py', 'local_rag_ids.py', 'local_rag_ids_v2.py', 'assistant.py', 'ingest.py')},
        embedding_model=embedding_model, generation_model=model,
        python=platform.python_version(), platform=platform.system(),
        human_review='pending', database_unchanged=all(c['database_unchanged'] for c in cohorts),
        case_count=len(rows), reference_checks_passed=sum(c['reference_checks_passed'] for c in cohorts),
        generation_requests=sum(bool(r['diagnostics'].get(stage, {}).get('request_started'))
                                for r in rows for stage in ('decision', 'selection')),
        cohorts=cohorts, cases=rows)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--embedding-model', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--allow-local', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.allow_local:
        parser.error('--allow-local is required')
    args.output.mkdir(parents=True, exist_ok=False)
    report = evaluate(args.embedding_model, args.model)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    # Reuse escaped case rendering. Keep cohort totals explicit above individual cases.
    page = render(report)
    import html
    page = page.replace('<h1>Operations evidence review</h1>',
        '<h1>Operations evidence review</h1><h2>Separate evaluation cohorts</h2><pre>' +
        html.escape(json.dumps(report['cohorts'], indent=2)) + '</pre>')
    (args.output / 'report.html').write_text(page, encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('execution', 'cohorts', 'generation_requests',
                                            'database_unchanged', 'human_review')}, indent=2))
    return 0 if report['database_unchanged'] and report['reference_checks_passed'] == report['case_count'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
