# Evidence briefing — milestone 2

## What is available

A deterministic retrieval baseline and optional OpenAI Responses adapter now build an order briefing from the milestone-1 database. The application retrieves one explicit order and its events/notes, keeps database access read-only, and exposes source IDs. This is a bounded decision-support prototype, not an autonomous agent.

The original milestone-2 check covered 30 tests and eight authored baseline cases. Later local/Mac and CI verification is recorded in [the current project overview](../../README.md) and [M4 evidence](AUTHOR_VERIFICATION_M4.json). Real provider execution, model quality, productivity gains and deployment remain unverified. Baseline regression passes must not be reported as model evaluation.

## Offline demo on Mac

From the extracted project folder (Python 3.10+, no packages needed):

```bash
python3 verify.py
python3 ingest.py --bundle fixtures --database output/demo.sqlite
python3 assistant.py --database output/demo.sqlite --order-id O001
python3 assistant.py --database output/demo.sqlite --order-id O001 --task confirmed_root_cause
python3 evaluate_assistant.py
```

The first briefing is `review_draft`, `mode=baseline`, `live_execution=false`; findings quote complete retrieved source items. The root-cause request is `abstained`: the database does not contain a verified-cause field. Baseline is deterministic Python logic, not LLM inference or ML.

Evaluation creates isolated temporary databases. It writes `output/assistant_evaluation_baseline.json`. Eight cases cover exception/dispatch/no-events, absent order, unverified cause, instruction-in-note, mixed event history and withheld overlong notes. Passing these authored cases measures only stated application checks, not independent AI accuracy. The cases were used during development; they are not a held-out test set. Semantic relevance and action suitability require separate human scoring.

## Optional actual GenAI run

Requires an OpenAI API account/key, network access to api.openai.com and a model that supports the documented Responses structured-output format. Set `OPENAI_API_KEY` locally using your normal secure environment configuration; do not paste keys in chat, commit them or place them in command history. No SDK is required. No model is selected implicitly.

After choosing an accessible model, replace `YOUR_ACCESSIBLE_MODEL` below with its actual model ID:

```bash
python3 assistant.py --database output/demo.sqlite --order-id O001 --mode openai --model YOUR_ACCESSIBLE_MODEL --allow-remote
```

This opt-in transmits retrieved order facts, event text and note text to OpenAI and can incur API charges. Use only the supplied synthetic fixtures for the first trial. Do not send internship/customer information. Only one request is attempted; no automatic retries. The API key is read at execution time and never logged. The endpoint is fixed, redirects/proxies are disabled, timeout is 45 seconds and output is bounded. These are transport limits, not a guarantee of data governance or zero provider retention. `store=false` does not establish zero data retention.

For a comparable model regression run:

```bash
python3 evaluate_assistant.py --mode openai --model YOUR_ACCESSIBLE_MODEL --allow-remote
```

At most six cases call the model (unknown order and unverified cause abstain before remote execution). Results include observed latency/token usage on successful calls. Errors do not count as model passes. `assistant_evaluation_openai.json` is not bundled as a fabricated success: it must come from actual execution. An HTTP success or valid JSON alone is insufficient; model output must pass source checks, then human relevance review.

## Prompt and validation design

- Versioned system prompt: `operations-evidence-v1`; prompt hash and explicit model ID appear on a validated live result.
- Incoming records are untrusted data. There are no executable tools, shell commands, email or database-write capabilities.
- The model can select at most six evidence findings and one suggested action from a fixed set. Suggestions are proposals, never executed.
- Every finding must cite an ID from the retrieved order and quote the COMPLETE source item exactly. Unknown/duplicate citations, modified numbers/text, extra output fields and arbitrary actions are rejected.
- Exact text matching verifies provenance, not truth: a source note may be wrong or contain malicious instructions. A copied malicious note is still untrusted text. These tests do not prove model immunity to prompt injection.
- Structured data status is computed outside the model. `delivery_event_recorded` does not mean independently confirmed receipt. Both exception and delivery events produce a mixed-history warning, not an inferred contradiction/root cause.
- Retrieval caps 20 events and 10 notes; notes over 1,500 characters are withheld. Warnings identify limits, and source incompleteness still needs human review.
- This prototype has no user authentication, tenant isolation, PII redaction or enterprise retention policy. Local ownership controls remain necessary. It must not be offered as an organization-wide service in its current form.

## Resume boundary

May describe: implemented a read-only evidence-retrieval baseline, citation/quote validation, abstention logic and an optional GenAI adapter with authored evaluation cases.

Do not describe actual GenAI quality/results, an agent, business savings, production deployment or organizational adoption until separately implemented and evidenced. This milestone's baseline results are not evidence of model performance.

## API reference used

Official OpenAI documentation, checked 20 October 2026:
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses

The adapter uses `text.format` with a strict JSON schema and handles refusal/incomplete responses. Structured output constrains format; it does not establish the correctness of a selected observation.
