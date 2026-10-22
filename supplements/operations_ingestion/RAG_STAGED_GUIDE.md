# Two-stage evidence review

The preceding ID-selection v2 Mac report passed 7/8 original cases and 4/8 newer
cases. Four failures returned `abstained` with nonempty IDs; one falsely abstained
on an available quantity. The application correctly rejected contradictory outputs.
The raw report is preserved at
[evidence/local_rag_ids_v2_mac/report.json](evidence/local_rag_ids_v2_mac/report.json).
SHA-256: `444bfe6684fc40f553f5b81f08c352da9f556886304c47ced5e0e220acb30813`.
All five recorded source hashes match the implementation at commit
`ccfa9c508635d0f70ec9c5363ed493228d99464e`. This is an owner-supplied Mac artifact,
not independent machine attestation. Pending human-review labels remain intact.

## Protocol

1. Retrieve the same bounded six records, including the order record, using the
   existing embedding/ranking logic.
2. Ask only for `decision`: `supported` or `insufficient`. Reject extra fields,
   invalid values, malformed/incomplete JSON, and duplicate JSON keys.
3. For `insufficient`, construct an empty abstention and stop. This is the defined
   contract of the decision-only call, not a repair of an old contradictory answer.
4. For `supported`, make a separate call to select IDs from the same records.
   Reject empty, duplicate, foreign, unselected IDs and extra fields. Copy source
   text with the existing validated renderer. Never execute actions.

The second-call schema enumerates retrieved IDs; application validation remains
mandatory. There is no retry, silent deduplication, hard-coded quantity answer, or
keyword override of the model's decision. The first-stage model can still falsely
abstain or accept insufficient evidence. The selector can still choose irrelevant
valid IDs. This is not an independent semantic verifier.

The implementation reuses the existing transport, vector validation, cosine
function, context loader and source renderer. Earlier implementations remain
unchanged for reproduction. Prompt text and call structure change together, so
results cannot isolate the effect of either change alone.

## Reproduce once on the existing Mac checkout

Update the repository using `git pull --ff-only`, then from
`supplements/operations_ingestion`:

```bash
python3 verify.py
python3 evaluate_rag_staged.py \
  --embedding-model nomic-embed-text:v1.5 \
  --model qwen2.5:3b \
  --allow-local \
  --output output/rag-staged-mac-01
open output/rag-staged-mac-01/report.html
```

Keep `report.json` and `ollama list` output. An existing output directory is
rejected before inference. A nonzero evaluation exit can mean failed checks;
inspect and retain the report. No paid API or model download is performed.

The 16 questions and data are unchanged. Both cohorts are now development cases:
`regression` contains the original eight, and `prior_new_cases` contains the eight
previously introduced cases. Neither cohort is held out. Interpret each group's
answerable and model-abstention counts separately. The unknown-order application
gate is also reported separately. Source hashes and both fixture fingerprints
are recorded, as are raw synthetic outputs for each generation stage.

Successful unknown-order handling uses zero model calls; an insufficient decision
uses one generation call; a supported decision uses two. `generation_requests`
counts actual attempted calls, including failures, not cases. Up to 30 generation
calls are possible for this fixture. A second call may add latency; no speedup claim.
Failures carry `failure_stage`; no accepted completion is fabricated after failure.

## Verification and next decision

92 software tests and SQLite acceptance pass locally on Linux/Python 3.12.14,
including 12 tests for stage routing, exact source text, invalid/duplicate IDs,
malformed decisions, incomplete responses, stage failures, no retries, read-only
behavior and honest mock reporting. CLI JSON/HTML creation, failed-check exit and
no-overwrite behavior were also checked without model calls. These checks establish
software behavior, not model quality. Live Mac results are pending.

Evaluate whether contradictory abstentions disappear under the new contract and
whether the available quantity is selected correctly. Retain any false decisions
as failures. If decision errors persist, compare model capability under a fixed
protocol rather than repeatedly modifying rules to fit individual questions.
Independent new-case evaluation and criterion-level human review remain necessary
before making broader quality claims. This is a portfolio prototype.
