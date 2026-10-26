# Paired full-path context selector experiment

This implements the [frozen selector design](RAG_CONTEXT_SELECTION_DESIGN.md)
without changing the historical inference modules/evaluators or five raw reports.
No model upgrade or prompt tuning is included. The short decision prompt's bytes
are unchanged from the supplied Mac capture; it now lives in a label-free runtime
module rather than being defined in a diagnostic module.

## Runtime behavior

`context_selector.py` recognizes exactly the five documented English single-field
question forms. For quantity/due_date it retains the complete original order
record. Other questions, compound requests and explicit order IDs use the original
pinned-order/cosine-top-six fallback. Missing or ambiguous order evidence does
not activate the field route. Notes cannot supply routing instructions.

The selector receives only question, candidate records and ranked IDs. Its runtime
dependency graph excludes evaluators/diagnostics and reference labels. It returns
existing source objects, a route and an audit reason, never supported/insufficient.
`rag_context_runtime.py` still asks the model for a decision. An insufficient is
not overridden, even after routing a field question to the order record.

Unknown orders are gated before inference. For known orders, a supported decision
starts the original selection prompt with an enum of retrieved IDs. The same
retrieved context is used for decision and selection. Strict duplicate-key,
completion, membership/count/uniqueness checks and exact materialization remain.
Decision requests omit format; selection requests retain the original ID schema.

The candidate deliberately does not improve note ranking. Receiving_window may
still fail; no code selects a note using a fixture ID or a reference keep-set.

## Paired runner

`evaluate_context_selector.py` evaluates all 16 authored development cases in
each arm, with 32 durable arm observations:

- **B (control):** frozen short system/no decision format, original top-six context.
- **C (candidate):** identical decision/selection settings, field-aware-context-v1.

Both arms share one live embedding/ranking result per known-order case. Candidate
records, every cosine score, selected context/route and HTTP bodies are captured.
B runs first on even case indices, C first on odd indices. There are no shared
conversation-context fields or automatic retries. Expected labels are scored only
after both raw arm outputs have been recorded; they are never passed to runtime
selection or generation. Failures have explicit retrieval/context-selection/
decision/selection/validation stages. A false-support decision remains visible
even if subsequent ID validation fails.

Runtime preflight checks generation version/digest/template/configuration against
the completed short-system capture, and embedding digest against its inventory.
It also captures the embedding model's current show metadata. Model identity is
checked again afterward. Effective server defaults remain a limitation. Missing
models or mismatched identities stop before inference; no downloads are performed.

**Call budget:** at most 15 shared embedding calls, 30 decisions and 30 selections,
or **60 generation calls maximum**, plus metadata. The 46-generation figure in the
initial design assumed all negative decisions were correct; false support can
cause up to 14 additional selections. A simulated always-supported provider tests
the full 60-call bound. The unknown-order case makes zero per-case provider calls.

## Run once on the same Mac

From operations_ingestion on `fix/rag-durable-evidence-20261022` with Ollama running:

```bash
git pull --ff-only
python3 verify.py
python3 evaluate_context_selector.py \
  --baseline-capture evidence/due_date_short_system_mac_01 \
  --allow-local \
  --output evidence/context_selector_pair_mac_01
python3 inspect_rag_run.py --directory evidence/context_selector_pair_mac_01
zip -r evidence/context_selector_pair_mac_01_handoff.zip \
  evidence/context_selector_pair_mac_01
```

The run uses the original installed qwen2.5:3b and nomic-embed-text:v1.5 inventory
identities. Keep the existing baseline directory and all prior outputs intact.
Use a new output directory; interrupted runs are not overwritten or resumed.

Exit 1 may simply mean an arm did not pass all 16 reference checks. Inspect/share
that result; do not rerun until a passing score appears. Completed means execution
finished, not quality passed. `events.jsonl` retains arm outputs immediately;
case_scored events follow only after both outputs exist. An interruption can
therefore leave a durable unscored arm observation for later review.

## Interpretation and limits

`report.json` separates for **each arm** 8 answerable, 7 model-abstention and
1 application-gate cases, along with reference coverage, exact-required-ID
secondary checks, extra selected IDs, stage/error counts and request counts.
The original permissive reference scorer still permits extra evidence when
required IDs are covered. Exact IDs are not a semantic truth or relevance check;
human review remains pending. Retrieval failure is not successful abstention.

B vs C is a contemporary selector comparison under identical prompt/settings.
Do not compare C to historical 13/16 as if only retrieval changed: that older run
used a different system and decision schema, with incomplete runtime identity.
Historical results remain unchanged. Both arms are development cases already
seen during design, not held-out evaluation or production-quality evidence.
No automatic adoption or merge is performed; first inspect per-case regressions,
negative false support, gate behavior and invalid outputs. General-quality claims
need independent examples frozen before inspecting results.

Software verification covers runtime dependency isolation, source/ID preservation,
grammar fallbacks, untrusted notes, strict response/ID validation, shared ranking,
both 16-case arms, worst-case counts, interruption, model drift and read-only
databases. All model behavior in these tests is simulated. No cloud live generation
was performed; the actual paired Mac result is pending.
