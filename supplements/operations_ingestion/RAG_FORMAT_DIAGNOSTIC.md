# One-call format diagnostic

`diagnose_rag_format.py` compares against the preserved one-record due-date HTTP
capture. It generates exactly once, removing only `format` from the baseline
request. System prompt, question, record, model tag, stream and options remain
equal. It does not send format=null, alter a prompt, add a retry, or select IDs.

The uploaded Mac capture reproduced insufficient with HTTP 200, done=true and
done_reason=stop. It recorded Ollama 0.40.7, qwen2.5:3b Q4_K_M full digest
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`,
265 prompt tokens and a loaded context of 4096. These observations do not establish
why the answer was insufficient or independently attest the rendered model input.
The current capture is user-supplied evidence; its raw files remain on the user's
Mac and in the original upload, not substituted by reconstructed requests.

## Run once on the original Mac

From `supplements/operations_ingestion`, on branch
`fix/rag-durable-evidence-20261022`, with Ollama running:

```bash
git pull --ff-only
python3 verify.py
python3 diagnose_rag_format.py \
  --baseline-capture evidence/due_date_capture_mac_01 \
  --allow-local \
  --output evidence/due_date_no_format_mac_01
python3 inspect_rag_run.py --directory evidence/due_date_no_format_mac_01
```

The baseline must be a complete live durable-due-date-v1 capture. Before creating
output or contacting Ollama, the script validates sequence numbers, stored HTTP
body hashes, the single generation response, and the exact baseline request against
the frozen synthetic due-date case. It records baseline file hashes. Current
Ollama version, full model digest, template, system, parameters and model details
must match the baseline before generation is allowed. Existing output is rejected.
The same durable capture transport records metadata and HTTP bodies; no models
are downloaded. Postflight captures loaded context and inventory, flagging digest
drift. Source hashes are recorded with the experiment configuration in the journal.

Keep both directories. To share this new run:

```bash
zip -r evidence/due_date_no_format_mac_01_handoff.zip \
  evidence/due_date_no_format_mac_01
```

## Interpret carefully

The original strict JSON parser is retained. Without constrained output, Ollama
may return prose or Markdown. Such output remains in full HTTP capture and
diagnostics; a parse failure is not automatically a semantically wrong answer.
Exit 1 on parse/decision validation failure is expected to require inspection.
Do not trim, repair or silently retry. A runtime mismatch stops before generation;
retain the failed run and inspect its metadata instead of upgrading models.

Supported here versus insufficient in the baseline is evidence of a difference
between these observations, consistent with a format interaction. It is not proof
that schema alone caused it: the calls occurred on different occasions and not
all effective runtime defaults are observable. Insufficient again does not rule
out every schema interaction. Neither result changes the historical 13/16 reference
checks or establishes that a larger model is necessary.

Software tests use simulated HTTP and cover exact request differences, a single
generation, baseline preservation, parse-failure evidence, interruptions, corrupt
baselines and runtime mismatches before dispatch. No new live generation has been
performed by the cloud assistant.
