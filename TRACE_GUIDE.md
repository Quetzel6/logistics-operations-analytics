# Trace a synthetic KPI to orders

Run `python3 trace_demo.py` for a repeatable, in-memory example: order A is on time and complete; B is open and short. The SQLite primary key rejects a duplicate B. A separately supplied corrected snapshot for B moves OTIF from 50% to 100% and unit fill from 75% to 100%; B leaves the exception list. Recomputing the same snapshot gives identical results. This is a demonstration of correction, not automatic resolution of conflicting records or a production workflow.

Run `python3 project.py --output /tmp/logistics-trace` to generate `kpi_trace.csv`. Each due order includes its trip, cohort, due date, snapshot-visible delivery, ordered and shipped units, on-time and OTIF flags, and exception flags. Sum OTIF flags and divide by row count; sum shipped units and divide by ordered units to independently check report totals. Filter by warehouse and route to reconcile cohorts, then join order_id to `orders.csv` and trip_id to `trips.csv` for source rows. A delivery after the snapshot is shown as blank in the trace; consult `orders.csv` for its original date. Future-due orders are excluded. Trip utilization has a different dispatch window and cannot be reconciled from this due-order trace. The existing whole-snapshot quality gate rejects capacity and date violations; it does not quarantine individual records. The data are synthetic.

Run from the repository root with Python 3.10+:

```bash
python3 -m unittest discover -s tests -q
node tests/test_dashboard.cjs
python3 trace_demo.py
trace_output=$(mktemp -d)
python3 project.py --output "$trace_output"
python3 verify_release.py
```

The build output is isolated by `mktemp`. `verify_release.py` also builds twice in temporary directories, verifies byte equality including `kpi_trace.csv`, checks its due-order scope, cohort contributions and exception membership, and writes `output/release_verification.json`. This last file is generated evidence: review its diff separately and do not include it in a source-only PR. CSV boolean flags are the strings `True` and `False`; count `True` values rather than treating both strings as truthy.

The separate ingestion regression suite is `(cd supplements/operations_ingestion && python3 -m unittest discover -s tests -q)`. Its test files are distinct from root `tests/`. `verify_release.py` reruns the root suite, so that execution is not additional test coverage. No RAG model calls are needed.
