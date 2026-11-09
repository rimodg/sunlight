# SUNLIGHT

See the [organizational watch rebuild and measured verification](docs/MILESTONE_1A_REBUILD_2026-11-05.md), with the [macOS service guide](docs/MACOS_WATCH_SERVICE.md). Native Mac/reboot and full-suite acceptance remain open.

The long-term direction is **The Global Humanitarian Watch**. Procurement is
the operational entry point; broader categories must earn their own validated
coverage. Read the [charter](docs/CHARTER_v2_global_humanitarian_watch.md) and the
[institutional review brief](docs/INSTITUTIONAL_REVIEW.md) for current capability
boundaries, the evaluation protocol, and a reproducible demonstration.

The dashboard's default page is a live evidence workspace: supplied JSON goes
through the API, and results expose findings, normalized-input gaps, calculation
traces, and downloadable content-addressed receipts. It does not present random
fixture scores as operational results. Historical evaluation metrics below come from a constructed regression population,
not independently labeled prosecuted outcomes. They do not establish field accuracy.

Read the [master plan and implementation notes](docs/plans/README.md) for the next proof gates and the distinction between implemented, measured and proposed work.

**Procurement Integrity Verification Infrastructure**

Structural and statistical analysis for institutional procurement oversight.

## What It Does

SUNLIGHT verifies the structural integrity of public contracts before money is spent, then verifies whether that spending delivered the intended development outcome after money moves. When procurement corruption is caught, the system tracks recovered funds, maps them against the institution's own stated development goals, computes gap-weighted reallocation recommendations proportional to where the institution is furthest behind its own stated goals, verifies that redeployed funds deliver results, and corroborates the claimed outcome against independent evidence that never routes through the party being verified. Procurement integrity, delivery verification, intelligence alerting, recovery redirection, and independent evidence corroboration — the full lifecycle of institutional funds. Catch, redirect, verify, corroborate, report.

Existing institutional tools measure statistical deviation — they flag contracts where the price looks unusual. SUNLIGHT looks at the structure behind the contract: whether the awarded entity has the required capability, whether a competitive process actually occurred, whether the stakeholder dependencies and procedural commitments are internally consistent. It detects structural contradictions that live in the topology of a contract's dependency graph, a class of finding that indicator-based methods are architecturally unable to produce. Contracts where the price was calibrated to look clean but the structure underneath is broken.

The system is deterministic. Given the same input, it produces the same output. No machine learning, no stochastic components. Every flag traces to a rule, every rule traces to a jurisdiction-specific legal citation, every finding is framed as a risk indicator, not an allegation.

SUNLIGHT integrates once at the institutional level and covers an entire operational footprint. Each contract is analyzed against its execution country's legal framework through jurisdiction profiles. Adding a new country is a data task — authoring a profile — not a code change.

## Architecture

A 16-stage pipeline runs across five sides: stages 1-8 procurement, stages 9-12 delivery, stages 13-16 evidence corroboration. Seven engines operate on each dossier:

**CRI (Contract Risk Indicators)** — Statistical engine. Computes price deviation from peer cohort, Bayesian posterior probability, z-scores, and Wilson confidence intervals. Produces a structural confidence score.

**TCA (Transparent Contradiction Analysis)** — Rule engine. Constructs a structural dependency graph of each contract's stakeholders, capabilities, and procedural commitments, then identifies topological contradictions through graph analysis. 16 rules across 5 layers (procurement 5, entity 3, financial 3, temporal 3, network 2). Each rule fires with a confidence score, legal citation, and evidence string. Grounded in the i* Strategic Dependency Framework (Heng, Tsilionis, Scharff & Wautelet, 2022).

**EVG (Evidence Verification Gate)** — Gating framework. Requires convergent evidence across independent analytical dimensions before issuing a verdict. Three procurement dimensions (CRI statistical markup, CRI bribery channel, TCA typologies). Prevents single-signal flags from reaching high-confidence tiers.

**Delivery Verification (Side 2)** — Evaluates post-award contract execution. 12 rules across 4 layers (milestone, resource, outcome, financial reconciliation). 4 EVG dimensions. Produces independent delivery verdicts that combine with procurement findings. A contract that cleared procurement but shows no construction permits, no equipment, and no staffing at month 12 has a structural contradiction between what was procured and what was delivered. The same graph methodology catches it.

**Intelligence Alert System (Side 3)** — Priority-ranked triage briefs with cross-contract pattern detection. Vendor clustering, rule concentration, temporal clustering, pillar concentration, financial escalation. Emits through configurable channels (webhook, file, log) with HMAC-signed payloads. Deterministic intelligence summaries where every word traces to a data point.

**Recovery Intelligence (Side 4)** — Closes the loop. Tracks recovered funds from flagged contracts, reads the institution's own Country Programme Document allocation targets, computes gap-weighted redirection recommendations proportional to where the institution is furthest behind its own stated goals, and verifies that redeployed funds deliver results through Side 1 and Side 2. Produces institutional impact reports tracing the full cycle from corruption caught to beneficiaries reached. The institution's own published commitments determine the allocation. SUNLIGHT reads the plan, identifies the gaps, and recommends. The institution decides.

**Evidence Corroboration (Side 5)** — The final gate. Corroborates claimed outcomes against six independent evidence classes (institutional records, third-party administrative records, geospatial imagery, independent field verification, beneficiary-side signal, and adversarial/open signal) that do not route through the implementing partner. Detects the contradiction no documentary review can reach: a claim that passed every procurement and delivery gate but that independent evidence does not support. Produces four verdicts — VERIFIED, PARTIAL, UNVERIFIED, CONTRADICTED — and architecturally refuses to conflate UNVERIFIED (insufficient queryable evidence) with CONTRADICTED (evidence actively contradicts the claim), so a country with thin digital infrastructure is never flagged for fraud on absence alone. Every artifact carries a provenance chain (source, digest, timestamp); evidence content is hashed at ingestion and discarded, never stored. The recovery loop cannot close on an uncorroborated claim.

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

The stored historical report used a 42,835-contract comparison database to
construct a regression evaluation: nine synthesized positive price examples,
200 presumed-negative comparisons and one excluded case. These are not nine
independently observed prosecuted contracts. The figures below describe that
constructed population only; they do not measure field accuracy.

| Metric | Reported result |
|--------|-----------------|
| Precision | 33.3% |
| Recall | 100% |
| False Positive Rate | 9.0% |
| PR-AUC | 0.746 |
| Flag Rate | 129.2 per 1,000 evaluated contracts |

The recorded confusion matrix is TP 9, FN 0, FP 18, TN 182. These are sampled
evaluation counts, not 42,835 independently labeled outcomes. No misses among
nine synthesized positive examples does not establish recall on real cases. A separate
multi-jurisdiction research corpus contains 32 case records; that count must not
be substituted for the evaluated positives in this confusion matrix.

The intended operational use is analyst screening: flagged records need review,
and a flag is not an allegation. The complete reference database and exact
sampling protocol are required to reproduce these historical results. Current
unit-test results and browser demonstrations are separate evidence. See the
[institutional review protocol](docs/INSTITUTIONAL_REVIEW.md) before citing a
performance claim.

The recorded protocol uses `--seed 42 --clean 200 --profile doj_federal`.
Reproduction also requires the exact reference database and case fixture. The
current sandbox lacks that database, so neither reference protocol has been
rerun for this branch. A previous result is not a new measurement.

## API

REST API via FastAPI with auto-generated OpenAPI documentation. Supplied-record analysis and the persistent organizational watch are distinct workflows. The watch journal retains admitted frozen response bytes, observations, findings and operational receipts in the operator-configured external data directory. Other API workflows also maintain operational calibration or recovery state, so the application must not be described as wholly stateless. The one exception is deliberate and bounded: corroboration dossiers are held in an in-process cache so a result can be inspected after the fact. That cache is capped, evicts oldest-first, does not survive a restart, and says so in its own responses — it is not a database, and no audit trail should be built on it. It retains provenance (source, digest, timestamp) and never artifact content. Designed for integration into institutional pipelines behind the deploying institution's own authentication layer.

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

**Evidence Corroboration**
- `POST /evidence/analyze` — Corroborate a claimed outcome across six independent evidence classes
- `POST /evidence/batch` — Batch corroboration, up to 1,000 claims
- `GET /evidence/expected/{outcome_type}` — Publish what evidence SUNLIGHT will look for, before submission
- `GET /evidence/capacity/{country_code}` — Honest disclosure of which evidence classes are queryable in a jurisdiction and the resulting confidence ceiling
- `GET /evidence/dossier/{dossier_id}` — Retrieve a corroboration dossier (ephemeral cache, not a database)
- `POST /evidence/verify-integrity` — Detect post-ingestion tampering via provenance hash

## Deployment

Containerized via Docker. The deploying institution controls data residency, authentication, backups and routing. The watch is a separate persistent service: its admitted frozen capture bodies and journal survive restarts in operator storage. Corroboration artifacts use a separate digest-only path; that does not mean the whole system discards all source content. Preserve operational state before taking an old deployment offline or replacing it.

```bash
docker build -t sunlight .
docker run -p 8000:8000 sunlight
```

## Test Suite

The last locally measured watch subset, from a fresh clone on November 5,
2026, passed **50 tests**. It covers the rebuilt identity, journal, capture,
re-examination, replay, health, read-only routes and service simulations.

| Verification | Measured state |
|---|---|
| Watch subset | 50 passed, November 5, 2026 |
| Complete backend suite on this branch | Not verified; local pytest/dependencies unavailable |
| Exact production dependency lock | CI check configured; outcome not observed locally |
| Historical reference floor | Not rerun; exact database unavailable |
| Native Mac install and reboot | Not verified; requires the owner's Mac |
| Real-source unattended acceptance | Not verified |

These are separate gates. The watch subset is not the whole backend suite, a
native launchd test, a live-source run or a reference-floor measurement. Earlier
full-suite counts describe earlier builds and are not advertised as current.
See the [measured rebuild closeout](docs/MILESTONE_1A_REBUILD_2026-11-05.md).

```bash
SUNLIGHT_OFFLINE=1 python -m unittest discover -s tests -p 'test_watch_*.py' -v
PYTHONPATH=code python -m pytest tests/ -q
```

## Academic Foundation

TCA operationalizes the i* Strategic Dependency Framework published by Dr. Christelle Scharff (Pace University, Seidenberg School of Computer Science) and colleagues in Heng, Tsilionis, Scharff & Wautelet (2022). The i* framework provides the formal dependency-modeling semantics. SUNLIGHT translates those semantics into a deterministic rule engine that detects structural contradictions no indicator-based method can surface.

## Design Principles

- Deterministic logic over probabilistic guessing — every detection traces from result to inputs
- Every detection explainable in language an investigator understands
- A flag is a risk indicator, not an allegation
- An allocation is a recommendation, not a directive
- Preserve the constructed reference regression separately from claims of real-case detection; publish a new measured result only after replaying the exact inputs
- Jurisdiction calibration is a data task, not a code task
- The living standard is primary calibration for the majority of the operational footprint
- Recovered funds are redirected using the institution's own published commitments, not external opinion
- Absence of evidence is not evidence of fraud — UNVERIFIED is never CONTRADICTED
- Every claim is corroborated against evidence that does not route through the party being verified
- The system publishes what it will look for before it looks, and discloses what it cannot verify
- Ground truth before code — no engineering begins from assumed state

---

Built by Rimwaya Ouedraogo and Hugo Villalba.
