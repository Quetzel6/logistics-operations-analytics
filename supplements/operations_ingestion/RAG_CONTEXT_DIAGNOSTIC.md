# Fixed-prompt context diagnostic

The two-stage Mac run passed 13/16 development reference checks, with zero invalid
outputs. It still falsely abstained on three answerable questions. This experiment
investigates context sensitivity before changing the prompt or model again.

## Frozen baseline and intervention

The [original report](evidence/local_rag_staged_mac/report.json) is retained byte for
byte. Its SHA-256 is `74ea129d8f2f5abc459f906e4662fcaabdeaa1dbaecac05b045bc2095a7598a8`.
The diagnostic verifies its hash, all nine recorded implementation hashes and the
joint prompt hash before inference. It reuses the original decision prompt,
question, JSON schema, temperature 0, token limit and generation transport.

| Selected failure | Full records | Reduced records |
| --- | ---: | ---: |
| receiving_window | 6 | 2 |
| quantity_with_cause_context | 6 | 1 |
| due_date_with_instruction | 2 | 1 |

Full records are reconstructed in the exact retrieved order from the report.
Reduced records retain the reference-required IDs and order record, preserving
text and relative order. **This uses reference labels (oracle assistance).** It is
not a deployable retrieval strategy or evidence of improved end-to-end accuracy.
No source sentence is rewritten; multiple distractors may be removed together.

Four paired repetitions per case alternate full-first and reduced-first order:
**24 decision calls**, zero embedding calls and zero selection calls. Failed calls
are retained, with no automatic retries. Repetitions are planned observations,
not independent samples; do not calculate a significance claim from these counts.
All inputs and raw synthetic outputs are saved. Existing output folders are rejected.
No database is loaded or modified by this diagnostic.

## Run on the same Mac

From the repository root, update the existing branch with `git pull --ff-only`,
then enter `supplements/operations_ingestion`:

```bash
python3 verify.py
ollama list
python3 diagnose_rag_context.py \
  --model qwen2.5:3b \
  --allow-local \
  --output output/rag-context-mac-01
open output/rag-context-mac-01/report.html
```

Use the same installed model as the baseline. The previously supplied model ID
was `357c53fb659c`; it was not automatically captured or independently verified.
The script enforces the model name, not the model-weight digest. Record any model
or runtime change before comparing results. No new model download or paid API is
needed. Exit 1 means a trial failed; either valid decision is an observation, not
an accuracy pass/fail. Preserve `report.json` and the model inventory.

## Interpretation and limits

- Full context repeatedly insufficient but reduced context supported suggests
  sensitivity to the removed context under this protocol. It does not establish
  which record or phrase caused the difference.
- Both contexts insufficient means reduction alone did not resolve the failure.
  It does not prove that model size is the sole cause.
- Variation across repeated identical inputs or against the original run must be
  reported, rather than selecting a favorable result.

These are three deliberately selected failures from an already observed dataset.
The diagnostic does not rerun retrieval, ID selection or answer rendering, and
cannot replace the 13/16 baseline. Human relevance review and an independent
future evaluation remain necessary for broader claims.

## Software verification

99 software tests and SQLite acceptance passed in the Linux development
environment (Python 3.12.14). Seven new mock-based tests cover exact record subsets,
balanced scheduling, unchanged request settings, no extra retry, invalid decisions,
opt-in/model/source checks and HTML escaping. These do not verify live model quality.
Live Mac diagnostic execution is pending.
