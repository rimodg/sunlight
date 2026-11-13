# Learnings

## EVAL-001: recorded settings do not establish reproducibility; only a re-run does

**Recorded:** November 12, 2026.

Both archived reports recorded seed 42, 1,000 bootstrap iterations and 200
comparison contracts. Their old sampler nevertheless used SQLite
`ORDER BY RANDOM()`, which the recorded CLI seed did not control. Equal settings
therefore did not establish equal evaluated populations or reproducible results.

The old general evaluator was re-run against the verified corpus with the
archived sample IDs. It reproduced every stored case result, metric, confidence
interval, PR curve and threshold sweep exactly. The DOJ report did not retain
its negative draw, so its full historical result remains unverifiable even
though its positive case details re-run exactly.

**Rule going forward:** recorded settings do not establish reproducibility;
only a re-run with verified inputs and compared outputs demonstrates it. Retain
input hashes and durable locations, the source revision, runtime/dependency
identity, command, every sampling seed and the selected record IDs or immutable
sampling basis, then preserve the execution receipt and output digests. Check
all random-number generators and ordering dependencies, not just the CLI seed.

Report which fields matched and what could not be reproduced. A matching re-run
shows that a result can be reproduced under the recorded conditions; it does
not authenticate an unrecorded historical execution or establish field accuracy.
Never infer fabrication solely from missing provenance. Preserve stale artifacts
with dated notices and current measured results beside them.

Evidence: [EVAL-001 history and executed controls](EVAL001_HISTORY_2026-11-12.md),
[correction COR-001](CORRECTIONS_REGISTER.md), and the
[committed audit receipt](../reports/reference-history-2026-11-12/summary.json).

## November 13, 2026: publication-order evidence needs the right event pair

A dated award or a portal label does not establish the procurement's regime.
A cited parent framework can establish saved-regime context without supplying
the corresponding call-off award notice. Keep those joins separate and report
UNDETERMINED where the legal-basis chain is missing. A complete traversal of
one update window is not an all-time notice search. Preserve release-version
denominators and do not backfill an unavailable historical version with a
fresh document. A running scheduler and a completed examination also do not
prove fresh source contact: report backoff and source silence separately.

## November 13, 2026: a populated date field is not automatically the legal event

The FTS sample supplies both signature and publication dates for all 150
contract-details rows. It supplies no admitted equivalence between signature
and the contract-entry event used by section 53. Field coverage is therefore
100% for that pair while legal assessability is zero under the owner's
conservative scope. Keep those denominators separate. A name resemblance,
common practice, or a fact-specific guidance example cannot establish a
universal date mapping or ordering. Report plain measured gaps separately,
keep undefined statutory margins null, and retain the legal-review question.
