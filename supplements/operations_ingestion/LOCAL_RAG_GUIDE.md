# Local retrieval and evidence selection

Status: v3 owner-run macOS transcript shows all three development cases matching expected status; two invoke local models and one rejects an unknown order before inference. See [LOCAL_RAG_EVIDENCE.md](LOCAL_RAG_EVIDENCE.md) for failures and limits.
This is a small order-scoped retrieval-augmented evidence-selection prototype,
not a production assistant, autonomous agent or persistent vector database.

The read-only SQLite context loader first filters by exact order ID and retains
its existing 20-event / 10-note bounds. Embeddings rank that bounded context in
memory using cosine similarity. Up to six sources (including the order record)
are passed to a local generator. The output is an evidence-selection JSON object,
not free-form advice. The existing validator rejects altered quotes, unknown or
unretrieved citations, duplicate citations, extra fields and unsupported actions.
All accepted outputs still require human review. Source matching does not prove
relevance, factual truth, prompt-injection resistance or business usefulness.
The model can return an empty abstention. There is no calibrated relevance cutoff or independent semantic verifier: unrelated questions can still produce irrelevant citations. Abstention is model-decided, not guaranteed.
Do not use this prototype to establish root cause or delivery acceptance.

## Run on macOS

Install and open Ollama from https://ollama.com/download first. Model downloads
require internet, storage and the publisher's license terms. Inference requests
from this code use only 127.0.0.1:11434; redirects and HTTP proxies are disabled.
Use the bundled synthetic fixture for this trial. From a fresh clone, run
`cd supplements/operations_ingestion` before the commands below.

In this directory:

```bash
ollama pull nomic-embed-text:v1.5
ollama pull qwen2.5:3b
ollama --version
ollama list
python3 -m unittest discover -s tests -v
python3 ingest.py --bundle fixtures --database output/local-rag-demo.sqlite
python3 local_rag.py --database output/local-rag-demo.sqlite --order-id O001 --question "Which exception was recorded for this order?" --embedding-model nomic-embed-text:v1.5 --model qwen2.5:3b --allow-local
```

Expected successful status is `review_draft`, with exact evidence quotes and
`live_execution: true`. Errors are retained as failures, not converted into a
baseline success. A failed run can have already performed some model calls;
`live_execution: false` in CLI failures means no completed accepted result.
Models may fail to copy source text exactly; that is an evaluation outcome.

Record `ollama --version`, `ollama list`, command output and hardware details.
Human review must check whether findings actually answer the question. Also try
O003 (sparse records), UNKNOWN (must abstain without inference), an unrelated
question and an instruction-like note in a disposable test database. Retain
failures alongside successes. These are authored smoke cases, not a held-out
quality benchmark. V3 development outcomes are recorded; they do not establish general retrieval or answer quality. Human assessment of each new output is still required. No production, model-training, vector-database
or agent implementation claim is supported by this extension.

References:
- https://docs.ollama.com/api/embed
- https://docs.ollama.com/api/generate
- https://ollama.com/library/nomic-embed-text
- https://ollama.com/library/qwen2.5:3b

## Retain diagnostic evaluation

```bash
python3 evaluate_local_rag.py --database output/local-rag-demo.sqlite --embedding-model nomic-embed-text:v1.5 --model qwen2.5:3b --allow-local --diagnostics-synthetic > output/local_rag_evaluation.json
```

The explicit diagnostics flag includes raw generation text for synthetic inputs.
Without it the report omits raw responses. CI runs mocks and existing pipeline
checks; CI does not download or run these models. A status match is not an
automatic relevance judgment. Record model IDs with `ollama list`; tags can move.
