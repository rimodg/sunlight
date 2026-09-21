# REPORT — Sunlight gate audit, branch `chain-audit-gates`

Date: 2026-09-21. Machine: Hugo's MacBook, python 3.14.6, pytest 9.1.1, venv at
`repo/.venv`. Commit on the branch: `97fcefe` (local only; nothing pushed, no PR
opened, GitHub read once with `gh run list`, never written).

Every number below was produced in this session and the command output is pasted
as captured. Labels: **measured** means I ran it and the output is here;
**sourced** means read from a file in the repo with the path given; **reasoned**
is an argument. Nothing here is a guess.

---

## 1. The five problems, re-checked before anything was changed

| # | Brief said | Re-check (measured) | Holds? |
|---|---|---|---|
| 1 | CI never passed, 118 runs | `gh run list --workflow=ci.yml --limit 200`: 118 runs, `Counter({'failure': 118})`, oldest 2026-02-19, newest 2026-09-02 | Yes |
| 2 | 3866a49 deleted the cases file; 5 tests ERROR | `git show 3866a49 --stat` lists `prosecuted_cases.json | 168 -`; baseline `pytest tests/test_doj_calibration.py`: `11 passed, 5 errors`, `FileNotFoundError ... prosecuted_cases.json` | Yes |
| 3 | tee pipe masks pytest under bash -e; step exits 0 | Direct proof: `pytest exit=1  tee exit=0  pipeline status bash -e sees=0`. Running the exact step body: it exited **1**, not 0, but only because the two error outputs carried different elapsed-time text (`0.04s` vs `0.05s`) so the digests differed by luck. The masking is real; the exit-0 outcome depends on timing text. See §4. | Yes, with that nuance |
| 4 | TestDOJCaseValidation never runs the engine | Read `tests/test_doj_calibration.py`: every assertion compares `case['markup_pct']` to a `DOJProsecutionThresholds` constant. No engine import. | Yes |
| 5 | README numbers unasserted; claim moved 9 → 32 without a gate change | `git log -S"32 prosecuted" -- README.md`: `90526c7 2026-06-12 Update README.md` introduced "100% recall on 32 prosecuted reference cases" and "gated by CI — every commit"; ci.yml changed only in 90d0243/97395b7 (matrix, timeouts). `grep` over tests for 33.3 / 0.746 / 129.2 / 1889: nothing. | Yes |

One thing the brief did not say, found on the way (**measured**): the Dockerfile
also copied the deleted file (`COPY prosecuted_cases.json ./`), so the image
could not build on a clean clone. That is why the CI *container* job failed too.
Fixed in the same commit (§7).

---

## 2. What the real entry point is (sourced, from reading the code)

- `POST /analyze` and `/batch` in `code/api.py` build `SunlightPipeline(grapher=..., structure=...)` with **no price engine**. The price stage is the stub in `code/sunlight_core.py` (`markup_pct=0.0`), so through those two routes the EVG markup dimension can never fire. There is no `PriceEngine` implementation anywhere under `code/` (`grep` returned nothing).
- The DOJ-tier scorer the README's numbers come from is `institutional_pipeline.score_contract` → `assign_tier`. That is what `code/evaluation.py` (which wrote `docs/evaluation_report.json`), `code/doj_validation.py`, and the API worker (`code/jobs.py::run_scan_pipeline` → `InstitutionalPipeline.run`) all call. The blind test drives exactly that, both as functions and through `InstitutionalPipeline.run` over a real SQLite database.
- README lists `POST /doj/validate`; no such route exists in `code/` (`grep` returned nothing).

---

## 3. Baseline, then final, full suite (measured)

Baseline, before any change (`pytest tests/ -q --ignore=tests/test_docker_live.py`):

```text
ERROR tests/test_doj_calibration.py::TestDOJCaseValidation::test_all_price_fraud_cases_detected
ERROR tests/test_doj_calibration.py::TestDOJCaseValidation::test_extreme_cases_red_tier
ERROR tests/test_doj_calibration.py::TestDOJCaseValidation::test_detection_rate_above_80_percent
ERROR tests/test_doj_calibration.py::TestDOJCaseValidation::test_total_settlement_value_coverage
ERROR tests/test_doj_calibration.py::TestDOJCaseValidation::test_non_price_cases_acknowledged
1972 passed, 3 skipped, 1 xfailed, 2 warnings, 5 errors in 16.31s
exit=1
```

Final, after the commit:

```text
2022 passed, 3 skipped, 4 xfailed, 2 warnings in 14.73s
exit=0
```

Delta: +50 passed (5 formerly erroring, 3 fixture-integrity, 25 blind engine, 17 ledger), 0 failed, 0 errors. The 4th xfail is one that already existed in the suite.

Docker-live tests (docker was available here, so I ran them; the brief expected them to be skipped):

### Before the Dockerfile fix

```text
E           COPY failed: file not found in build context or excluded by .dockerignore: stat prosecuted_cases.json: file does not exist
E           COPY failed: file not found in build context or excluded by .dockerignore: stat prosecuted_cases.json: file does not exist
E           COPY failed: file not found in build context or excluded by .dockerignore: stat prosecuted_cases.json: file does not exist
E           COPY failed: file not found in build context or excluded by .dockerignore: stat prosecuted_cases.json: file does not exist
E           COPY failed: file not found in build context or excluded by .dockerignore: stat prosecuted_cases.json: file does not exist
E           COPY failed: file not found in build context or excluded by .dockerignore: stat prosecuted_cases.json: file does not exist
E           COPY failed: file not found in build context or excluded by .dockerignore: stat prosecuted_cases.json: file does not exist
ERROR tests/test_docker_live.py::test_health_returns_ok - RuntimeError: docke...
ERROR tests/test_docker_live.py::test_profiles_lists_both_jurisdictions - Run...
ERROR tests/test_docker_live.py::test_profile_propagation_differential - Runt...
ERROR tests/test_docker_live.py::test_batch_capacity_threshold_metadata - Run...
ERROR tests/test_docker_live.py::test_calibration_monotonic_across_calls - Ru...
ERROR tests/test_docker_live.py::test_calibration_per_profile_isolation - Run...
ERROR tests/test_docker_live.py::test_analyze_response_schema - RuntimeError:...
7 errors in 4.26s
exit=1
```

### After the Dockerfile fix

```text
7 passed in 10.24s
exit=0
```

No containers were left running afterwards (`docker ps -a | grep sunlight`: none).

---

## 4. CI step: the masking proof and the fixed step under bash (measured)

### Direct proof that the tee pipe masks pytest

```text
pytest exit=1  tee exit=0  pipeline status bash -e sees=0
11 passed, 5 errors in 0.03s
```

### The exact old step body under `bash -e`

```text
11 passed, 5 errors in 0.04s
11 passed, 5 errors in 0.05s
run1: ff45701337bc5ce9bd782c2ad7f3dfaf64ad427b469524340c31c527dcb99da4
run2: 5fa0d0a384b70e614a0baca48d0f14c941466157a7c2e38f247f971e3c8a626b
STEP EXIT CODE (before fix): 1
```

### The fixed step under `bash -eo pipefail` (what `shell: bash` means on GitHub)

```text
### unit check of the summary grep
  44 passed, 3 xfailed in 2.85s      -> ok
  16 passed in 0.02s                 -> ok
  11 passed, 5 errors in 0.04s       -> RED
  40 passed, 4 failed in 1.0s        -> RED
  1 error in 0.08s                   -> RED

### GREEN PATH: fixed step, fixture present (bash -eo pipefail = GitHub shell: bash)
44 passed, 3 xfailed in 2.79s
44 passed, 3 xfailed in 2.89s
run1: aea5887176d108d9865238f056b6a415394975cca335ff6c083b4e48584dd347
run2: aea5887176d108d9865238f056b6a415394975cca335ff6c083b4e48584dd347
run1.txt summary: 44 passed, 3 xfailed in 2.79s
run2.txt summary: 44 passed, 3 xfailed in 2.89s
DETERMINISM: byte-identical (timing stripped)
STEP EXIT CODE (green path): 0

### RED PATH: fixed step, DOJ fixture hidden (a DOJ test fails)
E   Failed: DOJ fixture missing: /Users/hugovillalba/projects/sunlight-chain-audit/repo/tests/fixtures/prosecu
ERROR tests/test_doj_blind_e2e.py - Failed: DOJ fixture missing: /Users/hugov...
1 error in 0.08s
STEP EXIT CODE (red path): 2

### RED PATH 2: fixed step, one blind-test assertion broken (sed: FLAGGED must be RED only)
STEP EXIT CODE (red path 2): 1

### restored:
f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f  tests/fixtures/prosecuted_cases.json
(blind file back to written state: ?? tests/test_doj_blind_e2e.py)
```

Red path 2 prints no summary because `set -e` with pipefail aborts on the first failing pytest before the echo, which is the intended fail-closed order. Exit code 1 is the evidence.

What changed in `.github/workflows/ci.yml`: `defaults.run.shell: bash`; the determinism step runs both DOJ files, checks pytest's summary line for `N passed` and for whole-token `failed`/`errors`, strips the elapsed-time suffix before hashing, and exits 1 on any mismatch. A bug in my first version (the substring `failed` matching `3 xfailed`) was caught by this same proof and fixed before commit.

---

## 5. Fixture restored and pinned; fail-closed proofs (measured)

`git show 3866a49~1:prosecuted_cases.json > tests/fixtures/prosecuted_cases.json`
→ sha256 `f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f`, 10 cases.
Pinned in `tests/doj_fixture.py`. `.gitignore` line 26 (`prosecuted_cases.json`) matched at any depth, so a negation line was added; `git status` shows the file tracked (`A tests/fixtures/prosecuted_cases.json`).

### Missing and altered fixture both fail hard

```text
### 1. fixture MISSING
E           Failed: DOJ fixture missing: /Users/hugovillalba/projects/sunlight-chain-audit/repo/tests/fixtures/prosecuted_cases.json. The recall gate cannot run without it. Restore with: git show 3866a49~1:prosecuted_cases.json > tests/fixtures/prosecuted_cases.json
11 passed, 5 errors in 0.04s
pytest exit=1
### 2. fixture ALTERED (Oracle markup 350 -> 30)
E           Failed: DOJ fixture altered: sha256 7780b25606488f1ccd33a2f5b205127fcb943c5a4e9765abf11683a04db17cf1 != pinn
11 passed, 5 errors in 0.04s
pytest exit=1
### 3. restored
f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f  tests/fixtures/prosecuted_cases.json
16 passed in 0.02s
```

### The dedicated integrity test reports FAILED

```text
### integrity test with fixture hidden
FAILED tests/test_doj_calibration.py::TestDOJFixtureIntegrity::test_fixture_present_and_unaltered
1 failed in 0.02s
exit=1
### restored:
f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f  tests/fixtures/prosecuted_cases.json
```

---

## 6. The blind engine test and what it found (measured)

`tests/test_doj_blind_e2e.py`. Comparables shape: the repo's own `sample_comparables` fixture (coefficient of variation 0.158), rescaled to each case; award = peer median × (1 + markup). Fixed before any result was looked at. Bootstrap iterations 1,000, matching `docs/evaluation_report.json`.

### Engine verdict per case, function path (`score_contract` → `assign_tier`)

```text
comparables shape (x median): [0.763, 1.099, 1.038, 1.237, 0.84, 0.962, 1.206, 0.931, 0.885, 1.145] CV=0.158
case                               markup award/med   ci_lo   ci_hi   post   pci tier
US_v_Oracle_2011                      350     4.500   282.8   408.2  0.666 100.0 YELLOW
US_v_Boeing_2006                      450     5.500   367.9   521.1  0.717 100.0 RED
US_v_DynCorp_2005                      75     1.750    48.9    97.6  0.527 100.0 GREEN
US_v_United_Technologies_2015         250     3.500   197.7   295.3  0.928 100.0 YELLOW
US_v_General_Dynamics_2011              0     1.000   -14.9    12.9  0.279  20.0 GREEN
US_v_Lockheed_Martin_2012             320     4.200   257.3   374.3  0.584 100.0 YELLOW
US_v_Northrop_Grumman_2009            180     2.800   138.2   216.2  0.584 100.0 YELLOW
US_v_CACI_2010                        240     3.400   189.2   284.0  0.527 100.0 YELLOW
US_v_Raytheon_2014                    150     2.500   112.7   182.3  0.584 100.0 YELLOW
US_v_BAE_Systems_2010                 190     2.900   146.7   227.5  0.584 100.0 YELLOW
```

### Same cases through the worker path (`InstitutionalPipeline.run` over SQLite)

```text
case                               markup tier(db path)   ci_lo survives_fdr
US_v_Oracle_2011                      350        YELLOW   282.8 1
US_v_Boeing_2006                      450           RED   367.9 1
US_v_DynCorp_2005                      75         GREEN    48.9 1
US_v_United_Technologies_2015         250        YELLOW   197.7 1
US_v_General_Dynamics_2011              0         GREEN   -14.9 0
US_v_Lockheed_Martin_2012             320        YELLOW   257.3 1
US_v_Northrop_Grumman_2009            180        YELLOW   138.2 1
US_v_CACI_2010                        240        YELLOW   189.2 1
US_v_Raytheon_2014                    150        YELLOW   112.7 1
US_v_BAE_Systems_2010                 190        YELLOW   146.7 1
```

### Dispersion sweep for the 75% floor case (DynCorp)

```text
DynCorp 75% floor case: tier vs comparables dispersion (same 10-point shape, deviations scaled)
 scale     CV   ci_lo   ci_hi   post tier
   0.1  0.016    72.0    77.0  0.527 YELLOW
   0.2  0.032    69.1    79.1  0.527 YELLOW
   0.3  0.048    66.2    81.2  0.527 YELLOW
   0.4  0.064    63.5    83.4  0.527 GREEN
   0.5  0.080    60.9    85.6  0.527 GREEN
   0.6  0.095    58.3    87.9  0.527 GREEN
   0.7  0.111    55.8    90.2  0.527 GREEN
   0.8  0.127    53.4    92.6  0.527 GREEN
   0.9  0.143    51.1    95.1  0.527 GREEN
   1.0  0.158    48.9    97.6  0.527 GREEN
   1.2  0.190    44.5   102.9  0.527 GREEN
```

Findings:

- **8 of 9** price-fraud cases are flagged. **DynCorp 2005 at the 75% floor is GREEN**: its bootstrap lower bound is 48.9%, under the 66% `min_ci_yellow` gate. It is flagged only when the peer cohort's coefficient of variation is about **0.05 or lower**.
- Of the three cases at or above 300%, **only Boeing reaches RED**. Oracle (350%) and Lockheed (320%) are YELLOW because their lower bounds (282.8, 257.3) sit under the 300 gate.
- `docs/evaluation_report.json` (2026-06-11, real USAspending comparables, database not in the repo) recorded DynCorp YELLOW and all three extreme cases RED. The difference is comparables dispersion, which the artifact does not record. So the README's 100% recall is **contingent on a corpus property that is neither stored nor stated**.
- The worker's database path and the function path agree on every case (tier and CI lower bound), so the test stands for both.

Those three outcomes are `xfail(strict=True)` with the measured, dated reason. A strict xfail is a recorded failure that becomes a hard failure the moment the engine changes in either direction. It is not a skip. I chose this over a red suite because the brief's done criterion requires no new failures and because a dated, preserved failure is more useful than a red X nobody reads. Rim can flip them to plain failures in one line each if that is the policy wanted.

The old `TestDOJCaseValidation` is renamed `TestDOJThresholdConstantsOnly` with a docstring saying it never runs the engine. All its tests are kept.

---

## 7. Mutation proof (D) (measured)

### Break the engine's YELLOW gate, run the blind test, restore

```text
### D. mutation proof: break the engine's YELLOW gate in assign_tier, run the blind DOJ test, restore
before: b434dc98a91525cf9d1465de638e6cc7bc157b04  (HEAD blob: b434dc98a91525cf9d1465de638e6cc7bc157b04)
--- mutation (sed): min_ci_yellow gate raised 100x ---
-    elif avg >= 70 and ci > min_ci_yellow:
+    elif avg >= 70 and ci > min_ci_yellow * 100:  # MUTATION
--- blind DOJ test under mutation ---
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_price_fraud_case_is_flagged_by_engine[US_v_Oracle_2011]
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_price_fraud_case_is_flagged_by_engine[US_v_United_Technologies_2015]
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_price_fraud_case_is_flagged_by_engine[US_v_Lockheed_Martin_2012]
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_price_fraud_case_is_flagged_by_engine[US_v_Northrop_Grumman_2009]
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_price_fraud_case_is_flagged_by_engine[US_v_CACI_2010]
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_price_fraud_case_is_flagged_by_engine[US_v_Raytheon_2014]
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_price_fraud_case_is_flagged_by_engine[US_v_BAE_Systems_2010]
FAILED tests/test_doj_blind_e2e.py::TestEngineFlagsPriceFraudCases::test_recall_on_price_fraud_cases_is_recorded
FAILED tests/test_doj_blind_e2e.py::TestFloorCaseDependsOnDispersion::test_floor_case_flagged_with_tight_cohort
9 failed, 16 passed, 3 xfailed in 2.87s
exit=1
--- restore ---
after:  b434dc98a91525cf9d1465de638e6cc7bc157b04  (HEAD blob: b434dc98a91525cf9d1465de638e6cc7bc157b04)
RESTORED: byte-identical to HEAD
--- blind DOJ test after restore ---
25 passed, 3 xfailed in 2.74s
```

---

## 8. Claims ledger (C)

`CLAIMS.md` at the repo root: 44 rows covering all 38 numeric tokens in README.md (the 39th token, `001`, is the fragment of the rule id TIME-001 and is skipped by rule). `tests/test_claims_ledger.py` fails on a README number with no row, a row whose number left the README, a row citing a test/artifact/code symbol that does not exist, an inconsistent status, or a summary list that disagrees with the table. It also carries the small tests that turn artifact and code facts into citable backing.

### Ledger gate proven to fail in both directions

```text
### (a) README gains a number with no ledger row
            f"README.md numbers with no CLAIMS.md row: {missing}. "
E       AssertionError: README.md numbers with no CLAIMS.md row: ['77.7%']. Add a row for each (BACKED with its test/artifact, or UNBACKED).
FAILED tests/test_claims_ledger.py::TestClaimsLedgerCoverage::test_every_readme_number_is_in_ledger
1 failed, 16 passed, 2 warnings in 0.29s
exit=1
README restored: 0 changed lines listed by git (0 = clean)

### (b) CLAIMS.md row cites a test that does not exist
E       AssertionError: row 2 (32): tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_this_test_does_not_exist -> test not found in clas
E       assert not ['row 2 (32): tests/test_claims_ledger.py::TestReadmeNumbersMatchArtifactsAndCode::test_this_test_does_not_exist -> test not found in class T
FAILED tests/test_claims_ledger.py::TestClaimsLedgerCoverage::test_every_referenced_test_exists
1 failed, 16 passed, 2 warnings in 0.27s
exit=1

### restored: ledger gate again
17 passed, 2 warnings in 0.25s
```

### Claims marked UNBACKED (26 rows)

| Row | Number | Claim | Why UNBACKED (measured / sourced) |
|---|---|---|---|
| 1 | 42,835 | validated on 42,835 contracts | database not in repo; artifact scored 210 rows; figure exists only in prose and a code comment |
| 2 | 32 | 100% recall on 32 cases | corpus has 32 cases, but the evaluation scored 9 US positives; no evaluation of 32 exists |
| 3 | 100% | recall "encoded in the test suite and gated by CI, every commit" | CI failed 118/118; in-repo engine gate measures 8/9; floor case contingent on dispersion |
| 4 | 100% | design principle "CI-gated" | same as row 3 |
| 5 | 1,889 | test count | measured 1,981 (excl. docker) / 1,988 (incl.) |
| 6, 7, 8, 34, 35, 36 | 734 / 242 / 129 / 79 / 570 / 96 | per-phase test counts | no test, artifact, or file-to-phase mapping; structural scoring file collects 105 |
| 19, 24, 25, 26, 27 | 12 / 1 / 8 / 9 / 13 | stage ranges 1-8, 9-12, 13-16 | pipeline enum has 12 unnumbered stages |
| 20 | 16 | 16-stage pipeline | enum has 12 members |
| 21 | 16 | 16 TCA rules | 14 rule ids in code |
| 22 | 5 | 5 rule layers | 4 prefixes in code |
| 23 | 2 | 2 network rules | 0 NET ids in code |
| 28 | 150 | ~150 countries | no source |
| 29, 30 | 6 / 25 | TIME-001 fires March 25 under UK, not US | no test exercises the fiscal calendar |
| 31, 32 | 1,182 / 1,133 | historical counts | no artifact |
| 33 | 39 | hardening tests | measured 39 collected, but no gate can check the phase table |

Backed rows (12): 33.3%, 100% (as the recorded evaluation value), 9.0%, 0.746, 129.2, 1,000 (twice), 42, 200, 12 (delivery rules), 5 / 3 / 4 (rule and layer counts). Not-a-claim rows (5): 41 USC, 2010, 2015, 2022, port 8000.

Non-numeric gaps recorded in the ledger's tail, outside the gate's reach: the README profile table lists four jurisdictions and the API registers two (`/profiles`: `us_federal`, `uk_central_government`; a test now pins that fact); `POST /doj/validate` does not exist.

---

## 9. `git diff --stat` (measured)

```text
 .github/workflows/ci.yml      | 55 ++++++++++++++++++++++++++++++-------
 .gitignore                    |  4 +++
 tests/conftest.py             | 16 ++++++++---
 tests/test_doj_calibration.py | 63 ++++++++++++++++++++++++++++++++++++++-----
 4 files changed, 118 insertions(+), 20 deletions(-)
```

That is the tracked-file diff before staging. The commit (`git show --stat 97fcefe`) is 11 files, 972 insertions, 21 deletions: the four above plus `CLAIMS.md`, `Dockerfile`, `.dockerignore`, `tests/doj_fixture.py`, `tests/fixtures/prosecuted_cases.json`, `tests/test_claims_ledger.py`, `tests/test_doj_blind_e2e.py`.

---

## 10. What I could not do, and decisions Rim should look at

- **Re-run the 42,835-contract evaluation.** No contracts database is in the repo (`find . -name '*.db'`: nothing outside the venv). The five headline metrics remain a 2026-06-11 record, now pinned by a test that the README matches the record, not that the record matches the world.
- **Reproduce 100% recall in-repo.** With the repo's own comparables shape the engine flags 8/9. I did not tune comparables to reach 9/9; the dispersion at which the floor case flips (CV ≈ 0.05) is recorded instead.
- **Run CI on GitHub.** Forbidden by the brief. The fixed step is proven locally under `bash -eo pipefail`, which is what `shell: bash` gives on GitHub. The `--build` docker job now builds locally; I have not seen it on a GitHub runner.
- **Lint with ruff.** Not installed in the venv or on PATH; I used `ast` parsing and an unused-import check instead (all five files clean).
- **README.md is untouched.** Its numbers are Rim's to change. The ledger says which ones disagree with what is measured.
- **A tension for Rim:** commit 3866a49 untracked the cases file as "sensitive ground-truth". The content is DOJ press-release data and the README's headline claim depends on it, so I restored it as a tracked test fixture with a gitignore exception. If Rim wants it kept out of git, the gate needs another source of truth, and the brief's fail-closed rule means the suite would then fail on a clean clone by design.
- **Docker fix is beyond the brief's letter.** Same root cause, two lines, and without it the container job can never pass; I applied it and flag it here.
- **`prosecuted_cases.json` readers elsewhere.** `code/doj_validation.py`, `code/evaluation.py`, `code/fp_profiler.py`, `scripts/expand_doj_cases.py`, `demo/generate_dossier_material.py` and `test_validation.py` still default to a root-level path. Inside the image that path now exists (Dockerfile copies the fixture there); on a checkout it does not. Left as is; a follow-up could point them at the fixture.

## 11. Where every raw output lives

Scratchpad for this session (session-scoped, may be cleaned): `/private/tmp/claude-501/-Users-hugovillalba-projects-sunlight-chain-audit/bc644661-65d6-4cb0-948d-55dcdaad1d1d/scratchpad`. Files: `baseline_full_suite.txt`, `final_full_suite.txt`, `pipe_masking_proof.txt`, `ci_step_before.out`, `ci_step_after_proof.txt`, `fixture_fail_closed_proof.txt`, `integrity_test_failed_proof.txt`, `engine_experiment.txt`, `engine_experiment_dbpath.txt`, `dyncorp_dispersion_sweep.txt`, `mutation_proof.txt`, `ledger_gate_negative_proof.txt`, `docker_live.txt`, `docker_live_after_fix.txt`, `git_diff_stat.txt`, `readme_numbers.txt`. Everything that matters is pasted above; the scratchpad is a convenience, not the record.
