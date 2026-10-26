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

## Next: the two other historical false abstentions

The owner-supplied eight-case capture returned insufficient for all seven
negative cases and supported for the reduced due-date positive. Offline review
verified raw HTTP replies, unchanged short prompt/options/model identity, and the
historical negative record lists. This is encouraging development evidence, not
an end-to-end improvement or a held-out accuracy result.

The `false-abstentions` suite uses that same short system and no format to test:

| Case | Historical input | Expected decision |
|---|---|---|
| receiving_window | All six retrieved records, including note:TARGET | supported |
| quantity_with_cause_context | All six retrieved records, including order:T201 | supported |

It sends each original question and the exact original retrieved records in the
same order, **without context reduction**, a new embedding call or reference
labels in requests. The order is receiving_window then quantity. There are exactly
two decision calls, no selection and no retry. The short-system capture continues
to supply the frozen prompt/request configuration and runtime identity baseline.

```bash
git pull --ff-only
python3 verify.py
python3 diagnose_rag_abstention.py \
  --suite false-abstentions \
  --baseline-capture evidence/due_date_short_system_mac_01 \
  --allow-local \
  --output evidence/short_system_false_abstentions_mac_01
python3 inspect_rag_run.py --directory evidence/short_system_false_abstentions_mac_01
zip -r evidence/short_system_false_abstentions_mac_01_handoff.zip \
  evidence/short_system_false_abstentions_mac_01
```

Run once on the same fix branch, from operations_ingestion, after software tests
pass. Preserve all prior directories. Runtime mismatch, interruption and parse
failures follow the same durable-storage behavior as the eight-case suite.
The report's historical key `positive_control` counts both positive cases (count=2);
negative_controls has count=0. A valid insufficient is a false abstention for these
two references, not a successful abstention. No prompt change is made mid-batch.

This checks whether the **short-prompt/no-format configuration** handles these
cases with full retrieved context. The historical staged baseline used the long
prompt with schema, so a difference for these cases alone would not isolate
prompt from schema effects. Only the earlier due-date comparisons changed one
field at a time. Regardless of outcome, the historical 13/16 reference-check
result remains unchanged until a separately versioned full evaluation is run.

## Records-only reduction under the same short prompt

The owner supplied a completed full-context capture where both cases again
returned insufficient with HTTP 200 and done=true/stop. Offline review verified
the exact six records per case, unchanged short prompt/options and matching
runtime identity. Therefore shortening the prompt alone is not an observed fix
for these two full-context inputs.

The `reduced-false-abstentions` suite now changes only the nested records list
relative to each **actual captured short-system full-context request**. It requires
both that full-context capture and the same short-system due-date capture used
as its baseline. Hashes establish the baseline chain; preflight validates runtime
version, digest and model configuration before any generation. The full capture's
HTTP body hashes and report/response agreement are checked as well.

| Case | Full records | Reduced records retained unchanged |
|---|---:|---|
| receiving_window | 6 | order:C101 and note:TARGET (2) |
| quantity_with_cause_context | 6 | order:T201 (1) |

These are the original reference-assisted reduced contexts from
diagnose_rag_context.py, not newly selected or edited source texts. All retained
records and their order are preserved. Question, system, model, stream, options
and the absence of format must match the full requests; each comparison is
journaled before dispatch. Expected labels remain outside requests. There are
exactly two generation calls, no embeddings, selection, retry or mid-run tuning.

From operations_ingestion on the existing fix branch:

```bash
git pull --ff-only
python3 verify.py
python3 diagnose_rag_abstention.py \
  --suite reduced-false-abstentions \
  --baseline-capture evidence/due_date_short_system_mac_01 \
  --full-context-capture evidence/short_system_false_abstentions_mac_01 \
  --allow-local \
  --output evidence/short_system_reduced_mac_01
python3 inspect_rag_run.py --directory evidence/short_system_reduced_mac_01
zip -r evidence/short_system_reduced_mac_01_handoff.zip \
  evidence/short_system_reduced_mac_01
```

Run once after software checks pass. Keep both baseline directories and every
older run. Missing/mismatched full capture stops before provider calls. A valid
insufficient is recorded as false abstention for these references; exit 1 may
reflect that outcome rather than a transport error. Preserve and inspect raw
outputs instead of repairing or retrying them.

This isolates a records-list change within the recorded request fields under a
fixed short prompt. An observed change would support context sensitivity for
that case, without identifying a particular distractor or length mechanism.
Trials occur on separate occasions and not all effective runtime defaults are
observable. The reduction uses reference IDs, so it is diagnostic, not a proposed
deployable retriever. No outcome changes the historical 13/16 reference checks.
