# Additional local RAG evaluation

Business question: can an operations reviewer obtain the relevant recorded facts,
while distinguishing missing evidence from a confirmed operational outcome?

This is an additional authored synthetic evaluation, not a production benchmark.
Eight questions share four orders; observations are correlated. The earlier three
cases were used during prompt debugging. These new cases have not yet been run
against the local model at publication. No success rate is claimed in advance.

## Protocol

- Keep the v3 system prompt unchanged; the runner rejects a changed prompt hash.
- Build a dedicated temporary synthetic bundle and ingest it using the real loader.
- Use 11 candidate records for C101 with only six retrieval slots (including one
  mandatory order record). This exercises selection under a retrieval budget.
- Test receiving-window evidence, quantity, unconfirmed cause, dispatch without
  acceptance, missing history, a foreign-order question, an instruction in a note,
  and an unknown order. Reference labels are never sent to the model.
- Run each question once. Preserve failures. Do not silently retry or change
  questions/prompt after observing results. Later changes require a new version.
- Record code hashes, fixture fingerprint, environment, model names, retrieval IDs,
  accepted results, and raw generation for this synthetic-only dataset.
- Check that the database bytes remain unchanged. No business actions are executed.

## Run on a machine with the two Ollama models already installed

From `supplements/operations_ingestion`:

```bash
python3 -m unittest discover -s tests -p 'test_rag_challenge.py' -v
python3 evaluate_rag_challenge.py \
  --embedding-model nomic-embed-text:v1.5 \
  --model qwen2.5:3b \
  --allow-local \
  --output output/rag-challenge-mac-01
```

Open `output/rag-challenge-mac-01/report.html` for the review page and retain
`report.json` as evidence. On macOS, use `open output/rag-challenge-mac-01/report.html`.
An exit code of 1 means one or more reference checks failed or the database changed;
inspect the saved report. Existing output directories are never overwritten.
No OpenAI API key or paid API is used. Local Ollama must already be running.

## Read the results correctly

| Measure | Meaning | Limitation |
| --- | --- | --- |
| Status match | Accepted result has the authored expected status | Does not establish relevance |
| Retrieval reference recall | Required evidence IDs present in the retrieved six | Only scored for three answerable questions; includes pinned order facts |
| Required evidence coverage | Required IDs present in accepted findings | Extra IDs remain visible for review; not an overall precision score |
| Reference checks passed | Status matches and required evidence is selected | Not model accuracy or independent human evaluation |
| Generation requests | Calls attempted by the runner | Unknown order is a code gate, not a successful model abstention |

The returned quotes already undergo exact source and retrieved-membership checks.
For each case, a human still needs to review relevance, misleading extra evidence,
appropriateness of abstention, and the suitability of the next action. The report
keeps `human_review: pending`; it does not fabricate reviewer decisions. Raw model
output can be invalid even when the application safely rejects it.

No confidence interval is reported: this small, authored, correlated set does not
support a meaningful population accuracy estimate. Local timing includes model
warm-up effects and is not a performance comparison. Model tags are mutable;
retain `ollama list` output alongside each real run to record the installed IDs.
