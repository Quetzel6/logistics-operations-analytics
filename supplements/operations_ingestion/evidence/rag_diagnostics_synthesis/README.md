# Offline synthesis of uploaded captures

`verified_summary.json` records six user-supplied ZIPs, their SHA-256 values,
per-file hashes, metadata and 15 recorded decision outcomes. It does not combine
these selected/repeated calls into accuracy or replace the historical 13/16.
Raw originals stay in the user's capture directories and original uploads; this
directory contains derived verification, not reconstructed HTTP evidence.

To reproduce, create a local JSON mapping with paths to the original ZIPs:

```json
{
  "schema": "due_date_capture_mac_01_hand0ff.zip",
  "no_format": "due_date_no_format_mac_01_handoff.zip",
  "short_system": "due_date_short_system_mac_01_handoff.zip",
  "negative_controls": "short_system_abstention_mac_01_handoff.zip",
  "full_context": "short_system_false_abstentions_mac_01_handoff.zip",
  "reduced_context": "short_system_reduced_mac_01_handoff.zip"
}
```

From operations_ingestion (paths may be absolute):

```bash
python3 evidence/rag_diagnostics_synthesis/verify_capture_chain.py \
  --captures /path/to/captures.json \
  --historical-report evidence/local_rag_staged_mac/report.json \
  --output /path/to/new-review-directory
```

The verifier does no network/model calls and never extracts untrusted archive
paths to disk. It verifies body hashes, run completion, request/response linkage,
baseline hash chains, runtime metadata equality, intended request differences
and historical full/reference-assisted reduced contexts. Assertions must remain
enabled (do not run Python with `-O`). Metadata consistency is not independent
attestation of the Mac process or all runtime defaults.

Interpretation: [Thai findings](../../RAG_FINDINGS_TH.md).
Proposed next selector: [design](../../RAG_CONTEXT_SELECTION_DESIGN.md).
