# Traceable operations data for exception review

## Business question

How can an operations reviewer find the recorded facts behind an order exception without confusing a dispatch with delivery, treating an unverified note as a confirmed cause, or changing operational data?

## Implemented path

Synthetic CSV orders + JSONL events + original text notes enter a contract-validated SQLite loader. Rejected bundles do not partially write business data. Replays leave entities unchanged and retain an audit attempt. The local runner reconciles source rows with storage before producing reports. Order quantities are aggregated at order grain to avoid join inflation.

The read-only briefing returns a bounded evidence draft and a proposal to review records. It executes no operational action. Missing orders and requests for a confirmed root cause abstain. All findings must match a source item exactly, but source matching cannot establish relevance or source truth.

## Reliability improvement discovered in M4

The original baseline retrieved the earliest 20 events and selected the first six evidence items. Routine history could displace the latest exception and consume the space for notes.

M4 retrieves the latest 20 events, presents that window chronologically, selects recent events while retaining an exception in the window, and reserves a note slot when a note is available. Three regression tests cover recent-window behavior, a latest exception after 25 routine events, and an exception followed by routine dispatches. Findings remain limited to six.

This remains bounded retrieval: an exception outside the latest-20 window can be omitted; notes are selected by note ID, not timestamp, and only the first ten are retrieved. Warnings and retrieval_scope make that limit explicit. An event labelled delivered does not prove recipient acceptance. The tool is not a full incident investigation system.

## Evaluation layers

1. Unit/integration checks: ingestion, rollback, replay, source matching, transport error handling, report escaping and read-only behavior.
2. Eight developer-authored baseline regression cases. These are behavior checks, not model accuracy.
3. Eight review-packet cases with authored required evidence and four human criteria. Human judgments start pending and must include reviewer and rationale. No fabricated reviewer scores or time-savings claims.
4. Separate PostgreSQL synthetic query experiment. Its result is pending until Docker execution succeeds. It is not the ingestion backend in this milestone.

## Adoption proposal, not measured impact

An operator reviews the evidence, checks missing/conflicting records, and decides whether to request receiving-window or delivery confirmation through existing procedures. A later pilot could measure review time and missed critical evidence against a manual process on new cases with consent and appropriate data controls. No benefit estimate is reported here.

## Delivery boundary

Local synthetic-data prototype. No successful live LLM execution, autonomous agent, private company integration, production SLA, cloud warehouse, Airflow/dbt deployment or GDPR-compliance claim. The applicant's internship business-analysis work and these personal project experiments are distinct experiences.

## Author verification update: 2026-10-20

The author submitted Mac/Python 3.10.11 output showing 50 tests and eight authored baseline cases passed. The PostgreSQL experiment also passed on the author Mac: 50,000 orders, 200,000 events and 1,000 notes. Median server execution decreased from 5.458 to 0.048 ms across seven samples per arm. The representative plan changed from parallel sequential scanning plus sorting to an index scan using event_order_recent. Results matched the expected four rows; three invalid writes were rejected and the disposable container was removed. Both arms read from cache. This supports this selective-query experiment only.

The author explicitly confirmed reviewing all eight review-packet scenarios and reported no issues. This is qualitative project-owner feedback via conversation. Per-criterion ratings/rationales and timed review measurements were not submitted; decisions.json remains a pending template and must not be presented as completed rubric scoring. No independent evaluation, successful live LLM execution or measured business benefit is established.

AUTHOR_VERIFICATION_M4.json transcribes the supplied key metrics and feedback; it is not the full original PostgreSQL report.
