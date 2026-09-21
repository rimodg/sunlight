# CLAIMS.md — ledger of every number in README.md

Dated 2026-09-21. Machine-checked by `tests/test_claims_ledger.py`: every numeric
token in README.md must have a row here, every row's Number must still be in the
README, and every test, artifact or code symbol a row cites must exist. The suite
fails otherwise.

**UNBACKED rows:** 1, 2, 3, 4, 5, 6, 7, 8, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36

## How to read a row

- **Number**: the token exactly as it appears in README.md (`33.3%`, `42,835`, `16`).
- **Claim**: what the README says the number means. One number can carry more
  than one claim; each gets its own row.
- **Backing**: what makes the claim checkable.
  `tests/<file>.py::<Class>::<test>` is a test in this suite that asserts it.
  `artifact:<path>` is a checked-in file that records it.
  `code:<path>::<symbol>` is where a value is defined (implemented, not tested).
  `none` is nothing.
- **Status**: `BACKED` (a test or artifact cites it), `UNBACKED` (nothing does,
  or the measured value disagrees), `NOT-A-CLAIM` (a year, statute, port or
  section label; not a measurement).
- **Note**: the measured value when it differs, and where it was measured.

Measurement references in Note use the same `tests/...::...` form and are
resolved by the gate too.

## The ledger

| # | Number | Claim | Backing | Status | Note |
|---|---|---|---|---|---|
| 1 | 42,835 | "Validated on 42,835 real US federal procurement contracts" | none | UNBACKED | The contracts database is not in the repo. `docs/evaluation_report.json` records 200 clean + 9 positive + 1 excluded = 210 rows scored; the 42,835 figure appears only in prose (`SUNLIGHT_READINESS_ASSESSMENT.md`) and a code comment. Not reproducible from this checkout. |
| 2 | 32 | "100% recall on 32 prosecuted reference cases spanning four legal systems" | none | UNBACKED | The corpus has 32 cases in 4 jurisdictions (tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_corpus_has_32_cases_in_4_jurisdictions), but the evaluation artifact scored 9 US positives (tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_scored_nine_positives_not_thirty_two). No evaluation of the 32 exists. README moved from 9 to 32 in commit 90526c7 (2026-06-12) without a gate change. |
| 3 | 100% | "100% recall means every prosecuted case in the corpus is detected ... encoded in the test suite and gated by CI, every commit" | none | UNBACKED | As a claim about CI: SUNLIGHT CI failed on all 118 recorded runs (2026-02-19 to 2026-09-02, `gh run list`) and had never passed. As a claim about the suite: the engine gate measures 8/9 with repo-realistic comparables (tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_recall_on_price_fraud_cases_is_recorded); the 75% floor case is flagged only when comparables' coefficient of variation is about 0.05 or below (tests/test_doj_blind_e2e.py::TestFloorCaseDependsOnDispersion::test_floor_case_not_flagged_with_repo_realistic_cohort). See row 9 for the recorded value. |
| 4 | 100% | Design principle: "100% DOJ recall is the institutional credibility floor, zero tolerance, CI-gated" | none | UNBACKED | Same evidence as row 3. |
| 5 | 1,889 | "1,889 tests across five build phases plus two cross-cutting suites" | none | UNBACKED | Measured 2026-09-21: 1,981 collected excluding `tests/test_docker_live.py`, 1,988 including it (`pytest --collect-only -q`). Before this branch the count was 1,972 passed + 5 errors + 3 skipped + 1 xfailed. |
| 6 | 734 | Test table: Side 1 procurement verification, 734 tests | none | UNBACKED | No test, artifact or file-to-phase mapping exists for the per-phase counts. |
| 7 | 242 | Test table: Side 2 delivery verification, 242 tests | none | UNBACKED | As row 6. |
| 8 | 129 | Test table: Side 3 intelligence alerts, 129 tests | none | UNBACKED | As row 6. |
| 9 | 100% | Evaluation table: Recall 100% | artifact:docs/evaluation_report.json; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_metrics_match_readme | BACKED | Recorded 2026-06-11 over 9 US DOJ price-fraud cases with real USAspending comparables that the artifact does not store. Not reproducible in-repo; the in-repo engine gate gives 8/9 (row 3). |
| 10 | 33.3% | Evaluation table: Precision 33.3%; "DOJ regression baseline preserved across every commit: 33.3% / 100% / 9.0% / 0.746 / 129.2" | artifact:docs/evaluation_report.json; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_metrics_match_readme | BACKED | "Preserved across every commit" is row 3's CI claim and is UNBACKED; the value itself is recorded in the artifact. |
| 11 | 9.0% | Evaluation table: False Positive Rate 9.0% | artifact:docs/evaluation_report.json; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_metrics_match_readme | BACKED | Artifact records 0.09: 18 false positives over 200 clean contracts sampled from a database not in the repo. Backed as a recorded value; not re-measurable here. |
| 12 | 0.746 | Evaluation table: PR-AUC 0.746 | artifact:docs/evaluation_report.json; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_metrics_match_readme | BACKED | Artifact value 0.7456. |
| 13 | 129.2 | Evaluation table: Flag Rate 129.2 per 1,000 contracts | artifact:docs/evaluation_report.json; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_metrics_match_readme | BACKED | Recorded as 27 flags over 209 scored rows in the artifact. That is a flag rate of the 209-row evaluation set, not of the 42,835-contract corpus the README pairs it with; the corpus rate was never recorded. |
| 14 | 1,000 | "Flag Rate: 129.2 per 1,000 contracts" | artifact:docs/evaluation_report.json | BACKED | Denominator of row 13. |
| 15 | 1,000 | "POST /batch: up to 1,000 contracts per request"; "POST /evidence/batch: up to 1,000 claims" | tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_batch_endpoint_rejects_1001_contracts; tests/test_evidence_api.py::TestBatchEndpoint::test_batch_limit_enforced | BACKED | 1,001 contracts to /batch returns 413; 1,001 claims to /evidence/batch returns 413. /delivery/batch has no test. |
| 16 | 42 | "Evaluation is deterministic and reproducible: --seed 42 --clean 200 --profile doj_federal" | artifact:docs/evaluation_report.json; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_records_seed_and_clean_count | BACKED | run_seed 42 recorded. |
| 17 | 200 | "--clean 200" | artifact:docs/evaluation_report.json; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_evaluation_artifact_records_seed_and_clean_count | BACKED | n_clean_contracts 200 recorded. |
| 18 | 12 | "Delivery Verification: 12 rules across 4 layers" | tests/test_delivery_rules.py::TestBuildDeliveryRules::test_returns_12_rules; tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_delivery_rule_ids_are_12_across_4_layers | BACKED | 12 DEL-* rule ids in `code/delivery_rules.py`. |
| 19 | 12 | "stages 9-12 delivery" (16-stage numbering) | none | UNBACKED | The pipeline enum has 12 members with no side numbering (row 20). The 1-8 / 9-12 / 13-16 scheme exists only in prose. |
| 20 | 16 | "A 16-stage pipeline runs across five sides" | none | UNBACKED | Measured: `PipelineStage` has 12 members (tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_pipeline_stage_count_is_measured). |
| 21 | 16 | "TCA: 16 rules across 5 layers (procurement 5, entity 3, financial 3, temporal 3, network 2)" | none | UNBACKED | Measured: 14 rule ids in `code/tca_rules.py`, prefixes PROC 5, ENT 3, FIN 3, TIME 3, NET 0 (tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_tca_rule_id_count_is_measured). |
| 22 | 5 | "16 rules across 5 layers" | none | UNBACKED | Four rule-id prefixes exist; there is no network layer in code (row 21). |
| 23 | 2 | "network 2" (TCA network-layer rules) | none | UNBACKED | Zero NET-* rule ids in code (row 21). |
| 24 | 1 | "stages 1-8 procurement" | none | UNBACKED | As row 19. Also the section label "Side 1", which is not a claim. |
| 25 | 8 | "stages 1-8 procurement" | none | UNBACKED | As row 19. |
| 26 | 9 | "stages 9-12 delivery" | none | UNBACKED | As row 19. |
| 27 | 13 | "stages 13-16 evidence corroboration" | none | UNBACKED | As row 19. |
| 28 | 150 | "approximately 150 countries without mature local prosecution data" | none | UNBACKED | No source cited in the README or repo. |
| 29 | 6 | "TIME-001 fires on March 25 under the UK profile (6 days before UK fiscal year-end) and does not fire under US federal" | none | UNBACKED | No test asserts the March-25 behaviour under either profile; `tests/` was searched for "March 25", "03-25" and the TIME-001 references (`tests/test_evg_gate.py`, `tests/test_structural_scoring.py`, `tests/test_alerts.py`) do not exercise the fiscal calendar. |
| 30 | 25 | "March 25" (same claim as row 29) | none | UNBACKED | As row 29. |
| 31 | 1,182 | "The pre-Side-5 baseline was 1,182" (test count history) | none | UNBACKED | Historical count; no artifact. |
| 32 | 1,133 | "the original 1,133 after an institution-readiness pass" | none | UNBACKED | Historical count; no artifact. |
| 33 | 39 | Test table: Hardening, 39 tests | none | UNBACKED | Measured 2026-09-21: `tests/test_hardening.py` collects 39 (23 functions, parametrised). No test asserts it; listed UNBACKED with rows 6-8 because the per-phase table has no mapping a gate could check. |
| 34 | 79 | Test table: Side 4 recovery intelligence, 79 tests | none | UNBACKED | As row 6. |
| 35 | 570 | Test table: Side 5 evidence corroboration, 570 tests | none | UNBACKED | As row 6. |
| 36 | 96 | Test table: Output layer, 96 tests | none | UNBACKED | As row 6. Measured 2026-09-21: `tests/test_structural_scoring.py` collects 105. |
| 37 | 5 | "procurement 5" (PROC-* rule count) | tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_tca_rule_id_count_is_measured | BACKED | Five PROC-* ids measured. |
| 38 | 3 | "entity 3, financial 3, temporal 3" (ENT-*, FIN-*, TIME-* rule counts) | tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_tca_rule_id_count_is_measured | BACKED | Three of each measured. |
| 39 | 4 | "12 rules across 4 layers"; "4 EVG dimensions" (delivery) | tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_delivery_rule_ids_are_12_across_4_layers; tests/test_delivery_evg.py::TestDimensionTraceability::test_all_four_dimensions_always_present | BACKED | Four DEL-* layer prefixes; DeliveryDimension has four members. Also the section label "Side 4". |
| 40 | 41 | "41 USC" (US federal profile framework) | none | NOT-A-CLAIM | Statute citation. |
| 41 | 2010 | "UK Bribery Act 2010" | none | NOT-A-CLAIM | Statute year. |
| 42 | 2015 | "Public Contracts Regs 2015" | none | NOT-A-CLAIM | Statute year. |
| 43 | 2022 | "Heng, Tsilionis, Scharff & Wautelet (2022)" | none | NOT-A-CLAIM | Citation year. |
| 44 | 8000 | "docker run -p 8000:8000" | code:Dockerfile::8000 | NOT-A-CLAIM | Port matches the container CMD. |

## What the ledger cannot tell you

- Whether every meaning of a number was found. Rows 3, 4 and 9 are the same
  token `100%` read three ways; a fourth reading would need a human to add it.
- Whether a BACKED artifact is still true. `docs/evaluation_report.json` is a
  record of one run on 2026-06-11 against a database this repo does not carry.
  The gate proves the README matches the record, not that the record matches
  the world.
- Non-numeric claims. The README's profile table lists four jurisdictions; the
  API registers two (tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_api_registers_two_of_the_four_readme_profiles). "Zero regressions" and
  "four legal systems" are words, not tokens, and are outside this gate.

## Changing a row

Update the row, the UNBACKED list at the top, and (for rows 9-17) the artifact
or test the row cites, in one commit. The gate rejects a README number without a
row and a row pointing at a test that does not exist.
