# Short-system abstention controls

The owner-supplied short-system due-date capture returned supported, whereas the
long-system captures with and without format returned insufficient. Comparison
verified that the last two requests differed only in system, with identical
runtime metadata and model inventories. This supports prompt sensitivity for that
observed case. It does not prove which wording/length caused the change, improve
the old 13/16 end-to-end reference checks, or establish general model quality.

Before adopting the short prompt, check whether it simply accepts everything.
`diagnose_rag_abstention.py` fixes the same SHORT_DECISION_PROMPT and absence of
format, then runs exactly **eight** sequential decision calls:

| Case | Requested fact absent/unverified | Expected decision |
|---|---|---|
| unconfirmed_cause | Confirmed receiving-delay cause | insufficient |
| dispatch_only | Customer acceptance time from dispatch-only data | insufficient |
| missing_history | Transport exception without event history | insufficient |
| foreign_order | Another order's receiving window | insufficient |
| cause_still_unknown | Verified cause where note says unverified | insufficient |
| estimate_not_acceptance | Actual signature time from an arrival estimate | insufficient |
| missing_weight | Measured weight absent from records | insufficient |
| due_date_reduced_positive_control | Recorded due date in the single order | supported |

The seven negative questions and exact retrieved record lists come from the
preserved original staged report, whose hash and recorded source hashes are
verified. No embeddings are recalculated. The eighth input is the exact reduced
positive payload from the supplied short-system capture. Reference labels/group
names appear only in the journal and scoring, never in the model request.
Unknown-order application gating is excluded, not counted as model abstention.

This is decision-only on previously observed development cases. It bypasses new
retrieval, ID selection, source-text display and full evaluation. Negative context
is the historical full retrieved list; the positive is its previously tested
single-record context, so this is not a balanced or held-out quality estimate.
No prompt tuning, retries, repairs or model changes occur during the batch.

## Run once

From `supplements/operations_ingestion` on branch
`fix/rag-durable-evidence-20261022`, with the same Ollama installation running:

```bash
git pull --ff-only
python3 verify.py
python3 diagnose_rag_abstention.py \
  --baseline-capture evidence/due_date_short_system_mac_01 \
  --allow-local \
  --output evidence/short_system_abstention_mac_01
python3 inspect_rag_run.py --directory evidence/short_system_abstention_mac_01
zip -r evidence/short_system_abstention_mac_01_handoff.zip \
  evidence/short_system_abstention_mac_01
```

Only a complete live short-system capture is accepted as baseline. Before
generation the runner validates baseline bodies, question/records/options/prompt,
runtime version, full model digest and template/configuration. A mismatch stops
before inference. It saves every request/response and completed observation with
the same durable transport and records source, baseline-file and short-prompt
hashes. Postflight checks model identity again. Existing output is rejected; never
delete a partial run to hide it. Retain all earlier runs without modification.

The final report separately counts negative correct_insufficient, false_support,
and failed, plus positive correct_supported/false_abstention/failed. Parse errors
are retained and require raw-output review rather than semantic guessing. Exit 1
can mean a valid decision disagreed with its reference, not a transport failure.
Inspect and share that run; do not rerun to obtain a passing result. Interrupted
runs remain readable via inspect_rag_run.py.

Passing seven negatives would support retaining abstention on these selected
cases, not a general safety/accuracy guarantee. Failing one is a visible tradeoff
to investigate before adopting the prompt. Do not merge the prompt into the
original protocol or change historical scores based on this batch.

Software tests exercise always-supported and always-insufficient providers,
malformed outputs, exact frozen prompt/options, no reference-label fields in
requests, exactly eight calls, runtime mismatch, interruption and old-directory
preservation. These tests use simulated HTTP, not real model judgments.
