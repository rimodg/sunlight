# SUNLIGHT

**Procurement Integrity Verification Infrastructure**

Structural and statistical analysis for institutional procurement oversight.

## What It Does

SUNLIGHT verifies the structural integrity of public contracts before money is spent, then verifies whether that spending delivered the intended development outcome after money moves. When procurement corruption is caught, the system tracks recovered funds, maps them against the institution's own stated development goals, computes gap-weighted reallocation recommendations proportional to where the institution is furthest behind its own stated goals, and verifies that redeployed funds deliver results. Procurement integrity to development impact, end to end. Catch, redirect, verify, report.

Existing institutional tools measure statistical deviation — they flag contracts where the price looks unusual. SUNLIGHT looks at the structure behind the contract: whether the awarded entity has the required capability, whether a competitive process actually occurred, whether the stakeholder dependencies and procedural commitments are internally consistent. It detects structural contradictions that live in the topology of a contract's dependency graph, a class of finding that indicator-based methods are architecturally unable to produce. Contracts where the price was calibrated to look clean but the structure underneath is broken.

The system is deterministic. Given the same input, it produces the same output. No machine learning, no stochastic components. Every flag traces to a rule, every rule traces to a jurisdiction-specific legal citation, every finding is framed as a risk indicator, not an allegation.

SUNLIGHT integrates once at the institutional level and covers an entire operational footprint. Each contract is analyzed against its execution country's legal framework through jurisdiction profiles. Adding a new country is a data task — authoring a profile — not a code change.

## Architecture

Four systems operate on each contract dossier:

**CRI (Contract Risk Indicators)** — Statistical engine. Computes price deviation from peer cohort, Bayesian posterior probability, z-scores, and Wilson confidence intervals. Produces a structural confidence score.

**TCA (Transparent Contradiction Analysis)** — Rule engine. Constructs a structural dependency graph of each contract's stakeholders, capabilities, and procedural commitments, then identifies topological contradictions through graph analysis. 16 rules across 5 layers (procurement, financial, compliance, temporal, vendor). Each rule fires with a confidence score, legal citation, and evidence string. Grounded in the i* Strategic Dependency Framework (Heng, Tsilionis, Scharff & Wautelet, 2022).

**EVG (Evidence Verification Gate)** — Gating framework. Requires convergent evidence across independent analytical dimensions before issuing a verdict. Three procurement dimensions (CRI statistical markup, CRI bribery channel, TCA typologies). Prevents single-signal flags from reaching high-confidence tiers.

**Delivery Verification (Side 2)** — Evaluates post-award contract execution. 12 rules across 4 layers (milestone, resource, outcome, financial reconciliation). 4 EVG dimensions. Produces independent delivery verdicts that combine with procurement findings. A contract that cleared procurement but shows no construction permits, no equipment, and no staffing at month 12 has a structural contradiction between what was procured and what was delivered. The same graph methodology catches it.

**Intelligence Alert System (Side 3)** — Priority-ranked triage briefs with cross-contract pattern detection. Vendor clustering, rule concentration, temporal clustering, pillar concentration, financial escalation. Emits through configurable channels (webhook, file, log) with HMAC-signed payloads. Deterministic intelligence summaries where every word traces to a data point.

**Recovery Intelligence (Side 4)** — Closes the loop. Tracks recovered funds from flagged contracts, reads the institution's own Country Programme Document allocation targets, computes gap-weighted redirection recommendations proportional to where the institution is furthest behind its own stated goals, and verifies that redeployed funds deliver results through Side 1 and Side 2. Produces institutional impact reports tracing the full cycle from corruption caught to beneficiaries reached. The institution's own published commitments determine the allocation. SUNLIGHT reads the plan, identifies the gaps, and recommends. The institution decides.

Every engine reads its calibration from the jurisdiction profile loaded for the contract's execution country. When CRI computes price deviation, the tolerance band comes from the profile. When TCA evaluates competitive procurement thresholds, the legal threshold and citation come from the profile. When EVG assigns tier, the evidentiary standard comes from the profile. The same rules, the same statistical methodology, the same gating logic — calibrated differently for each country's legal framework. One engine, many jurisdictions. Adding a new country means authoring a profile, not changing the engine.

## Jurisdiction Profiles

| Profile | Framework | Coverage |
|---------|-----------|----------|
| us_federal | FAR/DFARS, 41 USC, DOJ prosecution standards | US federal procurement |
| uk_central_government | UK Bribery Act 2010, Public Contracts Regs 2015 | UK central government |
| wb_int | UNCAC, World Bank Procurement Framework | International development |
| france_pnf | Sapin II, Code de la commande publique | French public procurement |

Each profile defines its own legal citation set, threshold calibration, and rule activation map. Behavioral verification is confirmed across profiles: the same rule (TIME-001) fires correctly on March 25 under the UK profile (6 days before UK fiscal year-end) and correctly does not fire under US federal (March is a safe month in the US federal calendar). Same rule, different profile, jurisdiction-correct output.

## Living Standard (MJPIS)

These four prosecution corpora are not independent calibrations. The Multi-Jurisdiction Procurement Integrity Standard derives its thresholds from the intersection of all four — the strictest value across each dimension — producing a single global calibration that would hold up in Washington, London, Paris, and at the World Bank Sanctions Board simultaneously.

For the approximately 150 countries without mature local prosecution data, MJPIS is the default. The countries with the least local oversight get the highest evidentiary bar, not the lowest. When the corpus expands with new prosecuted cases from additional jurisdictions, the derivation reruns automatically and every deployment referencing the MJPIS version string inherits the updated values. The standard breathes with the data.

## Evaluation

Validated on 42,835 real US federal procurement contracts from USAspending.gov, with 100% recall on 32 prosecuted reference cases spanning four legal systems (US DOJ, UK SFO, French PNF, World Bank INT).

| Metric | Value |
|--------|-------|
| Precision | 33.3% |
| Recall | 100% |
| False Positive Rate | 9.0% |
| PR-AUC | 0.746 |
| Flag Rate | 129.2 per 1,000 contracts |

100% recall means every prosecuted case in the corpus is detected. No exceptions. This floor is encoded in the test suite and gated by CI — every commit, every threshold update, every engine change preserves it. The 33.3% precision reflects the system's design: it flags contracts exhibiting structural patterns consistent with prosecuted fraud, even when those contracts are ultimately clean. For an institutional oversight tool, missing a corrupt contract is catastrophic; flagging a clean one is a manageable investigative cost. The system is calibrated accordingly.

Evaluation is deterministic and reproducible: `--seed 42 --clean 200 --profile doj_federal`.

## API

REST API via FastAPI with auto-generated OpenAPI documentation. Stateless — contract in, verdict out, nothing stored. Designed for integration into institutional pipelines behind the deploying institution's own authentication layer.

**Core Pipeline**
- `POST /analyze` — Single contract structural analysis with jurisdiction profile
- `POST /batch` — Batch analysis, up to 1,000 contracts per request
- `GET /health` — Liveness and readiness probe
- `GET /version` — Deployment metadata, MJPIS version, registered profiles
- `GET /profiles` — All registered jurisdiction profiles with metadata

**Evidence and Reporting**
- `POST /evidence-packet` — Generate evidence packet for a contract
- `GET /case-packet/{contract_id}` — Retrieve investigator-ready case packet
- `POST /portfolio/screen` — Portfolio-level screening
- `POST /doj/validate` — DOJ standard validation
- `POST /certify` — Certification issuance

**Delivery Verification**
- `POST /delivery/analyze` — Single contract delivery verification
- `POST /delivery/batch` — Batch delivery verification
- `GET /delivery/pillar-summary` — Country office development pillar aggregation

**Intelligence Alerts**
- `GET /alerts/config` — Alert configuration (no secrets exposed)
- `POST /alerts/test` — Fire synthetic test alert through all emitters
- `POST /alerts/triage` — Generate triage brief with ranking, pattern detection, executive summary

**Recovery Intelligence**
- `POST /recovery/record` — Create recovery record when institution acts on a RED flag
- `POST /recovery/confirm` — Confirm contract cancellation or modification
- `POST /recovery/allocate` — Compute gap-weighted allocation from institution's CPD targets
- `POST /recovery/redirect` — Link recovered funds to new contract (enters Side 1 and Side 2 automatically)
- `GET /recovery/status/{recovery_id}` — Full recovery lifecycle with linked redirections and verdicts
- `GET /recovery/impact` — Institutional impact report: caught, redirected, verified, beneficiaries reached
- `GET /recovery/cycle/{source_contract_id}` — Complete traceability from RED flag to development outcome

## Deployment

Containerized via Docker. Stateless architecture — the engine stores nothing. Contract data enters, case packets exit. The deploying institution controls data residency, authentication, and routing at the deployment boundary.

```bash
docker build -t sunlight .
docker run -p 8000:8000 sunlight
```

## Test Suite

1,133 tests across four build phases. Zero regressions.

| Phase | Description | Tests |
|-------|-------------|-------|
| Side 1 | Procurement verification (CRI + TCA + EVG) | 683 |
| Side 2 | Delivery verification | 242 |
| Side 3 | Intelligence alerts | 129 |
| Side 4 | Recovery intelligence | 79 |

DOJ regression baseline preserved across every commit: 33.3% / 100% / 9.0% / 0.746 / 129.2.

```bash
PYTHONPATH=code python -m pytest tests/ -q --ignore=tests/test_tca_engine.py
```

## Academic Foundation

TCA operationalizes the i* Strategic Dependency Framework published by Dr. Christelle Scharff (Pace University, Seidenberg School of Computer Science) and colleagues in Heng, Tsilionis, Scharff & Wautelet (2022). The i* framework provides the formal dependency-modeling semantics. SUNLIGHT translates those semantics into a deterministic rule engine that detects structural contradictions no indicator-based method can surface.

## Design Principles

- Deterministic logic over probabilistic guessing — every detection traces from result to inputs
- Every detection explainable in language an investigator understands
- A flag is a risk indicator, not an allegation
- An allocation is a recommendation, not a directive
- 100% DOJ recall is the institutional credibility floor — zero tolerance, CI-gated
- Jurisdiction calibration is a data task, not a code task
- The living standard is primary calibration for the majority of the operational footprint
- Recovered funds are redirected using the institution's own published commitments, not external opinion
- Ground truth before code — no engineering begins from assumed state

---

Built by Rimwaya Ouedraogo and Hugo Villalba.
