# Context selector design before implementation

Status: **implemented as an opt-in experiment; not enabled in the original protocol**.
Live comparison is pending. Decision prompt tuning is paused. See the
[paired-run guide](RAG_CONTEXT_SELECTOR_GUIDE.md) and the [evidence synthesis](RAG_FINDINGS_TH.md) for why an oracle-assisted
reduction cannot be deployed as a retriever or counted as an end-to-end gain.

## Objective and boundaries

Choose bounded context from the existing order-scoped candidate records, using
only the question, application schema and source records. Retain exact original
text for ID validation/materialization. Keep unknown-order gating, read-only
storage, untrusted-note handling, strict validation and mandatory human review.

The selector must not receive case names, expected status, required_ids, answer
values or reports. Runtime code must not import evaluation/diagnostic modules.
Evaluation may inspect references only after collecting outputs. Knowing all
current cases during development limits independence even when runtime APIs
exclude labels; we will explicitly describe this as development work.

## First candidate: field-aware context v1

Start with a deliberately narrow deterministic policy rather than adding another
LLM prompt or a learned reranker before measuring the simpler alternative.

1. Keep the existing order-existence gate and bounded context acquisition.
2. Recognize only unambiguous, single-field questions about **the current order's
   stored quantity or due_date**, using a documented schema-level query contract.
   Return an internal route/field name, never an answerability decision.
3. For a recognized route, retain the one existing kind=order evidence item in
   full. Do not trim the unused field, edit dates/numbers, construct an answer,
   or set supported in application code. The frozen decision call still runs.
4. For everything else, use the original pinned-order plus cosine top-six policy
   unchanged. Preserve note qualifiers, contradictions and original source order.

Suggested API: `select_context(question, candidates, ranked_ids) -> records,
route, rationale`. It receives no database mutation capability, labels, historical
retrieved lists, per-case allowlists or inferred answer values. It returns only
source objects already in candidates. Rationale is an audit enum, not generated
chain-of-thought or content sent as extra instruction to the model.

The recognized-language contract should be fixed before measuring outcomes.
For this initial English-only experiment, candidate grammatical forms are:

- `what [quantity|due date] is recorded for this order`
- `what is the recorded [quantity|due date]`
- `how many units are recorded for this order`

Normalize case, surrounding whitespace and optional terminal question mark only;
do not treat arbitrary occurrence of quantity/date/units as a match. Broader
synonyms are not silently added after looking at evaluation results. The grammar
is an explicit narrow interface, not a claim of general natural-language parsing.
New generic forms require a new selector version and separate validation.

Compound questions, explanations, derived comparisons, damaged/missing units,
multiple orders, explicit different order IDs, conflicting field requests,
unknown fields and unsupported languages fall back to the original context.
Missing/ambiguous order evidence must also fall back or retain the existing gate;
it must never be interpreted as a reason to fabricate a value or bypass inference.
Source schema integrity, not parsing arbitrary note prose, establishes which
fields the order record contains.

This uses schema routing to choose context, **not a keyword override of the model
decision**. No model decision is repaired. The short prompt, absence of decision
format and strict response parser remain fixed for both experiment arms.

## Why not select note:TARGET automatically?

Its name is an authored fixture ID, not a relevance signal. The historical window
ranking puts an irrelevant note ahead of the supporting note; simply keeping the
first note can lose evidence. A shorter note saying no window is recorded can
also share the same query words. Therefore choosing a note from fixture IDs,
special-casing its text, or copying the oracle keep-set is forbidden.

The first candidate deliberately retains top-six fallback for note/event
questions. **It does not yet solve receiving_window.** Its value must be measured,
not assumed from the diagnostic. Independent note-ranking/contradiction handling
is a separate unresolved design question; no automatic context expansion or
oracle-driven fallback is added in v1.

## Software checks required before any live comparison

- Selector output is a subset of the same order's candidates with exact texts.
- Changing IDs/quantities/dates does not change the route or trigger a case rule.
- Labels and evaluation imports are absent from the runtime dependency path.
- Compound/cross-order/unsupported questions use fallback; adversarial note text
  does not control routing. Unknown-order gate makes no model calls.
- Retrieval changes cannot relax citation/duplicate/incomplete-output checks or
  update business data. Every route, ranking score, record ID and input is logged.
- Frozen full-context and historical reports remain byte-identical. Failures and
  interrupted runs preserve requests, responses and observations without retries.

The implementation now has software coverage for these checks; simulated providers
do not establish model semantics. See the paired-run guide for validation scope.

## Full-path comparison plan

Use a new versioned runner and new output directories; do not edit the historical
local_rag_staged.py or its 13/16 report.

| Arm | Decision config | Context policy | Selection/materialization |
|---|---|---|---|
| B: contemporary control | Frozen short system, no decision format | Original cosine top-six with pinned order | Original selection prompt, bounded retrieved-ID schema and exact materialization |
| C: candidate | Identical to B | field-aware-context-v1 | Identical to B |

Both arms run all 16 development cases, including the same application gate.
Compute one candidate embedding/ranking result per case and reuse it for both
arms in the first comparison, so only context selection differs. Do not optimize
away embedding calls for routed fields until after this comparison is complete.
Alternate B-first/C-first by case index, with no adaptive rescheduling or retries.
Decisions and ID selection have no shared conversation/context state between arms.

Capture runtime version, full generation and embedding digests, templates,
parameters, source/prompt/selector hashes, all client HTTP bodies, candidate and
selected records, scores, routing reasons and per-stage counters. Verify model
identity before/after and preserve failures. Effective runtime defaults remain a
stated limitation; a stable model tag is not sufficient identity proof.

Use at most 15 embedding calls shared by arms, 30 decision calls and 30 selection
calls (60 generation calls maximum), plus metadata calls. The earlier design's
46-call figure assumed only answerable cases reached selection; false support
on negative cases can also start selection and must be counted. If all references
are decided correctly, there are 16 selection calls and 46 generation calls.
The unknown-order case
has zero provider calls. Failure handling must distinguish embedding, decision,
selection and validation stages rather than counting errors as abstentions.

Report separately for each arm:

- 8 answerable cases: decision outcome, retrieval reference recall, selected-ID
  coverage and end-to-end reference checks; distinguish false abstention from
  missing/invalid selection.
- 7 model-abstention cases: correct abstention, false support and invalid output.
- 1 application gate: pre-inference handling, excluded from model abstention.
- Extra selected IDs and pending human relevance review, unchanged-database
  checks, request counts and latency. Keep the original permissive extra-ID score
  definition and add clearly named secondary measures without rewriting history.

The comparison B vs C isolates selector behavior under the same decision config.
Comparison to historical long-system/schema 13/16 changes multiple factors and
is descriptive only, especially without full historical runtime attestation.
Oracle-assisted reduced-context outcomes are never a third deployable arm.

## Adoption criteria and independent validation

Do not adopt v1 if it adds false support in any of the seven current negatives,
breaks unknown-order gating/source validation, introduces invalid outputs or loses
reference coverage without a justified improvement. An equal result favors the
simpler existing policy; a development gain alone is not sufficient for general
quality or production claims. Record every per-case difference rather than only
a total. A failure triggers analysis and a new explicit version, not a hidden
keyword exception or a retry until passing.

Before general-quality claims, use separately authored examples not used to
design the matcher: unseen phrasing/order IDs/values, compound questions, missing
facts, negation, conflicting notes and cross-order requests. Freeze the selector
before inspecting these results and keep human semantic review separate from
reference checks. Deterministic repeated observations are not independent samples.

The selector, label-free runtime and paired evaluator are now implemented in
separate modules without modifying the original inference path. No live comparison,
model change or promotion to main has occurred in this implementation milestone.
