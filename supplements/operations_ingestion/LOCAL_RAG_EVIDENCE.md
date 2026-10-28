# Local LLM development evidence

Provenance: manually transcribed summary of terminal outputs supplied by the
project author on 21-22 October 2026. Original output files were not uploaded;
this is not a byte-for-byte archive or independently attested host record.

## Environment reported

- macOS / Darwin, Python 3.10.11
- Ollama 0.40.7
- Generator qwen2.5:3b, displayed model ID 357c53fb659c
- Embeddings nomic-embed-text:v1.5, displayed model ID 0a109f422b47
- Synthetic fixtures: 3 orders, 3 events, 2 notes
- Fixture fingerprint bc1ea299c0203c3038522d27c1e1df45e428d9717e3911e4c2f6b07c008ee1ed

## Development history (failures retained)

| Revision | Exception question | Unknown order | Confirmed root cause question |
| --- | --- | --- | --- |
| v1 | Valid E002 quotation; 12366.18 ms | Application abstained, no inference | Rejected: quote_mismatch |
| v2 and diagnostic build | Rejected: invalid_abstention | Application abstained, no inference | Rejected: invalid_abstention |
| v3 | review_draft, exact E002 quotation; 3438.75 ms | Application abstained, no inference | Model abstained, empty findings; 558.46 ms |

V2 raw outputs selected status=abstained while retaining nonempty findings.
Inspection also identified contradictory inherited prompt instructions. V3 uses
one decision contract. Validation was not relaxed; no status rewriting, quote
trimming or hidden retries were added.

V3 prompt SHA-256:
`bd7f7de8ee0f649473642b44c849c6dc61dbaf101b4d73d36e1bb37d2e2d8ea3`

Manual inspection of the supplied transcript: E002 records an exception, and
the note explicitly says its cause is unverified; the two known-order outcomes
are consistent with those sources. This is an assisted review of a transcript,
not a completed independent human-rating exercise. The generated report's
`human_review: pending` is not changed retrospectively.

## Boundaries

These three authored cases were used to debug the prompt. They are development
regressions, not held-out evaluation or 100% model accuracy. Only two cases invoke
models. All four candidate records fit into context: ranking improvement has
not been established. Timings are single observations, not speed comparisons.
No model training, object detection, production deployment, persistent vector
database or autonomous agent is demonstrated. General semantic sufficiency,
prompt-injection resistance and business value remain unmeasured.

62 unit/regression tests passed on Linux Python 3.12.14 for the v3 extension.
These use mock model responses; the author-run live transcript is separate.
Remote CI status must be checked on the PR commit, not inferred from this run.
