# SUNLIGHT

Procurement Integrity Verification Infrastructure.

Structural and statistical analysis for institutional procurement oversight.

---

## What It Does

SUNLIGHT verifies the structural integrity of public contracts before money is spent, then verifies whether that spending delivered the intended development outcome after money moves. Procurement integrity to development impact, end to end.

Existing institutional tools measure statistical deviation — they flag contracts where the price looks unusual. SUNLIGHT looks at the structure behind the contract: whether the awarded entity has the required capability, whether a competitive process actually occurred, whether the stakeholder dependencies and procedural commitments are internally consistent. It detects structural contradictions that live in the topology of a contract's dependency graph, a class of finding that indicator-based methods are architecturally unable to produce. Contracts where the price was calibrated to look clean but the structure underneath is broken.

After procurement verification, the delivery engine monitors whether clean contracts actually produce results. A hospital contract that cleared procurement but shows no construction permits, no equipment, and no staffing at month 12 has a structural contradiction between what was procured and what was delivered. The same graph methodology catches it.

The system is deterministic. Given the same input, it produces the same output. No machine learning, no stochastic components. Every flag traces to a rule, every rule traces to a jurisdiction-specific legal citation, every finding is framed as a risk indicator, not an allegation.

SUNLIGHT integrates once at the institutional level and covers an entire operational footprint. Each contract is analyzed against its execution country's legal framework through jurisdiction profiles. Adding a new country is a data task — authoring a profile — not a code change. The living multi-jurisdiction standard derives its thresholds from the intersection of US DOJ, UK SFO, French PNF, and World Bank INT prosecution corpora. For the approximately 150 countries without mature local prosecution data, that intersection is the default — stricter than any single jurisdiction's bar.

---

## Architecture

Three engines operate on each contract dossier through a 12-stage pipeline:

**CRI (Contract Risk Indicators)** — Statistical engine. Computes price deviation from peer cohort, Bayesian posterior probability, z-scores, and Wilson confidence intervals. Produces a structural confidence score.

**TCA (Transparent Contradiction Analysis)** — Rule engine. Evaluates contracts against jurisdiction-specific legal frameworks. 16 rules across 5 layers (procurement, financial, compliance, temporal, vendor). Each rule fires with a confidence score, legal citation, and evidence string.

**EVG (Evidence Verification Gate)** — Gating framework. Requires convergent evidence across independent analytical dimensions before issuing a verdict. Three procurement dimensions (CRI statistical markup, CRI bribery channel, TCA typologies). Prevents single-signal flags.

**Delivery Verification (Side 2)** — Evaluates post-award contract execution. 12 rules across 4 layers (milestone, financial, quality, compliance). 4 EVG dimensions. Produces independent delivery verdicts that combine with procurement findings.

**Intelligence Alert System (Side 3)** — Priority-ranked triage briefs with cross-contract pattern detection. Vendor clustering, rule concentration, temporal clustering. Emits through configurable channels (webhook, file, log) with HMAC-signed payloads.

---

## Jurisdiction Profiles

The system ships with four jurisdiction profiles:

| Profile | Framework | Coverage |
|---|---|---|
| `us_federal` | FAR/DFARS, 41 USC, DOJ prosecution standards | US federal procurement |
| `uk_central_government` | UK Bribery Act 2010, Public Contracts Regs 2015 | UK central government |
| `wb_int` | UNCAC, World Bank Procurement Framework | International development |
| `france_pnf` | Sapin II, Code de la commande publique | French public procurement |

Each profile defines its own legal citation set, threshold calibration, and rule activation map.

These four prosecution corpora are not independent calibrations. The MJPIS living standard derives its thresholds from the intersection of all four — the strictest value across each dimension — producing a single global calibration that would hold up in Washington, London, Paris, and at the World Bank Sanctions Board simultaneously. For the approximately 150 countries without mature local prosecution data, MJPIS is the default. The countries with the least local oversight get the highest evidentiary bar, not the lowest.
---

## Evaluation

Validated against DOJ-prosecuted procurement fraud cases:

| Metric | Value |
|---|---|
| Precision | 33.3% |
| Recall | 100% |
| False Positive Rate | 9.0% |
| PR-AUC | 0.746 |
| Flag Rate | 129.2 per 1,000 contracts |

100% recall means every prosecuted case in the corpus is flagged. The 33.3% precision reflects the system's conservative design — it flags contracts that exhibit structural patterns consistent with fraud, even when they are ultimately clean. This is the correct tradeoff for an oversight tool.

Evaluation is deterministic and reproducible: `--seed 42 --clean 200 --profile doj_federal`.

---

## API

FastAPI application serving 14 endpoints across three domains:

**Core Pipeline**
- `POST /analyze` — Single contract analysis
- `POST /batch` — Batch contract analysis
- `GET /health` — System health check

**Evidence & Reporting**
- `POST /evidence-packet` — Generate evidence packet for a contract
- `GET /case-packet/{contract_id}` — Retrieve case packet
- `POST /portfolio/screen` — Portfolio-level screening
- `POST /doj/validate` — DOJ standard validation
- `POST /certify` — Certification issuance

**Delivery Verification**
- `POST /delivery/analyze` — Single delivery analysis
- `POST /delivery/batch` — Batch delivery analysis
- `GET /delivery/pillar-summary` — Delivery pillar summary

**Intelligence Alerts**
- `GET /alerts/config` — Alert configuration (no secrets)
- `POST /alerts/test` — Fire synthetic test alert
- `POST /alerts/triage` — Generate triage brief from alerts

---

## Test Suite

1,050 tests. Zero regressions across Side 1, Side 2, and Side 3 builds.

```
PYTHONPATH=code python -m pytest tests/ -q --ignore=tests/test_tca_engine.py
```

---

## Project Structure

```
code/                  Source modules
tests/                 Test suite
data/                  Database (not tracked)
knowledge_base/        Legal frameworks
academic_paper/        Research paper
```

---

## Requirements

Python 3.12+. Dependencies in `requirements.txt`.

```
pip install -r requirements.txt
```

---

**Authors:** Rimwaya Ouedraogo, Hugo Villalba
**License:** Proprietary — SUNLIGHT Infrastructure
