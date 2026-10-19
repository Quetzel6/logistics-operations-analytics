# Operations decision brief

**Synthetic demonstration. Retrospective selection, not independently validated policy.**
As-of: 2026-10-19 (end-of-day snapshot).

## Decision 1: investigate service reliability first

DC-B / Outer has the lowest observed OTIF, 52.0%, with 9 overdue open orders. Review the order IDs in exceptions.csv and the route filter. Check dispatch timestamps, receiving windows and exception-code accuracy before assigning a cause. The generator deliberately plants extra lateness at DC-B / Outer; recovering this pattern does not establish real operational causality.

## Decision 2: evaluate capacity separately from lateness

At +10% capacity, DC-C / Outer has the highest modeled shortage recovery per added unit: 692 / 2,800 = 24.7%.

| Alternative | Added homogeneous capacity units | Additional recoverable units, upper bound |
|---|---:|---:|
| Target DC-C / Outer only, +10% | 2,800 | 692 |
| All network, +10% | 16,800 | 2,273 |

These alternatives have different coverage and do not recover equal amounts. This ratio is a capacity-absorption measure, **not ROI**. No vehicle count, labor requirement or currency cost is available. The selected cohort is chosen from this same synthetic snapshot; validate on a later independent period before using it as policy.

## Action register

| Priority | Proposed owner role (hypothetical) | Action | Evidence needed before approval |
|---|---|---|---|
| 1 | Dispatch / operations | Inspect oldest open orders at DC-B / Outer | Dispatch and arrival timestamps, receiving constraints, verified cause codes |
| 2 | Transport planning | Assess targeted capacity replay at DC-C / Outer | Stock availability, dimensional loads, loading times, fleet/labor feasibility and costs |
| 3 | Analytics | Compare policy on another period | Independent inputs, fixed metric definitions, baseline and predeclared acceptance criteria |

## What must not be concluded

- Adding capacity guarantees higher OTD or OTIF.
- A network-wide capacity increase is necessary because one cohort has poor delivery service.
- The demonstration proves savings, ROI or production effectiveness.
- Historical shipments can be corrected by a scenario replay.

## Reproduce and inspect

Run `python3 project.py`. Reconcile report.json, daily.csv, exceptions.csv, capacity_scenarios.csv and capacity_stress.csv. Dashboard details and scenario tables use the same report object. `python3 verify_release.py` reruns tests and rebuilds twice in isolated temporary output directories, checks reproducibility and reconciles evidence.
