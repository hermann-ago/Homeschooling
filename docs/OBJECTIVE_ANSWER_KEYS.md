# Source-bound objective assessment

True/false statements and printed event-ordering exercises can be checked without
an AI assessment call. `source_key.resolve` reads the running session's pinned
source map. `sequence_key` matches the full printed list, its order, the assigned
source task and edition, and independently checked answer-key annotations.
Whitespace/punctuation differences from OCR are allowed; words and qualifiers
cannot be dropped. Ambiguous, disputed, unchecked or mismatched keys do not qualify.

Ordering responses are ranks in **printed statement order**, rather than an
inverted list of statement IDs. Only unambiguous complete number lists use the
direct comparison. The private key is frozen with assessment inputs and never
added to child activity content. Grouped and individual answer submission use
the same checker.

Confirmed answer-content captures supersede uncertain photo OCR. Keep the
original OCR and confirmed interpretation separately. Photos remain necessary
when the actual target is handwriting, a diagram or a written method.

The existing `recheck_key` event also repairs ordering misgrades, including a
saved revision. Attempts remain immutable; corrections append linked amendments.
If the first confirmed complete sequence was already correct, no subsequent full
sequence was wrong, and unnecessary teacher clarification created a knowledge
review, restore that first evidence and withdraw the spurious review. Follow-up
clarifications remain saved and unassessed rather than becoming learner errors.
Do not regenerate scripts or narration for an assessment correction.
