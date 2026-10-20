# Operations ingestion and evidence review lab

Working supplement staged for the existing analytics portfolio, not an employer system or factory connector. All bundled fixtures are synthetic. This stays separate from the FMCG loader, which replaces its project schemas and expects a complete generated snapshot rather than incremental files.

## Current release: M4 (2026-10-20)

See **M4_GUIDE_TH.md** for Mac steps, **CASE_STUDY.md** for the business case, and **DATA_MODEL.md** for grain/keys and the PostgreSQL experiment.

- Linux Python 3.12: 50 tests passed; eight baseline regression cases passed; pipeline repeat passed.
- Recent-window evidence selection now reserves note space and retains a recorded exception in the window.
- Eight-case offline review packet with explicit rubric, reviewer/rationale and source hash. **Author reviewed all eight and reported no issues; criterion-level scoring not submitted.**
- Disposable PostgreSQL 16 Docker benchmark prepared. **Author Mac execution passed; see AUTHOR_VERIFICATION_M4.json and the case-study update.**
- M4 author Mac: 50 tests and eight authored baseline cases passed. No model/API calls. Remote CI for M4 remains pending.

The sections below preserve earlier milestone history.

## Implemented

- CSV orders, JSONL operational events, original UTF-8 text notes.
- Centralized SQLite tables, relational keys and source-run provenance.
- Schema, date, quantity, ID and timezone validation.
- Whole-bundle rejection and transactional rollback; no partial business data.
- Exact bundle fingerprint deduplication; identical entities in changed bundles skip.
- Existing IDs with changed content reject, rather than silently overwrite.
- Committed/rejected/duplicate run history; unchanged note text plus SHA-256.
- Paths restricted to the bundle, including symlink resolution; 5 MB/file limit and maximum 1,000 note entries.

## Mac quick start — Python 3.10+, no dependencies

Extract into a NEW folder and open Terminal in `operations-ingestion-lab`:

```bash
python3 --version
python3 verify.py
python3 ingest.py --bundle fixtures --database output/demo.sqlite
python3 ingest.py --bundle fixtures --database output/demo.sqlite
```

Acceptance uses only temporary databases. CLI writes a NEW demo database in this folder. Do not point it at an unrelated existing SQLite database. Expected statuses: `passed_local`, then `committed`, then `duplicate`. Acceptance checks 3 orders, 3 events, 2 notes and total quantity 225, plus SQLite integrity/foreign keys.

**Status:** 14 unit tests and integrated acceptance passed in the development environment. No Mac author run or remote CI for this supplement yet. This milestone contains no ML, GenAI, provider call or agent.

## Contract

`fixtures/manifest.json` specifies `operations-bundle-v1` and input paths.

| Source | Exact fields |
| --- | --- |
| CSV header, in order | order_id,due_date,quantity |
| JSONL event | event_id,order_id,timestamp_utc,event_type |
| Notes manifest entry | note_id,order_id,path |

Dates are ISO calendar dates. Quantity is a positive signed 64-bit integer. IDs use 1–64 ASCII letters/digits/hyphens/underscores. Events require timezone-aware timestamps, normalized to UTC; types are dispatched, delivered or exception. Referenced orders must exist. Event-state transitions are not checked yet: storing `delivered` does not prove recipient acceptance.

Raw notes remain unstructured evidence, not commands or verified causes. Original text is stored, not sent to any external service. Protect database files with owner access controls: there is no built-in encryption, authentication or PII detector. Logs omit raw note content, but source paths/IDs may still be sensitive. This is a local controlled-input prototype, not a hardened public upload endpoint.

Whole-bundle validation precedes loading; foreign-key/conflict failures roll back business writes. A rejection audit is then written separately. Exact replay adds only an audit entry. IDs/timestamps vary across runs. Changed entity content requires a future versioned-correction policy. No streaming, CDC, retry scheduler, warehouse-scale benchmark, S3 or Airflow claim. Data rejection exits 1; storage failure exits 2.

## Fit

**Fabrinet:** mixed-format ingestion, validation, transactionality, deduplication, schemas and documentation. Not actual FITS/tester integration or professional DE tenure.

**Yusen:** traceable facts/events/text for a future evidence-grounded operations assistant. This ingestion milestone does not demonstrate prompt engineering, model inference or agentic AI.

See ROLE_ALIGNMENT.md for the next milestones and application boundaries.

## Milestone 2: evidence briefing

See **ASSISTANT_GUIDE.md** for the read-only order briefing, source matching, abstention, 8 authored baseline regression cases and optional provider integration. Combined unit tests now total **30** locally. GenAI execution/model quality remain pending; the default still works offline and makes no provider calls. The earlier milestone-1 verification scope above remains historical to that release.

## Milestone 3: offline pipeline

See **PIPELINE_GUIDE.md**. Run `python3 pipeline.py --bundle fixtures --output output/pipeline-demo` for ingest → exact reconciliation → replay check → JSON/HTML reporting. This release has **43 tests** in development. No API credits or credentials are needed. It is custom local orchestration, not Airflow. Earlier milestone counts remain historical; Mac/remote/model evidence boundaries are stated in the guide.
