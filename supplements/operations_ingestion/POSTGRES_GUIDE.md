# M5: PostgreSQL ingestion and reporting

## Scope

The existing contract validator now feeds a PostgreSQL backend, separate from the default SQLite CLI and the M4 synthetic query benchmark. CSV orders, JSONL events and original text notes are loaded into `ops_ingestion_lab` with typed dates/timestamps, foreign keys, positive quantities, raw-note hashes and source-run provenance.

This is an append-only lab, not a warehouse/lake, factory connector, API extractor, production scheduler or GenAI system. The PostgreSQL report does not invoke the existing SQLite assistant. Original SQLite commands continue to work without installing a PostgreSQL driver.

## Transaction and replay boundaries

- Whole-bundle file validation runs before business loading.
- Schema creation is allowed only if the fixed schema does not exist. An existing schema must contain the exact ownership marker. This is a workflow guard, not a security boundary; use a dedicated lab database and a role authorized only for that lab.
- A transaction advisory lock serializes this backend's cooperating writers, including concurrent exact replays. External writers do not have to respect that lock.
- Run placeholder and all new business rows share one transaction. A relational failure, content conflict or injected failure rolls them back together. A separate rejection audit remains.
- Exact bundle replay appends a duplicate audit, without changing business rows. A changed bundle containing identical entities skips those entities. A changed existing ID rejects; corrections require a future versioning policy.
- Reconciliation compares every source row, including note text/hash, in a repeatable-read read-only transaction. Report aggregates preserve order grain.
- Ingestion can commit before a downstream reconciliation/report failure. That later failure does not undo the load. Fix the cause and replay safely.

The SQL identifiers are fixed internal constants; values use psycopg parameters. DSNs come from environment variables, are not CLI arguments and are not written to stage evidence. Read-only transactions do not imply a separately provisioned read-only database role. The driver has connect, statement and lock timeouts. Logs omit raw notes; IDs and paths can still be sensitive.

## Mac: one disposable Docker acceptance

Use Python 3.10+ and Docker Desktop. From `supplements/operations_ingestion`:

```bash
python3 -m venv .venv-pg
source .venv-pg/bin/activate
python3 -m pip install -r requirements-postgres.txt
python3 verify_postgres.py --output output/mac-m5-postgres-01
```

The runner pulls PostgreSQL 16, creates its own container and database on a random localhost-only port, runs real integration tests, executes the pipeline twice, saves reports, and removes only that container. It never uses an existing Compose volume, your current PostgreSQL password or a remote model. Progress is printed during image setup and test execution. If rerunning, use a new output directory so earlier evidence is preserved.

Success requires:

- 16 real integration tests, no skips.
- Ingestion committed, exact reconciliation passed, replay unchanged, JSON/HTML report created.
- Second pipeline load is duplicate; 3 orders, 3 events, 2 notes and total quantity 225.
- `container_removed=true` in `postgres_runner.json`.

Reports are nested under `output/mac-m5-postgres-01/evidence/demo/runs/`. They are static HTML; opening them needs no service or credentials. The source includes synthetic notes only.

## CI and explicit disposable test databases

CI provisions a disposable PostgreSQL service and sets `OPERATIONS_TEST_DSN` for `postgres_acceptance.py`. Tests intentionally reset the complete `ops_ingestion_lab` schema. They refuse database names without the `operations_test_` prefix. **Never set this variable to an existing business database.** The prefix is an extra guard, not proof that a database is disposable.

```bash
# CI only, after explicitly provisioning a disposable operations_test_* database
python postgres_acceptance.py --output output/ci-postgres-ingestion
```

Normal non-test usage uses `OPERATIONS_DATABASE_URL` with a dedicated lab database:

```bash
python postgres_pipeline.py --bundle fixtures --output output/postgres-demo
```

Set credentials privately in your shell environment; do not commit them. The loader creates no roles, TLS policy, encryption, retention rules or GDPR controls. Do not expose it as an untrusted multi-user upload service. Throughput/large-bundle performance is not measured; the row-wise loader is intended for this small prototype.

## Verification status at implementation

The 50 original offline tests passed on the development Linux host. The new source compiles with psycopg 3.3.6 installed. This host has no Docker/PostgreSQL server; real PostgreSQL verification must come from the new CI job or author Mac acceptance. A passing M4 benchmark does not verify this new backend. CI and Mac results will be recorded only after actual runs.

## First real CI result

[CI run 39534839501](https://github.com/Quetzel6/logistics-operations-analytics/actions/runs/39534839501) passed on commit `165397a28ae71aae3cbdf1c12c7f83f995bf02ed`: all 16 real PostgreSQL integration tests and the repeated pipeline passed on Python 3.10 and 3.13. The original 50 offline tests, baseline regressions, M4 PostgreSQL benchmark and existing logistics validation also passed. These are GitHub Linux results, not author Mac execution. The Docker acceptance wrapper is checked separately after this result.
