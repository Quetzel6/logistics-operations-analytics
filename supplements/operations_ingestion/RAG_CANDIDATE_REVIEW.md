# Candidate v1: measured result, freeze and review

## Verified development result

The supplied `context_selector_pair_mac_01_handoff.zip` has SHA-256
`96a94272bb59979d4045093483aea50a24d3d0883ad161b941de0c5559a5e743`.
It completed 32 arm observations over the same 16 development cases. Both models'
full digests, source hashes, fixture fingerprints, shared rankings, wire inputs,
response parsing, ID selection/materialization and reference summaries were checked.

| Measure | B: original context | C: field-aware-context-v1 |
|---|---:|---:|
| Reference checks | 11/16 | 14/16 |
| Answerable reference checks | 3/8 | 6/8 |
| Model abstention checks | 7/7 | 7/7 |
| Unknown-order gate | 1/1 | 1/1 |
| False support / failed outputs / extra selected IDs | 0 / 0 / 0 | 0 / 0 / 0 |

C improved instruction_note, quantity_with_cause_context and
due_date_with_instruction. No B-pass/C-fail regression occurred in this run.
Both arms still falsely abstained on receiving_window and recorded_confirmed_cause,
which used fallback contexts. There were 15 shared embeddings, 30 decisions and
9 selections: 39 generation calls. The captured database-unchanged checks passed.

An offline replay reproduced all **54 inference requests** (15 embeddings plus
39 generations) from stored responses without contacting Ollama. All request
payloads matched exactly, and rescoring reproduced B=11/C=14. Latency and the
expected live-vs-replay provenance flag are excluded; cosine scores are compared
at 12 decimal places. See [verification](evidence/context_selector_pair_mac_01/verification.json)
and the unmodified [raw report](evidence/context_selector_pair_mac_01/report.json).

```bash
python3 replay_context_selector.py \
  --capture-zip /path/to/context_selector_pair_mac_01_handoff.zip \
  --output /path/to/new-offline-replay-directory
```

The ZIP's raw events/metadata remain in the original upload and the owner's
directory. Only its synthetic report and derived verification are published here;
no raw file has been rewritten or replaced by replay output. Replay is not a new
independent model evaluation. Historical long-system/schema 13/16 is unchanged and
is not a controlled comparator for C. Scores remain reference checks, not semantic
accuracy; all 16 development cases were already seen.

## Freeze

Candidate runtime is frozen at commit
`b9714367510bdd5f3175b2f3c2642d87364e6a3d`. The
[prospective manifest](prospective_evaluation_v1/manifest.json) records hashes for
the selector, short contract, runtime and source-validation dependencies. No
grammar, decision/selection prompt, model or retrieval changes are made in this
review milestone. The new data validator refuses drift in these frozen files.
This is an opt-in experimental candidate; no automatic adoption or merge occurs.

## Actual-output review packet

The [review packet](evidence/context_selector_review_packet_v1/packet.json) contains
the 32 actual outputs, their questions, available sources and supplied contexts.
Expected labels, reference scores and arm names are omitted from its review units;
the separate mapping is hash-bound for later audit. This is presentation masking,
not a claim of blinded or independent review. The
[HTML](evidence/context_selector_review_packet_v1/review.html) can be opened locally.

All ratings in [decisions.json](evidence/context_selector_review_packet_v1/decisions.json)
are **pending**. The assistant has not filled human ratings. The rubric covers
answerability, relevance/qualifiers, source strength and the human-action boundary.
Every completed judgment needs a rationale and reviewer identity. not_applicable
is allowed only for evidence relevance when there are no findings.

For a working copy, keep the committed pending packet intact:

```bash
python3 review_context_selector.py generate \
  --capture-zip /path/to/context_selector_pair_mac_01_handoff.zip \
  --directory /path/to/new-review-copy
# Review review.html and fill decisions.json in that new copy.
python3 review_context_selector.py score --directory /path/to/new-review-copy
```

Set reviewer_kind accurately to human or ai. A Cowork/AI review is permitted as
an AI assessment and **does not complete human review**. Human completion is
self-reported, not independently authenticated by this offline tool. Packet,
mapping and unit-order changes are rejected; existing directories are never
overwritten. No model calls or business actions occur in generate/score.

## Next evaluation data

A [prospective 16-case set](prospective_evaluation_v1/README.md) is prepared after
the runtime freeze. It uses new IDs/values and nonidentical questions: 8 answerable,
7 known-order abstention cases and 1 unknown-order gate, including new paraphrases,
compound requests, qualified quantities and competing unconfirmed notes.

It is developer-authored by the same assistant after observing development
results, not an independently authored or secret held-out benchmark. It has not
been run against a model. Human reference review is pending. The data hashes and
runtime freeze are registered before the first model run; do not adjust v1 or
labels after seeing those outcomes. Reference corrections require a new explicit
data version and preservation of the prior manifest.

This milestone prepares/validates data and review tools only. The existing paired
runner still runs the old development set; it does not automatically load this
new data. A separately versioned prospective runner is the next step, after
reference review, without changing the frozen runtime. No new live run is needed
to inspect the current evidence or review packet.
