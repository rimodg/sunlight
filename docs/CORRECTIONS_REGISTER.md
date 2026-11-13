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

## COR-002: the 96-record invariant cohort is not 96 distinct awards

- Recorded November 13, 2026. Affected artifact: the initial invariant-core
  report and its description of 96 awards in the captured population.
- Correction: 96 `(ocid, release_id)` pairs contain 96 award appearances,
  **94 distinct award IDs across 93 procurement OCIDs**. Two award IDs occur
  in two release versions. Three procurement OCIDs have two release versions;
  one of those contains different award IDs.
- The original 96-record denominator is retained for the authorized regime
  and matching measurement, with the distinct counts beside it. No records
  were silently dropped or replaced with later captures.
- The initial report is clarified in place. See the
  [per-record measurement](NOTICE_REGIME_MEASUREMENT_2026-11-13.md).
