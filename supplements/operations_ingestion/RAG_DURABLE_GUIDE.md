# Durable synthetic RAG experiments

This follow-up starts from PR #5 commit `35468f2d34d17363f5b1476dd030318052010a45`.
The [audit](evidence/pr5_audit_35468f2/REPORT_TH.md) precedes implementation.
Its [verification](evidence/pr5_audit_35468f2/verification.json),
[reconstructed requests](evidence/pr5_audit_35468f2/reconstructed_requests.json),
and [offline reproducer](evidence/pr5_audit_35468f2/check_offline.py) are included
so review does not depend on another session's workspace. Source links in the
archived report are relative; the reproducer now finds this checkout and writes
derived outputs into a temporary directory (or a supplied directory).
The archived interruption reproduction targets the preserved original evaluators.

## Storage and recovery

`run_rag_durable.py` is a new runner. Old evaluators, inference modules, prompts,
schemas, reference labels and all five raw Mac reports remain unchanged.
There is no model upgrade, automatic retry, decision override or new quality claim.

Each run requires a new output directory. `events.jsonl` has a flushed and fsynced
line for each prepared request, raw HTTP response and completed case/trial.
Responses are saved before application JSON parsing, including malformed JSON
and HTTP error bodies. Observations are saved immediately, before the final report.
`status.json` is atomically replaced with running/completed/interrupted/failed and
planned/completed observation counts. Completed means execution finished, not
that all reference checks passed.

Ctrl-C and CLI SIGTERM mark interrupted. SIGKILL, host or disk failure cannot
guarantee a finish record: `inspect_rag_run.py` derives incomplete from the journal
and reads completed observations. It explicitly reports a torn final append and
rejects earlier corruption. Journal events take precedence over stale status files.
Use a new directory for another run; no automatic resume or overwrite is supported.
A prepared request without a response has unknown delivery/completion status.

## Capture scope and runtime identity

The live transport stores exact client HTTP request/response **body bytes** as
Base64 plus SHA-256, endpoint, method, prepared headers, timestamps and request IDs.
These are client captures, not TCP packets, delivery proof or the rendered input
after Ollama applies its template. Response reads are bounded at 2,000,001 bytes;
oversized responses are marked truncated and rejected. The runner uses only its
built-in synthetic inputs; artifacts include raw records and need access controls.

Before generation it captures `/api/version`, `/api/tags` with full required-model
digests and `/api/show` including templates/parameters/model information. Missing
identity stops the run; it never downloads models. After observations it captures
`/api/ps` and a second inventory, rejecting identity drift. Metadata responses stay
in the journal even if preflight/postflight fails before report creation. This
brackets tag identity but cannot attest that it did not change and change back
during a request, or reveal all server environment defaults.

Generation retains `temperature=0,num_predict=1600`; no seed or num_ctx is added.
Capture the Ollama host's runtime configuration alongside the run. Inspect actual
prompt_eval_count, done_reason, template, parameters and loaded context information
before attributing failure to truncation. The final report includes source hashes,
model names and the frozen prompt hash. Injected providers have mock_only execution
and mock_request/mock_response events; these cannot establish live model behavior.

## First live experiment: one-record due date

On the Mac with the original installed Ollama/models, from
`supplements/operations_ingestion`:

```bash
python3 verify.py
python3 run_rag_durable.py --protocol due-date --allow-local \
  --output evidence/due_date_capture_mac_01
python3 inspect_rag_run.py --directory evidence/due_date_capture_mac_01
```

The default model is qwen2.5:3b; inventory verifies full digest rather than assuming
tag equality establishes identity. There is exactly one generation, no embeddings
or ID selection, after metadata preflight. System prompt/schema/options/question
match the frozen diagnostic, with only `Order T204; due_date=2026-12-06; quantity=73.`.
This reference-assisted input is a diagnostic, not deployable retrieval or a new
end-to-end score. Inspect its capture before changing a single factor such as
structured-output format in another versioned experiment.

After inspecting that capture, the [one-call format diagnostic](RAG_FORMAT_DIAGNOSTIC.md)
can remove only format while validating runtime identity against the original run.

Optional subsequent runs use the same durable storage:

```bash
python3 run_rag_durable.py --protocol context --allow-local \
  --output evidence/context_capture_mac_01
python3 run_rag_durable.py --protocol staged --allow-local \
  --output evidence/staged_capture_mac_01
```

Context runs all 24 trials. Staged runs 16 cases with original fixtures, retrieval,
scoring and separate answerable/model-abstention/application-gate totals. Staged
exit 1 on incomplete reference checks is intentional; decision-only exit 1 means
failed calls, whereas valid insufficient is an observation and exits 0.
Missing opt-in or existing output stops before provider calls.

## Validation and remaining limit

Tests cover interrupted staged/context runs, SIGKILL, partial tails, exact Unicode
request bodies, malformed/HTTP-error response retention, journal failure before
dispatch, metadata/identity checks, old output preservation and frozen hashes.
Simulated HTTP tests validate the client, not Ollama semantics.

This cloud workspace has no Ollama CLI and loopback port 11434 refused the readiness
request. No live generation or model installation was performed. The three
historical false abstentions remain unexplained.
