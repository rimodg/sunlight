# SUNLIGHT Database Audit Report

**Database:** `data/sunlight.db` (134 MB)
**Audit Date:** 2026-02-17
**Mode:** Read-only — no data modified

---

## Table Inventory

| Table | Rows | Status |
|---|---|---|
| `contracts` | 42,593 | Active — primary scoring table |
| `contracts_clean` | 337,021 | Active — larger dataset, NOT derived from `contracts` |
| `contract_scores` | 56,556 | Active — scores from 6 completed runs |
| `analysis_runs` | 10 | 6 COMPLETED, 4 stale RUNNING |
| `audit_log` | 16 | Hash chain intact |
| `political_donations` | 4 | All MOCK_DATA |
| `analysis_results` | 0 | Empty — superseded by `contract_scores` |
| `contract_amendments` | 0 | Empty — never populated |

---

## Critical Findings

### 1. Dead Columns (100% NULL)

| Table | Column | NULL Count | Impact |
|---|---|---|---|
| `contracts` | `location` | 42,593 (100%) | Dead weight |
| `contracts` | `raw_data` | 42,593 (100%) | Dead weight |
| `contract_scores` | `raw_data_hash` | 56,556 (100%) | Dead weight |

**Action needed:** Drop these columns or populate them.

### 2. "None" String Contamination in `contracts_clean`

8,764 rows have Python `str(None)` stored instead of SQL NULL:

| Column | "None" String Count | % of 337K |
|---|---|---|
| `award_type` | 8,764 | 2.6% |
| `extent_competed` | 8,764 | 2.6% |
| `description` | 85 | 0.03% |

Additionally, 156 rows have empty string `""` in `extent_competed`.

**Impact:** `WHERE award_type IS NULL` misses these rows. `WHERE extent_competed = 'NOT COMPETED'` won't catch them.

### 3. Redundant Column: `fraud_tier` vs `tier`

`contract_scores` has both `fraud_tier` and `tier` columns. They are **100% identical** across all 56,556 rows. One is fully redundant.

### 4. `contracts` vs `contracts_clean` — Misleading Relationship

| Metric | Count |
|---|---|
| IDs in both tables | 8,118 |
| IDs only in `contracts` | 34,475 |
| IDs only in `contracts_clean` | 328,903 |

These are **not** a raw/clean pipeline pair. They are largely independent datasets from different sources. The scoring engine uses `contracts`, not `contracts_clean`.

### 5. Four Stale RUNNING Analysis Runs

| Run ID | Started | Status |
|---|---|---|
| `run_20260211_160959_42` | 2026-02-11 16:09 | RUNNING (no scores produced) |
| `run_20260211_165021_42` | 2026-02-11 16:50 | RUNNING (no scores produced) |
| `run_20260211_165236_42` | 2026-02-11 16:52 | RUNNING (no scores produced) |
| `run_20260211_185527_42` | 2026-02-11 18:55 | RUNNING (no scores produced) |

These crashed or were interrupted and were never cleaned up.

### 6. Missing Indexes

No user-defined indexes exist. All indexes are auto-generated from PK/UNIQUE constraints.

**Recommended indexes:**

| Table | Column(s) | Row Count | Justification |
|---|---|---|---|
| `contracts` | `vendor_name` | 42K | Frequent GROUP BY / WHERE |
| `contracts` | `agency_name` | 42K | Frequent GROUP BY / WHERE |
| `contracts_clean` | `vendor_name` | 337K | Full scan without index |
| `contracts_clean` | `agency_name` | 337K | Full scan without index |
| `contract_scores` | `run_id` | 56K | Filter by run |
| `contract_scores` | `fraud_tier` | 56K | Filter by tier |

### 7. Foreign Key Enforcement OFF

`PRAGMA foreign_keys = 0`. No FK constraints are enforced at runtime. Logical FK relationships (`contract_scores.contract_id -> contracts.contract_id`) have no schema-level constraint.

### 8. Mock Political Donations

All 4 rows in `political_donations` are flagged `source = MOCK_DATA`. The `date` column is empty for all rows. This feature is a placeholder.

---

## Data Statistics

### contracts — Award Amounts

| Metric | Value |
|---|---|
| MIN | $0.00 (37 contracts at $0) |
| MAX | $51,242,733,558 |
| AVG | $92,594,707 |
| MEDIAN | $26,470,978 |
| TOTAL | ~$3.94 trillion |

### contracts — Agency Distribution (Top 10)

| Agency | Count | % |
|---|---|---|
| Department of Defense | 27,055 | 63.5% |
| Department of Homeland Security | 2,355 | 5.5% |
| Department of Health and Human Services | 2,327 | 5.5% |
| Department of Veterans Affairs | 1,825 | 4.3% |
| General Services Administration | 1,170 | 2.7% |
| Agency for International Development | 1,043 | 2.4% |
| Department of State | 896 | 2.1% |
| NASA | 798 | 1.9% |
| Department of the Treasury | 774 | 1.8% |
| Department of Agriculture | 634 | 1.5% |

### contracts — Top Vendors

| Vendor | Count |
|---|---|
| LOCKHEED MARTIN CORPORATION | 1,192 |
| RAYTHEON COMPANY | 1,063 |
| THE BOEING COMPANY | 874 |
| NORTHROP GRUMMAN SYSTEMS CORPORATION | 837 |
| BOOZ ALLEN HAMILTON INC | 603 |

### contract_scores — Tier Distribution

| Tier | Count | % |
|---|---|---|
| GREEN | 29,917 | 52.9% |
| YELLOW | 21,192 | 37.5% |
| RED | 5,426 | 9.6% |
| GRAY | 21 | 0.04% |

### contract_scores — FDR Results

- Survives FDR: 26,963 (47.7%)
- Does not survive: 29,593 (52.3%)

### contracts_clean — Competition Data (When Valid)

| extent_competed | Count |
|---|---|
| FULL AND OPEN COMPETITION | 145,931 |
| FULL AND OPEN AFTER EXCLUSION | 83,188 |
| NOT COMPETED | 48,549 |
| NOT AVAILABLE FOR COMPETITION | 26,866 |
| COMPETED UNDER SAP | 14,499 |

This data exists but is only usable after fixing the 8,764 "None" strings.

### contracts_clean — num_offers

128,789 rows (38.2%) have `num_offers = 0`, which semantically means "unknown" not "zero offers". 89,806 rows have `num_offers = 1` (sole-source).

---

## Audit Log Integrity

- **16 entries** across 6 completed runs
- Hash chain: **INTACT** (all entries verified)
- Redundant column pairs: `previous_log_hash`/`previous_hash` and `current_log_hash`/`entry_hash` contain identical values per row (migration artifact)

---

## Recommended Actions (Prioritized)

### P0 — Before Next Pipeline Run ✅ COMPLETED 2026-02-17
1. ~~Mark 4 stale RUNNING runs as ABORTED~~ — Done. All 4 set to ABORTED.
2. ~~Add indexes on `vendor_name` and `agency_name` for `contracts` and `contracts_clean`~~ — Done. 6 indexes created: `idx_contracts_vendor_name`, `idx_contracts_agency_name`, `idx_contracts_clean_vendor_name`, `idx_contracts_clean_agency_name`, `idx_contract_scores_run_id`, `idx_contract_scores_fraud_tier`.

### P1 — Data Quality
3. Fix "None" strings in `contracts_clean` (`award_type`, `extent_competed`) -> SQL NULL
4. Fix `num_offers = 0` -> SQL NULL where it means "unknown"
5. Remove 37 contracts with `award_amount = 0`
6. Investigate $51.2B max contract — likely data error

### P2 — Schema Cleanup
7. Drop redundant `tier` column from `contract_scores` (keep `fraud_tier`)
8. Drop dead columns: `contracts.location`, `contracts.raw_data`, `contract_scores.raw_data_hash`
9. Drop redundant audit_log columns (`previous_hash`/`entry_hash` — keep `previous_log_hash`/`current_log_hash`)
10. Drop empty tables: `analysis_results`, `contract_amendments` (if not needed)

### P3 — Schema Hardening
11. Enable `PRAGMA foreign_keys = ON`
12. Add FK constraints on `contract_scores.contract_id` and `contract_scores.run_id`
13. Document relationship between `contracts` and `contracts_clean`
14. Replace mock political donations with real OpenSecrets data
