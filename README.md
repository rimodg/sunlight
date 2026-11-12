# SUNLIGHT

See the [November 10 runtime and backend verification](docs/TASK1_RUNTIME_2026-11-10.md), with the [macOS service guide](docs/MACOS_WATCH_SERVICE.md). The backend suite passes with the exclusions listed below. Native service/reboot, live container and reference-database acceptance remain open.

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

SUNLIGHT analyzes supplied procurement, delivery, corroboration and recovery
records through distinct workflows. A procurement response does not run or
substantiate all those stages. Findings identify conditions requiring review;
they do not establish theft, intent, legal responsibility or harm. Institutions
retain authority over investigation, recovery and allocation decisions.

The rebuilt watch adds continuity: organizational identities joined only by cited
identifiers, admitted frozen captures, an append-only subject history and as-of
re-examination. It reports newly known evidence, changed readings and open items.
Both adapters passed one-page live validation on November 10, 2026. Population
and unattended public-source acceptance remain open. No source is enabled by default.

The analytical path uses no model. A reading is reproducible from the same
frozen inputs, parameters, code, reference data and seed. Statistical resampling
is seeded. Operational timing and health receipts are separate from the reading.
SUNLIGHT does not execute payments, hold funds or recover money itself.

## Architecture

Procurement, delivery, recovery and corroboration are distinct workflows. The
components below are implemented building blocks, not a claim that every API
request runs every component. Rule and evidence-class counts below were checked
against the loaded registries on November 10, 2026; they are implementation
counts, not measured detection accuracy.

**CRI (Contract Risk Indicators)** - Statistical engine. Computes price deviation from peer cohort, Bayesian posterior probability, z-scores, and Wilson confidence intervals. Produces a structural confidence score.

**TCA (Transparent Contradiction Analysis)** - Rule engine. Constructs a structural dependency graph of each contract's stakeholders, capabilities, and procedural commitments, then identifies topological contradictions through graph analysis. 16 rules across 5 layers (procurement 5, entity 3, financial 3, temporal 3, network 2). Each rule fires with a confidence score, legal citation, and evidence string. Grounded in the i* Strategic Dependency Framework (Heng, Tsilionis, Scharff & Wautelet, 2022).

**EVG (Evidence Verification Gate)** - Gating framework. Requires convergent evidence across independent analytical dimensions before issuing a verdict. Three procurement dimensions (CRI statistical markup, CRI bribery channel, TCA typologies). Prevents single-signal flags from reaching high-confidence tiers.

**Delivery Verification (Side 2)** - Evaluates post-award contract execution. 12 rules across 4 layers (milestone, resource, outcome, financial reconciliation). 4 EVG dimensions. Produces independent delivery verdicts that combine with procurement findings. A contract that cleared procurement but shows no construction permits, no equipment, and no staffing at month 12 has a structural contradiction between what was procured and what was delivered. The same graph methodology catches it.

**Intelligence Alert System (Side 3)** - Priority-ranked triage briefs with cross-contract pattern detection. Vendor clustering, rule concentration, temporal clustering, pillar concentration, financial escalation. Emits through configurable channels (webhook, file, log) with HMAC-signed payloads. Deterministic intelligence summaries where every word traces to a data point.

**Recovery Intelligence (Side 4)** - Closes the loop. Tracks recovered funds from flagged contracts, reads the institution's own Country Programme Document allocation targets, computes gap-weighted redirection recommendations proportional to where the institution is furthest behind its own stated goals, and verifies that redeployed funds deliver results through Side 1 and Side 2. Produces institutional impact reports tracing the full cycle from corruption caught to beneficiaries reached. The institution's own published commitments determine the allocation. SUNLIGHT reads the plan, identifies the gaps, and recommends. The institution decides.

**Evidence Corroboration (Side 5)** - The final gate. Corroborates claimed outcomes against six independent evidence classes (institutional records, third-party administrative records, geospatial imagery, independent field verification, beneficiary-side signal, and adversarial/open signal) that do not route through the implementing partner. Detects the contradiction no documentary review can reach: a claim that passed every procurement and delivery gate but that independent evidence does not support. Produces four verdicts - VERIFIED, PARTIAL, UNVERIFIED, CONTRADICTED - and architecturally refuses to conflate UNVERIFIED (insufficient queryable evidence) with CONTRADICTED (evidence actively contradicts the claim), so a country with thin digital infrastructure is never flagged for fraud on absence alone. Every artifact carries a provenance chain (source, digest, timestamp); evidence content is hashed at ingestion and discarded, never stored. The recovery loop cannot close on an uncorroborated claim.

Every engine reads its calibration from the jurisdiction profile loaded for the contract's execution country. When CRI computes price deviation, the tolerance band comes from the profile. When TCA evaluates competitive procurement thresholds, the legal threshold and citation come from the profile. When EVG assigns tier, the evidentiary standard comes from the profile. The same rules, the same statistical methodology, the same gating logic - calibrated differently for each country's legal framework. One engine, many jurisdictions. Adding a new country means authoring a profile, not changing the engine.

## Jurisdiction Profiles

| Profile | Framework | Coverage |
|---------|-----------|----------|
| us_federal | FAR/DFARS, 41 USC, DOJ prosecution standards | US federal procurement |
| uk_central_government | UK Bribery Act 2010, Public Contracts Regs 2015 | UK central government |
| wb_int | UNCAC, World Bank Procurement Framework | International development |
| france_pnf | Sapin II, Code de la commande publique | French public procurement |

Each profile defines its own legal citation set, threshold calibration, and rule activation map. Behavioral verification is confirmed across profiles: the same rule (TIME-001) fires correctly on March 25 under the UK profile (6 days before UK fiscal year-end) and correctly does not fire under US federal (March is a safe month in the US federal calendar). Same rule, different profile, jurisdiction-correct output.

## Living Standard (MJPIS)

MJPIS is an implemented versioned parameter registry and derivation mechanism.
The available profiles and their citations do not establish four independently
validated prosecution corpora, legal recognition or adoption by institutions.
Inspect `/assurance` and the source corpus for the current calibration basis and
any fallback state. A derived threshold is not evidence of field accuracy.

The master plan's proposed standard is the published invariants. The existing
registry is one implementation component, not a claim that SUNLIGHT owns an
international standard or already covers every jurisdiction.

## Evaluation

The stored historical report used a 42,835-contract comparison database to
construct a regression evaluation: nine synthesized positive price examples,
200 presumed-negative comparisons and one excluded case. These are not nine
independently observed prosecuted contracts. The figures below describe that
constructed population only; they do not measure field accuracy.

These values were matched to the stored report dated June 11, 2026 during the
November 10 README audit. That was an inspection of historical output, not a
new evaluator run witnessed here. The claimed 42,835-row source database could
not be independently counted because the database is unavailable.

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
current verification checkout lacks that database, so neither reference protocol has been
rerun for this branch. A previous result is not a new measurement.

## API

REST API via FastAPI with auto-generated OpenAPI documentation. Supplied-record analysis and the persistent organizational watch are distinct workflows. The watch journal retains admitted organizational projections and original-response digests, observations, findings and operational receipts in the operator-configured external data directory. Other API workflows also maintain operational calibration or recovery state, so the application must not be described as wholly stateless. The corroboration workflow also uses a bounded in-process cache so a result can be inspected after the fact. That cache is capped, evicts oldest-first, does not survive a restart, and says so in its own responses - it is not a database, and no audit trail should be built on it. It retains provenance (source, digest, timestamp) and never artifact content. Designed for integration into institutional pipelines behind the deploying institution's own authentication layer.

**Core Pipeline**
- `POST /analyze` - Single contract structural analysis with jurisdiction profile
- `POST /batch` - Batch analysis, up to 1,000 contracts per request
- `GET /health` - Liveness and readiness probe
- `GET /version` - Deployment metadata, MJPIS version, registered profiles
- `GET /profiles` - All registered jurisdiction profiles with metadata

**Watch ledger and reporting**
- `GET /watch-engine/status` - Recorded watch health and latest examination
- `GET /watch-engine/subjects` - Organizational subject register
- `GET /watch-engine/subjects/{subject_id}` - One subject's sourced observations and readings
- `GET /watch-engine/examinations` - Historical examination index
- `GET /watch-engine/captures/{capture_id}` - Retained organizational projection, with original-response digest
- `GET /watch-engine/packets/{examination_id}` - Frozen-input replay packet
- `GET /watch-engine/ui` - Readable journal interface
- `GET /assurance` - Capability and calibration boundaries

Procurement receipts are included in `/analyze` and `/batch` responses. CLI
reference evaluation is separate from these HTTP routes; no certification or
prosecution-validation endpoint is claimed here.

**Delivery Verification**
- `POST /delivery/analyze` - Single contract delivery verification
- `POST /delivery/batch` - Batch delivery verification
- `GET /delivery/pillar-summary` - Country office development pillar aggregation

**Intelligence Alerts**
- `GET /alerts/config` - Alert configuration (no secrets exposed)
- `POST /alerts/test` - Fire synthetic test alert through all emitters
- `POST /alerts/triage` - Generate triage brief with ranking, pattern detection, executive summary

**Recovery Intelligence**
- `POST /recovery/record` - Create recovery record when institution acts on a RED flag
- `POST /recovery/confirm` - Confirm contract cancellation or modification
- `POST /recovery/allocate` - Compute gap-weighted allocation from institution's CPD targets
- `POST /recovery/redirect` - Link recovered funds to new contract (enters Side 1 and Side 2 automatically)
- `GET /recovery/status/{recovery_id}` - Full recovery lifecycle with linked redirections and verdicts
- `GET /recovery/impact` - Institutional impact report: caught, redirected, verified, beneficiaries reached
- `GET /recovery/cycle/{source_contract_id}` - Complete traceability from RED flag to development outcome

**Evidence Corroboration**
- `POST /evidence/analyze` - Corroborate a claimed outcome across six independent evidence classes
- `POST /evidence/batch` - Batch corroboration, up to 1,000 claims
- `GET /evidence/expected/{outcome_type}` - Publish what evidence SUNLIGHT will look for, before submission
- `GET /evidence/capacity/{country_code}` - Honest disclosure of which evidence classes are queryable in a jurisdiction and the resulting confidence ceiling
- `GET /evidence/dossier/{dossier_id}` - Retrieve a corroboration dossier (ephemeral cache, not a database)
- `POST /evidence/verify-integrity` - Detect post-ingestion tampering via provenance hash

## Deployment

Containerized via Docker. The deploying institution controls data residency, authentication, backups and routing. The watch is a separate persistent service: its admitted projections and journal survive restarts in operator storage. Corroboration artifacts use a separate digest-only path; that does not mean the whole system discards all source content. Preserve operational state before taking an old deployment offline or replacing it.

```bash
docker build -t sunlight .
docker run -p 8000:8000 sunlight
```

## Test Suite

Latest measured branch result: **2,078 passed, 13 skipped, 0 failed** on
November 10, 2026 after the paging and population tests. The live
[identity proof](docs/TASK5_IDENTITY_2026-11-12.md) passed on November 12.
The earlier same-day baselines below remain attributed to their tested builds.

On **November 10, 2026**, the complete backend command measured **1,989 passed,
12 skipped, 0 failed on main** at `bd9ebef`, and **2,056 passed, 13 skipped,
0 failed on this rebuild** after the RUNTIME-002 path-comparison fix. Both ran
on macOS arm64 with CPython 3.12.14 and the same 35 locked runtime packages.
The test environment added pytest and its four dependencies. The rebuild also
reported 17 passing subtests, separately from the passed-test count.

| Verification | Measured state |
|---|---|
| Main backend suite | 1,989 passed, 12 skipped, 0 failed; November 10, 2026 |
| Rebuild backend suite after RUNTIME-002 | 2,056 passed, 13 skipped, 0 failed; November 10, 2026 |
| After organizational projection | 2,073 passed, 13 skipped, 0 failed; November 10, 2026 |
| After paging and population tests | 2,078 passed, 13 skipped, 0 failed; November 10, 2026 |
| Exact runtime dependency lock | All 35 pins installed and passed the service runtime verifier; November 10, 2026 |
| Historical reference floor | Not rerun; exact database unavailable |
| Native Mac service | Installed November 12; awaiting macOS Documents permission; reboot unverified |
| Real-source unattended acceptance | Pending first scheduled capture and full day; [native gate](docs/TASK6_NATIVE_2026-11-12.md) |

Both suites skipped nine live-container tests because Docker was unavailable
and three invariance tests because the production database was absent. The
rebuild also skipped one non-Mac-host test on this Mac. Both emitted two
dependency deprecation warnings. Service tests use launchctl simulations and
do not prove native installation or reboot persistence. See the
[dated verification and evidence hashes](docs/TASK1_RUNTIME_2026-11-10.md) and
the [README figure audit](docs/README_FIGURES_2026-11-10.md).

```bash
SUNLIGHT_OFFLINE=1 python -m unittest discover -s tests -p 'test_watch_*.py' -v
PYTHONPATH=code python -m pytest tests/ -q
```

## Academic Foundation

TCA operationalizes the i* Strategic Dependency Framework published by Dr. Christelle Scharff (Pace University, Seidenberg School of Computer Science) and colleagues in Heng, Tsilionis, Scharff & Wautelet (2022). The i* framework provides the formal dependency-modeling semantics. SUNLIGHT translates those semantics into a deterministic rule engine that detects structural contradictions no indicator-based method can surface.

## Design Principles

- Deterministic logic over probabilistic guessing - every detection traces from result to inputs
- Every detection explainable in language an investigator understands
- A flag is a risk indicator, not an allegation
- An allocation is a recommendation, not a directive
- Preserve the constructed reference regression separately from claims of real-case detection; publish a new measured result only after replaying the exact inputs
- Jurisdiction calibration is a data task, not a code task
- The living standard is primary calibration for the majority of the operational footprint
- Recovered funds are redirected using the institution's own published commitments, not external opinion
- Absence of evidence is not evidence of fraud - UNVERIFIED is never CONTRADICTED
- Every claim is corroborated against evidence that does not route through the party being verified
- The system publishes what it will look for before it looks, and discloses what it cannot verify
- Ground truth before code - no engineering begins from assumed state

---

Built by Rimwaya Ouedraogo and Hugo Villalba.
