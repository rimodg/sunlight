# Case Packet: 00500199911C0001500990012

> IMPORTANT: All findings in this case packet are statistical risk indicators, not allegations of fraud. Flagged contracts require human review and investigation before any conclusions can be drawn. Statistical anomalies may have legitimate explanations including market conditions, specialized requirements, or data quality issues.

**Generated:** 2026-02-18T18:38:21Z | **Rulepack:** 2.0.0 | **Snapshot:** 9c0e1fb0856bae08

---

## Contract Summary

| Field | Value |
|---|---|
| Contract ID | `00500199911C0001500990012` |
| Award Amount | $109,153,560 |
| Vendor | HP ENTERPRISE SERVICES, LLC |
| Agency | Department of Health and Human Services |
| Description | PROGRAM SAFEGUARD CONTRACT |
| Start Date | 1999-11-19 |

---

## Risk Assessment

**Tier:** RED | **Confidence:** 62/100 | **Severity:** RED

## Triggered Rules

### PRICE-001: Extreme Price Inflation [CRITICAL]

Bootstrap 95% CI lower bound (340%) exceeds DOJ extreme threshold (300%). This level of markup has been prosecuted under the False Claims Act.

- Threshold: CI lower > 300%
- Actual: 339.9%

### BAYES-002: Elevated Bayesian Fraud Probability [MEDIUM]

Bayesian posterior fraud probability (56.6%) exceeds 50% threshold.

- Threshold: Posterior > 50%
- Actual: 56.6%

### OUTLIER-002: Upper Quartile Outlier [MEDIUM]

Contract amount exceeds 92th percentile of comparable contracts.

- Threshold: Percentile > 75th
- Actual: 91.6th percentile

## Statistical Evidence

| Metric | Value |
|---|---|
| Markup vs. median | 356.4% |
| Bootstrap 95% CI | [339.9%, 371.1%] |
| Bayesian posterior | 56.6% |
| Percentile (CI lower) | 91.6th |
| FDR-adjusted p-value | 0.0002 |
| Survives FDR | Yes |
| Comparable contracts | 2326 |

## Peer Comparison

This contract ($109,153,560) is at the 93th percentile of 2326 comparable contracts in Department of Health and Human Services. The peer median is $23,917,330. This is a statistical risk indicator, not an allegation.

| Peer Statistic | Value |
|---|---|
| Peer count | 2326 |
| Peer median | $23,917,330 |
| Peer P75 | $40,097,280 |
| Peer P95 | $168,397,058 |
| This contract percentile | 93th |
| Deviation from median | 356.4% |

## Vendor Linkages

**Vendor:** HP ENTERPRISE SERVICES, LLC | **Match type:** exact_name | **Confidence:** HIGH

- Total contracts: 3
- Other flagged contracts: 2
  - `00500200210C0006500990012`: RED (confidence 72)
  - `00500200304C0007500990012`: YELLOW (confidence 46)

*Vendor linkages are based on exact name matching. Variations in vendor naming may cause missed linkages. These are indicators for further investigation, not conclusions.*

## Recommended Actions

**Action:** Immediate detailed review recommended

- Request complete cost/pricing data from vendor (FAR 15.403)
- Compare line-item pricing against GSA schedule or commercial equivalents
- Review contract modification history for unexplained cost growth
- Check vendor debarment/suspension status (SAM.gov)
- Investigate pattern across other flagged contracts from this vendor
- If evidence supports, consider referral to OIG or contracting officer

**Escalation path:** OIG Hotline or Contracting Officer for RED-tier findings; Contracting Officer for YELLOW-tier findings

## Analyst Disposition

| Field | Value |
|---|---|
| Status | PENDING_REVIEW |
| Reviewed by | ________________ |
| Date | ________________ |
| Disposition | [ ] TRUE_POSITIVE [ ] FALSE_POSITIVE [ ] BENIGN [ ] NEEDS_INFO |
| Notes | |

---

*SUNLIGHT Case Packet v1.0.0 | Rulepack 2.0.0 | All findings are risk indicators, not allegations.*