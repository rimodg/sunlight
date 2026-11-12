# Public corrections register

## COR-001: stale public reference reports and an unsupported reproducibility claim

- Recorded: November 12, 2026. Related investigation: EVAL-001.
- Affected public artifacts: reports/evaluation_report.json and .md;
  reports/validation_report.json and .md. Both retained February measurements
  after the comparison sampler became deterministic in April.
- Correction: label each artifact stale as of November 12, preserve the original
  values, and place the newly executed reference figures beside them. A fixed
  CLI seed did not make the February SQL random draw reproducible.
- Current measured reference: both protocols TP 9, FN 0, FP 18, TN 182;
  precision 33.33%, recall 100%, F1 50%, specificity 91%; general PR-AUC 0.7456.
  These are constructed-reference results, not independently measured field
  accuracy. Exact inputs, commands and runtime are in the dated run receipts.
- Execution-provenance limit: the general archive exactly replays from its
  stored sample and old code on the verified corpus. The DOJ archive lacks its
  negative draw and original execution receipt. No finding of fabricated or
  never-executed output is made; that historical provenance remains open.
- README correction: 2,090 passed, 10 skipped, 0 failed measured November 12 on
  watch-live-sources. The principle now names nine synthesized positive price
  examples and 200 presumed negatives and disclaims field-accuracy inference.
  The same misleading principle was corrected in docs/ARCHITECTURE.md.
- Detailed evidence: [history audit](EVAL001_HISTORY_2026-11-12.md).
