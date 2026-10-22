# Prompt-conflict correction

The v2 prompt inherited an instruction that the application computes abstention,
then appended an instruction requiring the model to decide abstention. Owner-run
diagnostics showed status=abstained with nonempty findings on both known-order
cases. These were correctly rejected, not accepted as successful abstentions.

This revision replaces the contradictory prompt with one explicit decision
contract, puts status first in the schema and restricts suggested_action to
review_records. Validators remain unchanged. No automatic status repair, quote
trimming or hidden retry is performed. The author-run v3 transcript subsequently showed both known-order cases
completing with expected outcomes; see LOCAL_RAG_EVIDENCE.md. These three cases are development regressions, not held-out evidence.

The cause-case raw quotation also omitted a trailing newline. If reproduced as
a review draft, exact-quote validation must reject it. Do not remove that check.

Diagnostics are optional via --diagnostics-synthetic, only for synthetic input.
Preserve historical failures; never replace them with the revised run.
