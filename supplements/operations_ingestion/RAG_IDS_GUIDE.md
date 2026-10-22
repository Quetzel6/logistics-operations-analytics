# ID selection and exact source rendering

The first eight-case Mac run exposed two generation failures: a correct note ID
with changed quote text and duplicate citation, and abstention despite an available
quantity record. The former was rejected; the latter was validly formatted but
unhelpful.

`local_rag_ids.py` asks for only `status` and `evidence_ids`. The application checks
unique IDs against retrieved records and copies complete source text into findings.
Invalid responses are rejected, not repaired or silently deduplicated. The application
assigns `review_records`; no actions are executed. Empty selection is valid only
for abstention. An irrelevant but valid ID still needs human review.

This removes model quote-copying from the output path. It does not prove better
semantic selection or fix false abstention. Both the output contract and its prompt
instructions change; a score difference cannot be attributed to schema alone.
Retrieval budget, ranking, inputs, temperature and scoring remain the same. There
is no quantity-specific answer rule or automatic retry.

The original `local_rag.py` and `evaluate_rag_challenge.py` remain byte-for-byte
unchanged. The new selector retains their retrieval/transport implementation in a
separate module to isolate the experiment. Consolidation is a later maintenance
step after comparison.

## Run on the existing Mac checkout

Update from the repository root with `git pull --ff-only`, then enter
`supplements/operations_ingestion`:

```bash
python3 verify.py
python3 evaluate_rag_ids.py \
  --embedding-model nomic-embed-text:v1.5 \
  --model qwen2.5:3b \
  --allow-local \
  --output output/rag-ids-mac-01
open output/rag-ids-mac-01/report.html
```

Retain `report.json`, including failures, and `ollama list` output. The output
directory must be new. A nonzero exit can mean reference-check failures; inspect
the saved report before rerunning. No paid API is used. Live model results for this
version are pending. Linux verification passes 76 software tests with mock inference.

These eight cases are now a development regression set: their failures informed
this change. They are not held-out quality evidence. Further evaluation needs new
questions/records, irrelevant valid-ID selections, and multi-source questions.
Human semantic review remains pending.

## Preserved first-run evidence

[Original Mac report](evidence/local_rag_v3_mac_challenge/report.json), received
from the owner on 2026-10-22, is preserved without modification.
SHA-256: `393669b03251ef0225020bcebf3abc8cdab4c43b9db067ea7e89af9d087df5c0`.
All four source-file hashes match commit `244bb8c92dcc7b08714af1bb01448a84fcb342c4`.
This is a supplied artifact, not independent machine attestation. Its pending
human-review status remains unchanged. Model IDs were separately supplied by the
owner from `ollama list`: qwen2.5:3b `357c53fb659c`; nomic-embed-text:v1.5 `0a109f422b47`.

| Group | First-run reference checks | Interpretation |
| --- | --- | --- |
| Answerable questions | 1/3 | Note quotes rejected; quantity falsely abstained |
| Model abstention questions | 4/4 | Expected abstention on this authored set |
| Unknown order | 1/1 | Rejected before inference |
| Total | 6/8 | Seven generation requests; not population accuracy |

Required sources were retrieved for all three answerable questions, but two use
the mandatory order record. This does not establish general retrieval quality.
The receiving-window response repeats `note:TARGET` and modifies both quotes.
The first error is `quote_mismatch`; duplication is another observed violation.
The quantity case retrieves `quantity=137` but returns empty findings. The report
does not establish the model's internal cause. Database bytes were unchanged.
