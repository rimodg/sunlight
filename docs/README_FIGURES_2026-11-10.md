# README figure audit, November 10, 2026

Read the README on main and the rebuild, both observed pytest logs, the stored
evaluation report, rule registries, evidence schema, research corpus and API
batch checks. Separate a witnessed run from an inspected historical report and
from a count of implemented objects; none establishes the others.

The 1,889-test statement is on main. The rebuild README had already removed it,
but still claimed that local full-suite verification and locked installation
were unavailable. This branch now supplies both dated measurements below. Main
has not been edited or pushed; it receives the correction only after review and
merge of this branch.

| Figure | Evidence and disposition |
| --- | --- |
| 1,989 tests passed on main | Observed 2026-11-10 on bd9ebef: 1989 passed, 12 skipped, 0 failed. Published with date and exclusions. |
| 2,056 tests passed on rebuild | Observed 2026-11-10 after resolving RUNTIME-002 paths: 2056 passed, 13 skipped, 0 failed; 17 subtests separate. |
| 35 locked packages | Installed with no dependency resolution and binary wheels only; actual service runtime verifier accepted the exact package map. |
| Earlier 50/8/6/4 subset counts | Historical November 9 report, not rerun separately in this audit. Removed from the current measurement table; historical report retained. |
| 33.3% precision, 100% recall, 9.0% FPR | Match docs/evaluation_report.json dated 2026-06-11T22:02:15.661362+00:00. Arithmetic agrees with stored TP=9, FN=0, FP=18, TN=182. Not a newly witnessed evaluation. |
| PR-AUC 0.746 | Rounded from stored pr_curve.pr_auc=0.7456. No new ranked-prediction evaluation performed. |
| 129.2 flags per 1,000 | Stored value and 27/209*1000 rounded to one decimal agree. No new evaluation performed. |
| 9 synthesized positives, 200 presumed negatives, 1 excluded | Match stored dataset_composition. Labels do not establish field truth. |
| 42,835 source contracts | Historical corpus claim, not independently recounted: exact database unavailable. Explicitly qualified. |
| 32 research case records, four included jurisdictions | Counted cases and jurisdictions_included arrays in research/corpus/prosecuted_cases_global_v0.1.json. File inventory, not 32 verified outcomes or independent calibrations. |
| 16 TCA rules | Loaded tca_rules.RULES: PROC=5, ENT=3, FIN=3, TIME=3, GEO=2. Implementation inventory, not observed detection performance. |
| 12 delivery rules | Loaded build_delivery_rules(US_FEDERAL): 12. Implementation inventory. |
| Six evidence classes | Loaded EvidenceClass enum: six entries. Does not demonstrate six independently obtained sources for any real finding. |
| 1,000-item batch limits | Explicit checks in API handlers for procurement, delivery and corroboration. Configuration limits, not a throughput benchmark. |
| 16-stage pipeline, seven engines on each dossier | Removed: the actual API workflows are distinct; a complete combined execution was not demonstrated. |
| Dates in examples, legislation titles and the academic citation | Descriptive source references, not measured counts or validation results. No new legal-applicability review claimed. |

Historical evaluation figures remain labeled as constructed regression outputs.
The missing database blocks reproducing them; a unit-suite pass is not a
substitute. No claim of universal recall, measured savings or recovered money
is introduced by this audit.
