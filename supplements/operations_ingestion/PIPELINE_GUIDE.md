# Milestone 3 — offline pipeline orchestration

## Run on Mac

Extract this release into a **new folder**, separate from the existing Operations_M2. No pip packages, API key, API credits, Docker or external service is needed for the commands below. Python 3.10+.

```bash
python3 verify.py
python3 evaluate_assistant.py
python3 pipeline.py --bundle fixtures --output output/pipeline-demo
python3 pipeline.py --bundle fixtures --output output/pipeline-demo
```

Expected: 43 tests pass; baseline 8/8; both pipeline runs return `passed_local`. The second run's ingestion result is `duplicate`, and all business-row counts remain unchanged. Each invocation deliberately adds audit entries and creates a distinct report directory; it is not byte-identical operational metadata.

The command prints `run_dir`. Open that directory's `report.html` using Finder or `open` with the exact printed path. It also contains `pipeline_run.json` (stage evidence) and `data_report.json` (exact report numbers). For bundled fixtures: 3 orders, 225 ordered units, 3 events, 2 notes. Opening the report requires no server or internet.

## Implemented sequence

1. **Ingest:** validate and transactionally insert the mixed-source bundle, or recognize an exact duplicate.
2. **Reconcile:** compare every supplied business row exactly with SQLite; check integrity and foreign keys.
3. **Replay check:** replay the same bundle and assert all business rows remain unchanged. This adds a duplicate audit record.
4. **Report:** SQL totals, order/event/note counts and the first 25 order-ID baseline statuses, exported as JSON and static HTML.

Events/notes are counted with separate aggregates so joins cannot multiply ordered quantity. The report covers all accumulated orders in this pipeline-owned database, while source reconciliation covers the current input bundle. The baseline sample is explicitly limited to 25 orders, not represented as an assessment of every row.

## Failure boundaries

- Fail-fast: failed stage => all subsequent stages skipped. No successful report is created for a run that fails before report generation.
- Ingestion failure rolls back its business transaction; the ingestion audit remains.
- A downstream reconciliation/report failure does **not** undo an already committed ingestion. Stage evidence explicitly preserves that boundary. Fix the underlying issue and rerun; no automatic deletion/reset occurs.
- Every run gets UTC stage start/end timestamps, observed durations, Python/platform identity and source hashes. Durations are observations, not performance benchmarks.
- This is local sequential orchestration. It is not Airflow, dbt, a distributed scheduler, streaming, a retry service or evidence of remote deployment.
- The pipeline never invokes the provider adapter. It always calls briefing in `mode=baseline`; no credentials are needed and no network request is intended. Tests fail if pipeline code attempts network access.
- Output directories must be newly empty or marked as owned by this pipeline. Input/output paths cannot overlap. Do not point output to a folder holding unrelated databases. This ownership marker is a workflow guard, not a multi-user security boundary or process lock. Run one pipeline process at a time per output folder.

## Verification state

- Development: 43 tests plus full local ingestion acceptance and 8 baseline regression cases passed.
- Mac author evidence from 20 October: earlier M2's 30 tests passed on Python 3.10.11; baseline 8/8; explicit demo ingestion and O001 baseline briefing passed. The author subsequently ran M3 on Mac: all 43 tests passed, all four pipeline stages passed, SQLite integrity was ok and foreign-key violations were 0. See AUTHOR_VERIFICATION.md.
- Actual OpenAI execution remains **blocked by API credits**. TLS configuration was repaired by the author using user-installed certifi and SSL_CERT_FILE. No successful model-output or GenAI-quality claim.
- No remote CI for this supplement yet. HTML has generated-structure/content checks and escaped display values; visual review in the author's browser remains pending.

## Portfolio use

This adds mixed-format ingestion, explicit data contracts, local orchestration, source-to-storage reconciliation, idempotency and failure reporting to the DE portfolio. It supplies readable evidence for operations decision-support design without pretending the deterministic baseline is AI.

Next separate workstream: validate actual OCR preprocessing/recognition experiments using held-out source documents. Custom pipeline orchestration and an optional API adapter demonstrate a bounded set of engineering capabilities; broader deployment and model evaluation require separate evidence.
