# Direct-support prompt experiment

ID-selection v1 improved the first Mac regression run to 7/8 checks but introduced
a regression: it selected unverified-cause and dispatch records instead of
abstaining on a confirmed-cause question. Exact source text does not guarantee
that a source answers the question. The original report is preserved at
[evidence/local_rag_ids_v1_mac/report.json](evidence/local_rag_ids_v1_mac/report.json).
Its SHA-256 is `9311e2c01a4595efd9e869ff96e033bde7d5338df0ecaaaa98fe4b934eed492b`.
All five recorded code hashes match the supplied implementation at commit
`0ff3f6d5a7e731caa78cbb7618b2752d00b9f4e6`. The report is owner-supplied,
not independent attestation; its human-review status is unchanged.

| Observed group | Quote-selection v3 | ID-selection v1 |
| --- | --- | --- |
| Answerable questions | 1/3 | 3/3 |
| Model abstention questions | 4/4 | 3/4 |
| Unknown-order application gate | 1/1 | 1/1 |
| Total reference checks | 6/8 | 7/8 |

These are single authored development runs, not population accuracy estimates.
The v1 raw response did not invent a cause sentence: its failure was accepting
background records as an answer to a confirmed-cause question.

## What changes

`local_rag_ids_v2.py` changes only the system prompt and protocol label relative
to v1. It explicitly distinguishes directly supporting evidence from related
background; uncertainty about one fact does not invalidate other recorded facts.
It allows a recorded confirmed cause to be selected while requiring abstention
when that cause is unverified. An estimate can answer a question about the recorded
estimate, but cannot establish an actual event. These are instructions to the
model, not an independent semantic verifier or a guarantee of correct abstention.

ID validation, exact source rendering, retrieval, model options, and transport
remain unchanged. Earlier code and reports remain intact. There is no keyword
rule that forces answers to the observed failing question and no automatic retry.
Separate experimental modules preserve historical reproduction; consolidating
common code remains a maintenance task after comparison.

## Run once and retain every outcome

From the existing repository root, run `git pull --ff-only`, then enter
`supplements/operations_ingestion`:

```bash
python3 verify.py
python3 evaluate_rag_ids_v2.py \
  --embedding-model nomic-embed-text:v1.5 \
  --model qwen2.5:3b \
  --allow-local \
  --output output/rag-ids-v2-mac-01
open output/rag-ids-v2-mac-01/report.html
```

The runner makes up to 15 generation requests for 16 cases. One unknown order is
rejected before inference. Outputs cannot overwrite an earlier directory. A
nonzero exit can indicate failed reference checks; retain and inspect the report.
No paid API is used. Retain `ollama list` with the run to identify installed models.
At this milestone Linux verification passed 80 software tests with mocks. The
first Mac v2 run subsequently passed 7/8 original and 4/8 newer cases. See the
[two-stage successor and preserved evidence](RAG_STAGED_GUIDE.md) for failures.

## Two separately reported cohorts

- `regression`: the exact earlier eight cases and bundle, including the previously
  successful answerable cases and the confirmed-cause regression. Its abstention
  total includes the unknown-order application gate, not a model success.
- `new_authored`: eight questions on four new synthetic orders. Five are answerable
  and three require abstention. They cover recorded confirmed cause, quantity amid
  cause-related records, a known window with an unknown cause, recorded estimate
  versus signed acceptance, and a due date alongside an instruction in a note.
  One order has 11 candidates competing for six retrieval slots.

The new cases were authored after observing v1, and target those known weaknesses.
They are not an independently sampled or blinded benchmark. No model results for
these cases were observed while writing this prompt. Keep the committed prompt,
fixtures and scoring fixed for the first run; further tuning makes those cases
part of the development set too. Do not combine cohort totals into a general
accuracy claim. Human review must still assess relevance, extra IDs and abstention.

Review the answerable and abstention counts separately. If confirmed-cause
abstention improves but answerable questions deteriorate, that is a tradeoff to
report, not a reason to suppress failed cases. Timing is not a controlled speed
comparison. The evidence supports a portfolio prototype, not production readiness.
