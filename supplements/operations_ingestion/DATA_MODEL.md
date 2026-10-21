# Operations data model and measured-query plan

This is a normalized operational model, not a completed dimensional warehouse or data lake.

| Table | Grain | Key | Relationship / checks |
| --- | --- | --- | --- |
| orders | one immutable source order | order_id | positive integer quantity; valid source date |
| events | one recorded source event | event_id | many events to one order; validated type and UTC timestamp |
| notes | one original source note | note_id | many notes to one order; original text plus hash in SQLite |
| runs (SQLite ingestion) | one ingestion attempt | run_id | contract, bundle fingerprint, outcome, source provenance |

`orders.quantity` belongs to the order grain. Joining orders to both events and notes can multiply it. Reports aggregate event/note counts separately. Source reconciliation compares each bundle row with storage rather than accepting matching row counts as proof.

## Load contract

The existing loader validates the complete bundle before a transaction writes business rows. Exact replay adds an audit record without adding entities. A changed existing ID rejects instead of overwriting. This prototype has no versioned correction workflow, late-event watermark, CDC or concurrency benchmark.

SQLite and PostgreSQL are separate exercises in this milestone. `postgres_benchmark.py` **does not migrate the SQLite data** or demonstrate incremental PostgreSQL ingestion. It creates fresh synthetic data in a disposable PostgreSQL container to measure a query and validate PostgreSQL constraints.

## PostgreSQL experiment

- 50,000 orders, 200,000 events, 1,000 text notes; known total 2,525,000 units.
- Query: latest events for a single known order, ordered by timestamp and event ID.
- Before arm: primary keys only; no event lookup index on order_id.
- After arm: composite index `(order_id, timestamp_utc DESC, event_id DESC)`.
- PostgreSQL optimizer chooses its own plan. No forced scan/index options.
- One warm-up, seven `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` samples per arm. Report medians plus raw timings and a representative plan.
- Both arms must match an independently specified four-event result hash.
- CHECK and foreign-key constraints are tested by deliberate invalid inserts; only expected PostgreSQL exceptions pass.

Execution Time excludes Docker/connection overhead. Always measuring before then after introduces cache/order effects. There is no randomized crossover, load test, throughput SLA, concurrency test or general speedup claim. The report records PostgreSQL version and container image ID.

## Privacy and security boundaries

Fixtures are synthetic. Free-text notes are untrusted and may contain personal data if real sources are substituted. Do not use real employer/customer documents in this public lab. No PII detector, encryption, retention automation or GDPR certification is implemented. The benchmark publishes no host port and uses a unique disposable container; it does not configure production database roles or migrate cloud infrastructure.

## M5 PostgreSQL ingestion extension

M5 adds [a PostgreSQL backend and pipeline](POSTGRES_GUIDE.md) for the same validated CSV/JSONL/text bundle. This is now real source ingestion into PostgreSQL, distinct from the earlier synthetic M4 benchmark. Dates and timestamps are typed, notes retain their original validated text/hash, and business rows reference their ingestion run. Sixteen integration cases cover transactional rollback, retry, replay, content conflicts, foreign keys, exact reconciliation and cooperating concurrent writers. CI and author Mac acceptance passed; see [author evidence](AUTHOR_VERIFICATION_M5.json). There is no dimensional warehouse, production workload benchmark, database migration or PostgreSQL assistant implementation in this extension.
