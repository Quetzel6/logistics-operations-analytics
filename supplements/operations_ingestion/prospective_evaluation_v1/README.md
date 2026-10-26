# Prospective developer-authored generalization set v1

Status: frozen data prepared after candidate commit
`b9714367510bdd5f3175b2f3c2642d87364e6a3d`; **no model run yet**.
This is not an independent/secret held-out benchmark. The same assistant authored
it after the original development results, and labels are intentionally visible
for reference review before any model evaluation.

- bundle.json: six new synthetic orders, events and notes. No reference labels are
  stored in source notes or runtime selection parameters.
- cases.json: sixteen evaluation-only questions and authored references: eight
  answerable, seven known-order abstentions, one unknown-order application gate.
- manifest.json: data and frozen runtime SHA-256 values, model identities/options,
  creation timestamp and scope. These record provenance, not independent attestation.
- reference_review.json: empty reviewer/kind and pending ratings; no human judgment
  or AI review has been fabricated.

All question strings and order IDs differ from the old 16 cases. Two questions
use the predeclared field grammar; fourteen exercise fallback/gating, including
unseen paraphrases, a compound field question, missing measured facts, qualified
quantities, a cross-order request and unconfirmed alternative appointments. This
composition is explicit, not a claim of representative real-world sampling.
Future dates are fixed synthetic values; they are not relative to today's date.

From operations_ingestion:

```bash
python3 prospective_dataset.py verify
python3 prospective_dataset.py build --directory /path/to/new-synthetic-bundle
```

Both commands make zero provider calls. verify checks frozen file hashes, performs
temporary SQLite ingestion and confirms reference IDs exist in each order's
candidate evidence and that case counts are 8/7/1. It does not prove semantic
reference correctness, guarantee retrieval recall or execute the paired model run.
build never overwrites an existing directory and writes source data only, without
expected labels. Do not use the old evaluate_context_selector.py command expecting
it to run these cases; that runner still uses the original development fixtures.

Before the first model run, review the references against source records and keep
the candidate fixed. If references need correction, version the data/manifest
before model execution rather than silently changing them after results arrive.
AI review must be labeled ai; human reference review remains pending until an
actual human assessment is recorded. The separate future evaluator must use
references only after collecting runtime outputs and report new-cohort results
separately from the 11/16, 14/16 and historical 13/16 development observations.
