# SUNLIGHT System Card

**Version:** 2.0.0
**Date:** 2026-02-18
**Classification:** Internal / Client-facing

---

## 1. Purpose

SUNLIGHT is a statistical anomaly detection system for government procurement contracts. It identifies contracts with pricing patterns that are statistically consistent with known fraud cases prosecuted by the U.S. Department of Justice (DOJ).

**SUNLIGHT does NOT:**
- Make fraud determinations
- Replace human investigators
- Provide legal evidence on its own
- Detect non-price fraud (bid rigging, false certification, kickbacks without price impact)

**Every flag is a statistical risk indicator, not an allegation of fraud.** All flags require human review, investigation, and corroboration before any action is taken.

---

## 2. Typologies Covered

| ID | Typology | Detection Method | Threshold |
|---|---|---|---|
| PRICE-001 | Extreme Price Inflation | BCa Bootstrap CI | CI lower bound > 300% markup |
| PRICE-002 | High Price Inflation | BCa Bootstrap CI | CI lower bound > 200% markup |
| PRICE-003 | Elevated Price Anomaly | BCa Bootstrap CI | CI lower bound > 75% markup |
| BAYES-001 | High Bayesian Posterior | Bayesian inference | Posterior probability > 80% |
| BAYES-002 | Elevated Bayesian Posterior | Bayesian inference | Posterior probability > 50% |
| OUTLIER-001 | Extreme Percentile Outlier | Percentile ranking | > 95th percentile among peers |
| OUTLIER-002 | Upper Quartile Outlier | Percentile ranking | > 75th percentile among peers |

### Not Covered

- Bid rigging / collusion (requires bid-level data, not contract amounts)
- False certification / compliance fraud (requires document analysis)
- Conflict of interest (requires personnel / relationship data)
- Quality fraud / substitution (requires performance data)
- Kickbacks without price impact (no statistical price signal)

---

## 3. Statistical Methods

| Method | Purpose | Configuration |
|---|---|---|
| **BCa Bootstrap** | Confidence intervals on markup percentages | 1,000 iterations, 95% confidence level |
| **Bayesian Posterior** | Probability of fraud given observed markup | DOJ base-rate prior (3.2%) |
| **Benjamini-Hochberg FDR** | Multiple testing correction across contract portfolios | alpha = 0.10 |
| **Percentile Ranking** | Position of contract price among comparable peers | Agency + value-band peer groups |

All thresholds are calibrated against DOJ prosecution precedent (documented in `DOJProsecutionThresholds`).

---

## 4. Tier Classification

| Tier | Meaning | Criteria |
|---|---|---|
| **RED** | Prosecution-grade anomaly | CI lower > 300% OR (avg confidence >= 90 AND survives FDR) |
| **YELLOW** | Investigation-worthy | Average confidence >= 70 |
| **GREEN** | Normal pricing | Below investigation threshold |
| **GRAY** | Insufficient data | < 5 comparable contracts OR low data confidence |

### Severity Downgrade Rules

If input data confidence is low (missing fields, ambiguous formats, heavily normalized values), SUNLIGHT automatically downgrades severity:

| Data Confidence | Action |
|---|---|
| < 30% | Downgrade to GRAY ("insufficient data") regardless of statistical signal |
| 30-50% | Downgrade RED to YELLOW; add "verify against source documents" note |
| > 50% | No downgrade |

---

## 5. Human-in-the-Loop Requirements

SUNLIGHT is designed as a **triage tool**, not an autonomous decision-maker. The required human workflow is:

1. **System flags** contracts with statistical anomalies
2. **Analyst reviews** the case packet (typology, evidence, peer comparison, vendor linkages)
3. **Analyst dispositions** each flag: TRUE_POSITIVE, FALSE_POSITIVE, BENIGN, or NEEDS_INFO
4. **Supervisor approves** disposition decisions
5. **Only after human review** can a flag proceed to investigation referral

### Controls Enforcing Human Review
- Every case packet includes the disclaimer: "risk indicators, not allegations"
- Disposition tracking is mandatory (flags remain PENDING_REVIEW until acted on)
- Audit log records who reviewed, when, and what decision was made
- No automated escalation — all referrals require explicit human action

---

## 6. Limitations & Known Weaknesses

### Statistical Limitations
- **Small validation set**: Evaluation is based on ~8 DOJ-prosecuted cases. Confidence intervals reflect this uncertainty.
- **Prevalence dependency**: Operational precision depends on real-world fraud prevalence, which varies by agency, contract type, and time period.
- **Comparable selection**: Peer groups are defined by agency + value band. Narrow peer groups (< 5 contracts) produce GRAY results.
- **Historical bias**: DOJ prosecution data skews toward large, high-profile cases. Detection of small-value fraud patterns is less validated.

### Data Limitations
- System quality depends on input data quality. Missing vendor names, inconsistent IDs, or incorrect amounts reduce detection confidence.
- Currency conversion is not performed — all amounts are compared within their reported currency.
- No entity resolution beyond vendor name normalization (no DUNS, SAM, or LEI matching).

### Deployment Limitations
- Single-database architecture (no multi-tenant isolation)
- No real-time streaming — batch analysis only
- Evidence package generation is CPU-intensive (~30s per contract)

---

## 7. Bias & Fairness Considerations

### What SUNLIGHT Does NOT Use for Scoring
- Vendor demographic information (ownership status, size classification)
- Geographic location of vendor
- Vendor's prior flag history (each contract scored independently)
- Political donation history (shown in case packet for context, NOT used in scoring)

### Potential Sources of Bias
1. **Agency peer groups**: Contracts are compared within agency + value band. Agencies with fewer contracts may produce more GRAY results.
2. **DOJ prosecution bias**: Validation is based on DOJ cases, which may over-represent certain industries or contract types.
3. **Value-band bias**: Very large or very small contracts have fewer peers, potentially increasing false positive rates.

### Mitigations
- Confidence scoring tracks data quality per field — low-quality data triggers severity downgrade
- GRAY tier explicitly labels "insufficient data" rather than forcing a classification
- Case packets show peer comparison details so analysts can assess reasonableness
- Political donation data is informational context only, never used in scoring algorithms

---

## 8. Governance & Auditability

| Control | Implementation |
|---|---|
| **Versioned Rulepack** | Each score records the rulepack version and hash used |
| **Immutable Audit Log** | SHA-256 hash chain covering all scoring operations, dispositions, exports |
| **Data Snapshot ID** | Each analysis records a hash of the input dataset |
| **Config Hash** | Each run records the configuration parameters used |
| **Code Commit Hash** | Each run records the git commit of the codebase |

### Rulepack Versioning
- Current version: **2.0.0** (released 2026-02-18)
- Rulepack changes are tracked in `governance.py:RULEPACK_REGISTRY`
- Hash verification: `compute_rulepack_hash(version)` produces deterministic SHA-256

---

## 9. Update Process

| Event | Required Actions |
|---|---|
| New rulepack version | 1. Add to RULEPACK_REGISTRY. 2. Update CURRENT_RULEPACK. 3. Document changes. 4. Re-run evaluation. 5. Verify CI gates pass. |
| New detection typology | 1. Add rule definition. 2. Implement detection logic. 3. Add tests. 4. Validate against DOJ cases. 5. Update system card. |
| Threshold change | 1. Document justification. 2. Re-run evaluation. 3. Compare metrics to previous version. 4. Obtain stakeholder approval. |
| New data source | 1. Document source and quality. 2. Add normalization rules. 3. Test with messy inputs. 4. Update system card. |

---

## 10. Contact & Responsibility

- **System Owner:** SUNLIGHT Development Team
- **Evaluation Review:** Quarterly (or upon rulepack change)
- **Incident Response:** Any false positive identified in production should be reported, dispositioned, and used to refine evaluation metrics

---

*This system card should be reviewed and updated whenever detection typologies, thresholds, data sources, or deployment architecture change.*
