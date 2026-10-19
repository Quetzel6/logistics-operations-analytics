"""Evidence-linked operational interpretation; retrospective synthetic demo only."""

def decision_summary(report):
    worst=min(report['cohorts'],key=lambda c:c['otif_rate'])
    candidates=[s for s in report['capacity_scenarios'] if s['scope']!='All network' and s['capacity_increment_pct']==10 and s['added_capacity_units']>0]
    best=max(candidates,key=lambda s:s['incremental_recoverable_units']/s['added_capacity_units'])
    network=next(s for s in report['capacity_scenarios'] if s['scope']=='All network' and s['capacity_increment_pct']==10)
    return {'service_priority':worst['warehouse']+' / '+worst['route'],
            'service_otif':worst['otif_rate'],'service_overdue_open':worst['overdue_open'],
            'capacity_candidate':best['scope'],'candidate_added_units':best['added_capacity_units'],
            'candidate_recoverable_upper_bound':best['incremental_recoverable_units'],
            'candidate_recovery_per_added_unit':best['incremental_recoverable_units']/best['added_capacity_units'],
            'network_added_units':network['added_capacity_units'],
            'network_recoverable_upper_bound':network['incremental_recoverable_units']}

def markdown(report):
    s=decision_summary(report)
    return f'''# Operations decision brief

**Synthetic demonstration. Retrospective selection, not independently validated policy.**
As-of: {report['as_of']} (end-of-day snapshot).

## Decision 1: investigate service reliability first

{s['service_priority']} has the lowest observed OTIF, {s['service_otif']:.1%}, with {s['service_overdue_open']} overdue open orders. Review the order IDs in exceptions.csv and the route filter. Check dispatch timestamps, receiving windows and exception-code accuracy before assigning a cause. The generator deliberately plants extra lateness at DC-B / Outer; recovering this pattern does not establish real operational causality.

## Decision 2: evaluate capacity separately from lateness

At +10% capacity, {s['capacity_candidate']} has the highest modeled shortage recovery per added unit: {s['candidate_recoverable_upper_bound']:,} / {s['candidate_added_units']:,} = {s['candidate_recovery_per_added_unit']:.1%}.

| Alternative | Added homogeneous capacity units | Additional recoverable units, upper bound |
|---|---:|---:|
| Target {s['capacity_candidate']} only, +10% | {s['candidate_added_units']:,} | {s['candidate_recoverable_upper_bound']:,} |
| All network, +10% | {s['network_added_units']:,} | {s['network_recoverable_upper_bound']:,} |

These alternatives have different coverage and do not recover equal amounts. This ratio is a capacity-absorption measure, **not ROI**. No vehicle count, labor requirement or currency cost is available. The selected cohort is chosen from this same synthetic snapshot; validate on a later independent period before using it as policy.

## Action register

| Priority | Proposed owner role (hypothetical) | Action | Evidence needed before approval |
|---|---|---|---|
| 1 | Dispatch / operations | Inspect oldest open orders at {s['service_priority']} | Dispatch and arrival timestamps, receiving constraints, verified cause codes |
| 2 | Transport planning | Assess targeted capacity replay at {s['capacity_candidate']} | Stock availability, dimensional loads, loading times, fleet/labor feasibility and costs |
| 3 | Analytics | Compare policy on another period | Independent inputs, fixed metric definitions, baseline and predeclared acceptance criteria |

## What must not be concluded

- Adding capacity guarantees higher OTD or OTIF.
- A network-wide capacity increase is necessary because one cohort has poor delivery service.
- The demonstration proves savings, ROI or production effectiveness.
- Historical shipments can be corrected by a scenario replay.

## Reproduce and inspect

Run `python3 project.py`. Reconcile report.json, daily.csv, exceptions.csv, capacity_scenarios.csv and capacity_stress.csv. Dashboard details and scenario tables use the same report object. `python3 verify_release.py` reruns tests and rebuilds twice in isolated temporary output directories, checks reproducibility and reconciles evidence.
'''
