# Resume evidence and interview notes

## Project title
Logistics Operations Analytics | Python, SQL/SQLite, JavaScript | Synthetic portfolio

## Evidence-based bullets
- Built an offline logistics analytics workflow for 1,339 synthetic orders and 168 trips, with order-level exceptions, warehouse/route KPIs and daily delivery views.
- Separated service reliability investigation from capacity scenario replay; compared targeted and network-wide capacity changes under explicit stock, labor and routing assumptions.
- Verified 14 automated Python tests, independent CSV-to-SQL KPI reconciliation and two clean reproducible builds; added JavaScript filtering checks.

GitHub Actions workflow is prepared but has **not run remotely yet**. Add a CI claim only after observing a successful run. Browser visual checks on the updated tabbed dashboard remain pending author review.

## What the author has demonstrated so far
The author correctly calculated OTD 80% and OTIF 70% in the 10-order exercise and explained why low OTIF does not prove a capacity bottleneck. Discussion refined the distinction between observed problems, hypothetical causes and validated decisions. This is a limited understanding check, not proof of independent implementation of every module.

## Tell the story
Business question → data grain and joins → metric contract → hand-calculated tests → exception drill-down → scenario assumptions → independent validation needed.

No claim of real logistics cost savings, vehicle optimization, deployed OMS, live company data or Power BI implementation is supported by this repository. Report synthetic generation and AI-assisted development accurately when asked.
