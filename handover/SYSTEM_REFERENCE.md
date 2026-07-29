SUNLIGHT — System Reference
Institutional Procurement Integrity Infrastructure
Architecture · Methodology · Institutional Position · Current State
April 2026 · v4 Core · Living Standard Architecture

1 — IDENTITY

SUNLIGHT is institutional procurement integrity infrastructure. It integrates into multilateral procurement and oversight pipelines, applies a structural and statistical analysis engine to every contract that flows through those pipelines, and produces explainable, tiered risk assessments that institutional investigators can carry directly into casework. Every output is framed as a risk indicator, not an allegation. The system identifies structural anomalies; humans investigate intent.

SUNLIGHT is pipeline verification infrastructure — the layer that sits underneath an institution's existing oversight workflow and verifies the structural integrity of every contract that passes through it. It is not a fraud detection product. It is the glove that lets the institutional hand grip.

SUNLIGHT's primary target is the United Nations Development Programme. Not as one customer among many, but as the institutional home the system is designed to live inside. UNDP programs development work through approximately 170 country offices and monitors global procurement through the Compass Global Anti-Corruption Data Dashboard, which aggregates approximately $60 trillion in purchasing-power-parity procurement spending across 51 countries and 70 million contracts over eight years. SUNLIGHT does not deploy to UNDP's country offices one by one. SUNLIGHT integrates once at the UNDP level — with OAI, with country office pre-award verification workflows, with Compass drill-down analysis, with reconstruction integrity scanning — and from that single integration point SUNLIGHT covers UNDP's entire operational footprint automatically. Every contract that flows through any UNDP pipeline gets structural analysis calibrated to its execution country's legal context, without a separate deployment per country.

Secondary institutional targets — to be approached through the UNDP credibility chain once the first conversation produces a warm handoff — include the World Bank Integrity Vice Presidency, the International Monetary Fund Fiscal Affairs Department, the African Development Bank Integrity and Anti-Corruption Department, regional development banks, national audit offices, and inspector general functions inside other multilateral agencies. None of these secondary targets are activated. UNDP is the lead channel and the right one to walk first.

2 — ORIGIN AND TEAM

SUNLIGHT was founded by Rimwaya Ouedraogo, a Pace University Seidenberg School student and the system's primary developer. Rim is from Burkina Faso, with formative years in Ghana, France, and the United States. His connection to the procurement integrity problem is structural and personal — the Ouedraogo lineage carries a governance responsibility tied to the founding of the Mossi Kingdom, and Rim's lived experience across West African development contexts shaped both the conviction and the design instincts that produced SUNLIGHT.

Hugo Villalba is strategic collaborator and co-owner, holding a 50/50 equity position. Hugo's role is strategic direction and the deeper structural reasoning that produced the TCA engine — the topological component that distinguishes SUNLIGHT methodologically from indicator-based approaches in the same space. The Rim-Hugo partnership is the load-bearing structure of the company: founder-builder paired with structural architect, with role differentiation that is real rather than nominal and an equity structure that reflects it.

The two founders work primarily through GitHub (rimodg/sunlight, private), with Hugo collaborating as hugoboss23-5. The codebase is held in Rim's repository and pushed from Rim's local environment.

3 — ARCHITECTURE

SUNLIGHT v4 Core is built around three detection engines operating on a unified ContractDossier data structure, threaded through an eight-stage pipeline from ingestion to verified output. As of April 2026, the system has been extended with a full jurisdiction profile architecture and a living multi-jurisdiction standard infrastructure — changes that make SUNLIGHT source-agnostic and deployment-agnostic at the architectural level.

3.1 — Detection Engines

The Contradiction Risk Indicator (CRI) engine is the statistical layer. It implements Fazekas-style integrity risk indicators with Bayesian evidence weighting, bootstrap confidence intervals for non-parametric price deviation analysis, and false discovery rate correction for multiple-testing control. Detection thresholds are anchored to the statistical signatures of prosecuted procurement fraud cases rather than to arbitrary cutoffs.

The Topological Contradiction Analysis (TCA) engine is SUNLIGHT's deterministic structural component, designed and built by Hugo. TCA constructs a structural graph of each contract's stakeholder dependencies, capability requirements, and procedural commitments — including explicit MISSING nodes for absent capabilities — and identifies structural contradictions through graph topology rather than statistical pattern-matching. TCA's academic grounding is Dr. Christelle Scharff's published i* Strategic Dependency Framework, which provides the foundational dependency-modeling formalism that TCA operationalizes for procurement integrity analysis. TCA is the methodological differentiator that allows SUNLIGHT to surface structural gaps that indicator-based methods cannot detect.

The TCA engine is implemented in code/tca_rules.py as a deterministic rule-based system: 16 rules organized into five enrichment layers covering procedural anomalies, entity anomalies, financial anomalies, temporal anomalies, and network/geographic anomalies. As of the jurisdiction profile refactor (commit ff267e0), the 6 jurisdiction-specific rules read their calibration from a JurisdictionProfile object passed to the rule engine at construction time, via the build_rules(profile: JurisdictionProfile) -> List[Rule] closure pattern. The 10 universal rules are unchanged. Each rule carries explicit legal grounding parameterized by profile — citations to UNCAC, UNDP guidance, and jurisdiction-specific legal frameworks — which extends SUNLIGHT's explainability contract directly into the case packet generator at the rule-fire level.

The Evidence Verification Gate (EVG) engine is the final integrity check before a flag becomes a tiered output. EVG enforces the multi-dimensional hard-evidence requirement that prevents weak-signal flags from being elevated to high-confidence tiers, and it carries the explainability contract that makes every detection traceable from output back to the specific evidence dimensions and field values that triggered it.

The three engines feed a unified contract dossier through the eight-stage pipeline: ingestion, normalization, entity resolution, structural construction, statistical analysis, topological analysis, evidence gating, and verified output generation. Each stage has a defined contract with the next, and each stage is independently testable.

3.2 — The Jurisdiction Profile Architecture

SUNLIGHT does not hardcode jurisdiction-specific constants anywhere in the rule engine. Every jurisdiction-specific value — fiscal calendar, competitive procurement threshold, price variation tolerance, legal citations, oversight body identification, currency, base rate — lives in a JurisdictionProfile object that is loaded at the moment a contract enters the pipeline. Contracts from different jurisdictions use different profiles, and the same rule engine produces jurisdiction-appropriate findings under each profile without any code changes.

The profile architecture separates two categories of parameters, marked explicitly in the JurisdictionProfile dataclass:

Local parameters are jurisdiction-specific facts about the deployment country's legal and fiscal context. These include the fiscal year calendar (when the fiscal year ends, which months constitute fiscal Q4, which months are genuinely free of fiscal pressure), the competitive procurement threshold in local currency (above which competitive tendering is legally required), the competitive pricing tolerance (the acceptable variance band around a fair market price), the mega contract threshold (the value at which a contract qualifies for additional scrutiny), the legal framework citations (procurement law, competition law, case authority), the currency code, the base rate corruption prevalence estimate, and the evidentiary standard. These vary by jurisdiction because they describe the country's actual law. The UK fiscal year ends March 31. The US federal fiscal year ends September 30. The UK competitive threshold under the Public Contracts Regulations 2015 is £214,000. The US federal threshold under FAR Part 13 is currently parameterized at $100,000 (preserved from the empirical DOJ calibration baseline). These values differ because the underlying legal frameworks differ, and SUNLIGHT's rule engine produces correct behavior in each context by reading the right values from the right profile.

Global parameters encode the statistical and evidentiary bar that applies consistently across all deployments. These include the RED and YELLOW posterior thresholds, the minimum confidence interval for YELLOW tier eligibility, the minimum number of typologies required for RED tier, the false discovery rate alpha, the bootstrap confidence interval level and resample count, and the maximum allowed flags per 1,000 contracts. These parameters do not vary by jurisdiction because they represent statistical methodology choices, not jurisdiction-specific legal facts. As of the GlobalParameters extraction (commit 2d3b4fe), profiles reference a shared GlobalParameters object by version string rather than containing their own copies of these values. This separation is the architectural precondition for the living standard: when global parameters update, every profile referencing the updated version inherits the change automatically.

Two profiles ship in the current codebase:

us_federal (committed in d453edd), referencing global parameters version us_federal_v0. This profile encodes US federal fiscal calendar (Oct 1 – Sep 30), $100,000 competitive threshold, USD currency, FAR Part 6 and DOJ case authority citations, and the empirical DOJ calibration for all statistical parameters. It has been validated against 42,835 US federal procurement contracts from USAspending.gov with 100% recall on the 9 DOJ-prosecuted reference cases.

uk_central_government (committed in 91ff35d), referencing global parameters version us_federal_v0 until the living standard derivation is complete. This profile encodes UK fiscal calendar (Apr 1 – Mar 31), £214,000 competitive threshold under the Public Contracts Regulations 2015, GBP currency, UK Procurement Act 2023 and Competition Act 1998 citations, and a 2.5% base rate derived from Transparency International CPI 2024 ranking. Behavioral verification confirmed the jurisdiction-specific deltas on real and synthetic contracts: TIME-001 correctly fires on March 25 under the UK profile (six days before March 31 fiscal year-end) and correctly does not fire under the US federal profile (March is a safe month in the US federal calendar). PROC-001 correctly uses the £214,000 threshold under UK and $100,000 under US federal. Same rule code, different profile, jurisdiction-correct output.

Creating a new country profile is a data task, not a code task. This is the architectural claim the jurisdiction profile system makes, and it is empirically validated.

3.3 — The Living Multi-Jurisdiction Standard (MJPIS)

The Multi-Jurisdiction Procurement Integrity Standard (MJPIS) is the living global calibration layer that SUNLIGHT uses for every jurisdiction without a mature local prosecution corpus. It is not a paper or a static threshold — it is a continuously-updated reference that derives its values from a versioned corpus of prosecuted procurement fraud cases spanning mature legal systems (US DOJ, UK SFO, French PNF, World Bank INT, and expansion jurisdictions as the corpus grows). When new prosecuted cases enter the corpus, the derivation function re-runs and every SUNLIGHT integration referencing the MJPIS version string inherits the updated values on next module reload. The system breathes with the data.

The MJPIS infrastructure ships in four pieces:

The corpus lives at research/corpus/prosecuted_cases_global_v0.1.json and is documented by research/corpus/SCHEMA.md. The v0.1 seed corpus contains the 9 US DOJ-prosecuted reference cases (Oracle 2011, Boeing 2006, DynCorp 2005 as the empirical markup floor at 75%, and six additional federal procurement prosecutions) restructured into a multi-jurisdiction schema that can accept cases from any jurisdiction via its dimensional taxonomy (markup-based, bribery-channel, administrative-sanctionable). The schema tracks case identifier, jurisdiction, year, legal basis, contract value in local currency and USD, markup percentage where documented, bribery-channel amount where documented, settlement or penalty, evidentiary standard, source URL, and dimensional tags.

The derivation function lives at code/mjpis_derivation.py and produces a GlobalParameters instance from the corpus via dimensional analysis. The v0.1 methodology is conservative: when the corpus contains only one jurisdiction (US DOJ in the seed state), the derivation inherits that jurisdiction's empirical calibration exactly. When the corpus expands to multiple jurisdictions in sub-task 2.2.6, the derivation will implement the full intersection methodology — markup floor from US DOJ anchor, bribery-channel pattern from UK SFO + French PNF anchors, administrative-sanctionable threshold from World Bank INT anchor — producing values that represent the intersection (strictest of each pair) across mature legal systems rather than any single jurisdiction's bar.

The registry integration lives in code/global_parameters.py, which now computes MJPIS_DRAFT_V0 at import time by calling mjpis_derivation.get_derived_mjpis(). When the corpus file is present, the derivation runs and produces live values. When the corpus file is missing (minimal production deployments without research/corpus/), the registry falls back cleanly to US_FEDERAL_V0 values with a warning. This ensures the module loads in every environment while enabling the living-standard behavior wherever the corpus is available.

The wiring into jurisdiction profiles happens via the global_params_version field on JurisdictionProfile. A profile with global_params_version="us_federal_v0" uses the empirical US DOJ calibration. A profile with global_params_version="mjpis_v1" (or whatever the stable version tag becomes after 2.2.6) uses the living MJPIS standard. The switch is a data change, not a code change.

What this architecture enables. SUNLIGHT deploys into two categories of jurisdictions within UNDP's operational footprint. The first category is countries with mature prosecution infrastructure — their own credible prosecuted-case corpus, their own statistical baseline derived from their own legal system, their own validated thresholds. For those countries, SUNLIGHT loads a locally-calibrated profile where the global parameters section references a jurisdiction-specific GlobalParameters instance derived from local prosecution data. This is the configuration US federal currently uses. The mature-calibration set is small — plausibly 15 to 25 countries globally — and includes the jurisdictions whose prosecution systems are deep enough and public enough to seed a defensible corpus.

The second category is every other UNDP-operational country. Countries where prosecution infrastructure is too thin, too politicized, or too new to generate a defensible local baseline. For those countries, SUNLIGHT loads a profile whose global parameters section references MJPIS. The profile's local parameters (fiscal calendar, competitive threshold, legal citations) are still country-specific and still require accurate authoring, but the statistical bars above which a finding counts as structurally significant are inherited from the living multi-jurisdiction standard. This is not the fallback — it is the primary calibration for the vast majority of UNDP's operational footprint. Mature local calibration is the exception reserved for a small set of countries. The living global standard is the default that serves approximately 100 to 130 UNDP-operational countries.

A country using MJPIS gets a threshold that would hold up in Washington, London, Paris, Berlin, and at the World Bank Sanctions Board simultaneously. That is harder to clear than any single jurisdiction's bar. The fallback is stricter than any local calibration could produce, which means deploying SUNLIGHT into a country without mature prosecution infrastructure is over-defensible rather than under-defensible — exactly the property you want in the contexts where institutional credibility matters most and where local calibration data does not exist to anchor defensibility on its own terms.

3.4 — The Eight-Stage Pipeline

The unified contract dossier flows through eight pipeline stages: ingestion, normalization, entity resolution, structural graph construction, statistical analysis, topological analysis, evidence gating, and verified output generation. Each stage has a defined contract with the next. The TCA structural analysis is performed by the TCAStructureEngineAdapter (committed in fa0c540), which wraps the rule engine output into a StructuralResult with populated rule IDs, legal citations, and confidence values. The adapter is the integration point through which the 16 TCA rules flow into the institutional pipeline's tier assignment logic.

3.5 — The REST API Layer

SUNLIGHT exposes its analysis capabilities as an HTTP service through a FastAPI application at `code/api.py`, committed in `3ade70e`. The API is the architectural precondition for deploying SUNLIGHT inside institutional pipelines as a service rather than as embedded Python code that consuming systems cannot call directly.

Five endpoints expose the full analysis surface with auto-generated OpenAPI documentation at `/docs` and `/openapi.json`:

- **`POST /analyze`** — Single contract structural analysis. Takes a contract in canonical OCDS shape plus a jurisdiction profile name. Returns structural findings including confidence, verdict, contradictions with rule IDs and legal citations, and processing time. The pipeline is constructed per-request with the specified profile wired into the TCA grapher via `TCAGraphRuleEngineAdapter(profile=profile)`, so jurisdiction calibration flows from the request through the engine into the output findings. The v4 `TCAStructureEngineAdapter` runs the structural analysis. EVG gate wiring is deferred to a future sub-task; `gate_verdict` returns `None` until EVG integration.

- **`POST /batch`** — Batch analysis of up to 1000 contracts per request under a single jurisdiction profile. Returns individual results plus aggregate statistics (verdict distribution, total errors).

- **`GET /health`** — Liveness and readiness probe. Never fails: returns `degraded` status on internal errors rather than raising.

- **`GET /version`** — Deployment metadata including SUNLIGHT version, MJPIS standard version from the registry, registered jurisdiction profile names, and API version.

- **`GET /profiles`** — Full listing of registered jurisdiction profiles with metadata (country code, currency, fiscal year end, description).

The API runs real TCA engine execution on every request. Integration testing confirms the profile propagation is live: the same contract analyzed under `us_federal` and `uk_central_government` profiles produces different findings, with processing times consistent with real graph construction and rule evaluation rather than stub behavior.

Authentication, authorization, rate limiting, and audit logging are deliberately out of scope for the initial API layer and are deferred to the security hardening sub-task that follows the integration-readiness arc. The module docstring explicitly documents that the API is designed for localhost or private-network deployment only and that public network exposure requires adding an authentication layer at the reverse proxy or gateway tier before any production use. This is the architecturally correct separation: the analysis service is internally stateless and deterministic, and the security perimeter is enforced at the deployment boundary rather than baked into the analysis code.

4 — DATA SUBSTRATE

The data substrate is source-agnostic by architectural design. The engine's analytical layer consumes ContractDossier objects; the ingestion layer converts whatever structured procurement format a source publishes into the canonical dossier shape.

The current ingestion paths include:

US federal procurement data from USAspending.gov. The production database contains 42,835 contracts spanning Department of Defense, Department of Homeland Security, Department of Health and Human Services, Department of Veterans Affairs, and other federal agencies. This is the validation baseline against which every engine change is regression-tested.

Canonical OCDS release packages from UK Contracts Finder (via OCDSFetcher("GB") in code/ocds_fetcher.py) and UK Find a Tender Service (via direct API at https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages). Both endpoints return canonical OCDS data that ingests natively into the v4 pipeline without schema conversion wrappers.

During validation work in April 2026, additional OCDS sources were investigated and found to be unsuitable: Ukraine Prozorro's live API returns non-canonical stubs and its bulk subdomain has been abandoned to a domain squatter; Nigeria's Bureau of Public Procurement and NOCOPO federal portals have expired SSL certificates, with state-level portals auth-walled; Colombia SECOP II stopped publishing canonical OCDS in April 2022 and shifted to a flattened Socrata format; five additional tier-2 OCP Data Registry publishers (Paraguay, Kenya, Dominican Republic, Albania, Uruguay) were unreachable or returned 404s during testing. This finding is documented as institutional intelligence rather than as a SUNLIGHT limitation — the OCDS publishing ecosystem has meaningfully degraded between 2022 and 2026, and any integrity tool serious about global deployment must be architecturally prepared to work with whatever structured procurement format a given integration point actually maintains today, rather than requiring the specific format the publisher committed to in 2018.

Crucially, SUNLIGHT's intended integration with UNDP does not depend on country-level OCDS infrastructure. When SUNLIGHT lives inside UNDP's pipelines, its contract data comes from UNDP's own procurement and integrity systems — OAI case files, country office pre-award workflows, Compass aggregate feeds, reconstruction integrity data. These are UNDP-operated pipelines, and their availability does not degrade when a partner country's public OCDS publishing infrastructure degrades. SUNLIGHT's coverage of 170 UNDP-operational countries is inherited from UNDP's own operational reach, not from the quality of any individual country's public data layer. The OCDS investigation work is institutional context, not a blocker.

5 — VALIDATION STATUS

SUNLIGHT v4 Core has been validated on 42,835 real US federal procurement contracts from USAspending.gov, with the engine stable in CI for multiple weeks and all regression gates preserved through every refactor in the jurisdiction profile architecture rollout.

5.1 — DOJ Reference Performance

The 9 DOJ-prosecuted reference cases remain the institutional credibility floor. Every engine modification, every threshold update, every CI run preserves 100% recall on those cases without exception. This floor is encoded in the test suite and gated by the CI accuracy check.

Current engine performance, against the DOJ-prosecuted reference corpus and the 200-contract clean comparison set:

Recall on DOJ-prosecuted reference cases: 100% (9 TP, 0 FN) across every commit in the jurisdiction profile architecture rollout

Precision (RED + YELLOW combined): 95% confidence interval [17.4%, 57.7%], with central estimate around 31-37% and observed run-to-run variance in the 25-38% range attributable to ORDER BY RANDOM() non-determinism in the get_clean_contracts() sampling query (a known non-blocking housekeeping issue)

Confusion matrix: 9 TP / 0 FN and approximately 15-25 FP / 175-185 TN depending on sampling draw

Test suite: 680 tests collected from repo root with 2 pre-existing collection errors (load_test.py and test_tca_engine.py) that are unrelated to the jurisdiction profile work

The precision variance is known, bounded by the baseline CI, and does not affect the DOJ recall floor. Every commit in the jurisdiction profile refactor series preserves recall at 100% without exception.

5.2 — Architecture Validation Across Two Legal Frameworks

The jurisdiction profile architecture has been behaviorally validated on two legal frameworks. The US federal profile produces the full DOJ validation results above. The UK central government profile produces jurisdiction-appropriate findings on synthetic and real UK data, with behavioral deltas from US federal proven explicitly:

TIME-001 fires on March 25 under the UK profile (six days before UK fiscal year-end of March 31) and correctly does not fire under US federal (March is a safe month in the US federal calendar, six months from September 30 year-end).

PROC-001 uses the £214,000 competitive threshold under UK and $100,000 under US federal, with both correctly applied to the respective currency denomination.

Legal citations in rule evidence strings render from the profile's legal_citations dictionary, producing "UK Procurement Act 2023" under the UK profile and "FAR Part 6" under US federal.

These verified deltas are the empirical proof that the same 16 TCA rules produce jurisdiction-appropriate structural detection under different profile calibrations without any code changes. The architecture works as designed for a second major legal framework.

5.3 — The Living Standard Infrastructure (MJPIS)

The MJPIS living standard infrastructure is operational as of commit b05f73f. The seed corpus contains 9 US DOJ cases in the multi-jurisdiction schema. The derivation function reads the corpus at module import time and produces a GlobalParameters instance that is registered as MJPIS_DRAFT_V0 in the global parameters registry. In the v0.1 state with only US DOJ cases in the corpus, the derivation produces values identical to the empirical DOJ calibration. When the research phase expands the corpus with UK SFO, French PNF, and World Bank INT cases, the same derivation function re-runs and produces multi-jurisdiction intersection values automatically. The engineering work required between corpus-expansion research sessions is zero — the research phase plugs directly into the infrastructure that shipped in sub-tasks 2.2.5a and 2.2.5b.

5.4 — REST API Layer End-to-End Validation

The REST API layer shipped in `3ade70e` has been validated end-to-end through integration testing and manual smoke testing. Real TCA engine execution is confirmed by processing time measurements (6.22ms on real UK Find a Tender Service contracts, versus 0.17ms for a no-engines stub baseline) and by the observed differential in findings across jurisdiction profiles (the same contract produces different confidence, verdict, and contradiction results under `us_federal` versus `uk_central_government`, proving that the profile parameter propagates from the HTTP request through the pipeline construction into the TCA engine calibration). The DOJ regression through `evaluation.py` continues to produce 100% recall with precision inside the baseline 95% CI, confirming that the API layer is pure additive scaffolding that does not disturb the core analysis paths.

6 — INSTITUTIONAL LANDSCAPE

SUNLIGHT enters a strategic landscape that has developed substantially in the last twenty-four months and is now actively funded, publicly committed, and in motion.

The United Nations Development Programme launched the Global Initiative on Measuring Corruption in December 2023, funded by Saudi Arabia's Oversight and Anti-Corruption Authority (Nazaha), with the explicit mandate to develop indicators for procurement integrity risk. In partnership with the Government Transparency Institute (GTI), UNDP standardized a procurement integrity methodology in 2024 and in December 2025 launched the Global Anti-Corruption Data Dashboard (the Anti-Corruption Compass): 51 countries, more than 70 million contracts, eight years of data, approximately $60 trillion in spending in purchasing power parity terms. This is the most comprehensive global procurement integrity database currently in existence.

In parallel, UNDP's Anti-Corruption for Peaceful and Inclusive Societies (ACPIS) program runs the Anti-Corruption Innovation Initiative, providing country-level support to nine countries deploying digital integrity solutions, with procurement specifically named as the deployment vertical for Nigeria. Donor partners across this work include Sida, Norad, UK FCDO, BMZ/GIZ, and the US State Department. Implementation partners include Transparency International, the U4 Anti-Corruption Resource Centre, the Basel Institute on Governance, and UNODC.

UNDP is also the multilateral implementer for Ukraine's reconstruction integrity apparatus, working directly with Ukraine's Ministry for Communities, Territories and Infrastructure Development on transparency and accountability mechanisms — plausibly the largest single-country procurement integrity engagement in modern history. Ukraine's new Anti-Corruption Strategy for 2026–2030 was presented at the Integrity2030 Forum in Kyiv in December 2025 and explicitly names public procurement as a high-risk sector requiring strengthened mechanisms.

This landscape changes SUNLIGHT's strategic position substantially. SUNLIGHT does not need to convince UNDP that procurement integrity is a category — that argument has been made and won. SUNLIGHT enters as the next-generation structural methodology layer that sits underneath the Compass indicator dashboard and provides the analytical depth an investigator needs at the moment of casework. The differentiation against the GTI methodology is structural and specific:

Topological structural analysis via TCA, including explicit MISSING-node detection for absent capabilities — a class of finding that indicator-based methods cannot produce

Multi-dimensional hard-evidence gating via the EVG engine, which produces case-defensible RED-tier outputs rather than indicator scores

Per-contract jurisdiction calibration that produces legally-grounded findings in the specific legal framework of the contract's execution country, without per-country deployment work

Living multi-jurisdiction standard (MJPIS) that provides prosecution-grade evidentiary calibration for the majority of UNDP-operational countries without mature local prosecution corpora, using the intersection of US DOJ / UK SFO / French PNF / World Bank INT as the reference floor

Explainable detection reports designed for case packets — every flag traceable from output back to evidence dimensions, field values, peer comparisons, rule-fire citations, and recommended investigation steps

GTI's published methodology and SUNLIGHT's approach are not in conflict. GTI's CRI provides the wide-angle indicator dashboard that triggers investigator attention. SUNLIGHT provides the deep structural layer underneath, the layer an investigator drops into when an indicator fires and a case has to be built. This is a complementary relationship, not a displacement, and it is a much easier institutional conversation than a cold pitch into an empty space.

7 — INSTITUTIONAL CREDIBILITY CHAIN

SUNLIGHT's path into the multilateral institutional system runs through a credibility chain that is partially built and is the company's most important non-technical asset.

Dr. Christelle Scharff is Associate Dean of Pace University's Seidenberg School of Computer Science, a two-time Fulbright scholar, and the author of the i* Strategic Dependency Framework that forms the academic foundation of SUNLIGHT's TCA engine. Scharff maintains active institutional networks in West Africa and across the multilateral system. She is the inbound door — Rim's direct academic relationship with her is the entry point.

Dr. Anga Timilsina is UNDP's Global Anti-Corruption Advisor and the named human owner of the ACPIS program, the Global Initiative on Measuring Corruption, and the broader UNDP anti-corruption strategic vertical. Timilsina is the single most strategically positioned individual for what SUNLIGHT is building, at a moment in his program's trajectory when country office engagements are expanding, donor money is fresh, and the Compass v1 is positioned to benefit from a v2 deeper structural layer. The Scharff-to-Timilsina introduction is the most important warm channel in the company's address book.

The institutional document for Scharff has been completed and refined into a deliverables-only framing without timelines. It requires a revision before the next Scharff contact to incorporate the architectural work shipped since January 2026 — the jurisdiction profile system, the living standard infrastructure, the UNDP-pipeline integration framing, the OCDS ecosystem findings as institutional intelligence, and the Timilsina-specific positioning that will emerge from dedicated Timilsina profile research.

Additional institutional pathways include direct outreach to the World Bank Integrity Vice Presidency, the IMF Fiscal Affairs Department, the African Development Bank IACD, and national audit offices. None of these pathways are activated yet — UNDP through Scharff/Timilsina is the lead channel and the right one to walk first.

8 — REVENUE MODEL

SUNLIGHT prices on a per-verification passport model — the Visa/Mastercard model adapted to procurement integrity. Every contract that passes through the verification pipeline carries a unit cost. Institutional clients license access to the verification infrastructure rather than purchasing an annual product. This pricing model aligns the system's incentives with the institution's volume needs, scales naturally with deployment footprint, and produces an annual revenue profile that is both predictable and growth-aligned.

The model is deliberately not a recovery-share model. Recovery-share pricing creates incentive distortions that undermine institutional credibility — it makes the verification provider a participant in the prosecution, which institutions correctly resist. The passport model preserves institutional independence and matches how multilateral procurement infrastructure is actually procured.

Initial pricing will be calibrated to the institutional procurement infrastructure category, where annual licenses for serious institutional integrity tools price in the high six to low eight figures depending on volume and scope. A single multilateral institution at scale — particularly one with UNDP's operational reach — represents seven-figure annual recurring revenue from a single institutional logo because the passport model scales with the number of contracts UNDP routes through the verification pipeline, not with the number of countries UNDP operates in.

9 — DESIGN PRINCIPLES

These principles are non-negotiable and they govern every engineering and product decision.

Deterministic logic over probabilistic guessing. Every detection follows explicit rules. No black boxes. Every output is traceable from result back to inputs through a path a human can read.

Every detection must be explainable. If a flag cannot be explained in language a procurement officer or investigator understands, it is not a valid detection.

A flag is a risk indicator, not an allegation. Every output carries this language. SUNLIGHT identifies structural anomalies; humans determine intent.

The DOJ-prosecution recall floor is absolute. Every prosecuted reference case must remain detected at RED or YELLOW through every engine change, every threshold update, every CI run, with zero tolerance. This is the institutional credibility floor and it is encoded in the test suite.

Pipeline verification infrastructure, not fraud detection. The institutional positioning is structural. SUNLIGHT verifies the integrity of the procurement pipeline. It does not replace investigators — it equips them.

Jurisdiction calibration is a data task, not a code task. Every jurisdiction-specific constant lives in a JurisdictionProfile object. Adding a new country means authoring a profile, not modifying rules. This is architecturally enforced via the build_rules(profile) closure pattern.

The living standard is primary calibration for the majority of UNDP's operational footprint. Mature local calibration is the exception reserved for countries with deep, public, recent prosecution corpora. MJPIS is the default for every other country, which is the vast majority of UNDP-operational countries.

Scope discipline. SUNLIGHT is structural and statistical procurement integrity infrastructure. It is not an everything-platform. Scope creep is the enemy of credibility.

Academic-grade validation. Every statistical claim is reproducible. Every metric carries dataset labeling. Every methodological choice can be defended in a published artifact.

Institutional UI standard. The interface must feel like the most serious software a World Bank investigator has ever used. The benchmarks are Palantir Foundry, Bloomberg Terminal, and Apple. Generic dashboard aesthetics are explicitly rejected.

Ground truth before code. No engineering work begins from assumed state. Every workstream is anchored in verified ground truth from the codebase, the git history, and the actual evaluation reports. Stale documentation is a known failure mode and is corrected at the moment of detection.

10 — IMMEDIATE PRIORITIES

Five workstreams govern the next phase of work, and they are sequenced.

**First, complete the integration-readiness arc.** Sub-task 2.2.7a shipped the REST API layer (commit `3ade70e`) with real TCA engine execution, profile-aware pipeline construction, and auto-generated OpenAPI documentation. The remaining sub-tasks in the integration-readiness arc are: 2.2.7b (input format adapter architecture — pluggable ingestion layer for OCDS, future Quantum, future Compass), 2.2.7c (output serialization hardening with roundtrip tests), 2.2.7d (Dockerfile and containerized deployment artifact), 2.2.7e (integration test suite with live HTTP server), 2.2.7f (`docs/INTEGRATION.md` developer guide for UNDP integration teams). Each sub-task is bounded engineering work estimated at one to three hours of focused Claude Code work. When this arc completes, SUNLIGHT is fully integration-ready as a containerized service with documented adapters, serialization contracts, deployment artifacts, integration tests, and a developer guide. Authentication, authorization, and security hardening are a separate arc that follows integration-readiness.

Second, run the global jurisdictional research phase. This is a structured survey of the global legal landscape to identify which jurisdictions have mature prosecution infrastructure suitable for local calibration (the small set of countries whose prosecution systems are deep enough, public enough, and recent enough to seed a defensible corpus) versus which jurisdictions fall back to the MJPIS living standard (the vast majority of UNDP-operational countries). The mature-calibration candidate set to evaluate includes Germany (BGH and OLG procurement decisions), Italy (ANAC and DDA prosecutions), Canada (Competition Bureau and RCMP), Australia (AFP, CDPP, and state ICAC bodies), Japan, South Korea, Singapore (CPIB), Netherlands (FIOD), Sweden (EBM), Switzerland (OAG), and the four core jurisdictions already identified (US DOJ, UK SFO, French PNF, World Bank INT). Each candidate is assessed against three criteria: corpus depth, public accessibility, and recency. The research output is a two-list table: UNDP-operational countries with mature prosecution infrastructure (locally-calibrated profile authors, maybe 15-25 countries), and UNDP-operational countries without mature prosecution infrastructure (MJPIS-default profiles, the remaining ~150 countries of UNDP's footprint).

Third, assemble the expanded corpus and run the real MJPIS derivation. With the mature-calibration set identified in priority two, assemble actual prosecuted cases from each of those jurisdictions into research/corpus/prosecuted_cases_global_v1.0.json using the existing schema. Extend code/mjpis_derivation.py to implement the full intersection methodology (sub-task 2.2.6) that produces real multi-jurisdiction consensus threshold values rather than the v0.1 US-only passthrough. The derivation re-runs at import time and MJPIS_DRAFT_V0 is automatically updated with the new values. This closes the gap between the living-standard infrastructure (already shipped) and the living-standard values (pending real multi-jurisdiction data).

Fourth, conduct the Timilsina deep research and draft the Scharff outreach document v2. Research Dr. Timilsina's public positions, articulated pain points, institutional priorities, intellectual commitments, and stated gaps in current anti-corruption tooling. Produce three documents: a Timilsina profile, a pain point inventory with exact citations, and a mapping from his articulated concerns to specific SUNLIGHT components that address them. Use these research outputs to draft the Scharff outreach document v2 — the artifact Scharff carries into her introduction to Timilsina. The outreach document should reference the eleven commits of architectural work, the living standard infrastructure, the OCDS institutional intelligence findings, and the specific alignment between Timilsina's public priorities and SUNLIGHT's capabilities. The Timilsina meeting, when it happens, opens with sentences drawn from Timilsina's own published voice mapped to concrete SUNLIGHT responses, not generic vendor framing.

11 — STRATEGIC THESIS

SUNLIGHT exists at a structural intersection that very few institutional infrastructure companies ever reach: a real engineering substrate with the jurisdiction profile architecture operational and validated on two legal frameworks, a real academic credibility chain through Scharff's i* framework and her direct relationship with Rim, a real validation on real data with 100% DOJ recall preserved across every refactor, a real institutional door partially open through the Scharff-to-Timilsina channel, a real and named buyer at a real moment of program expansion with fresh donor money and active country engagements, a real differentiation against a real incumbent (GTI's CRI via the Compass) that is complementary rather than competitive, and a real architectural commitment to the living multi-jurisdiction standard as public-good infrastructure rather than private methodology.

The company that wins this position is not the company that pitches loudest. It is the company that ships the engineering on time, walks the institutional door patiently, holds methodological integrity absolutely, and lets the structural inevitability assemble underneath itself rather than chasing it.

SUNLIGHT is the first product the founders are building on an underlying public-money infrastructure substrate that they are constructing as the load-bearing layer of a longer institutional intelligence thesis. The substrate is the canonical entity-resolved, graph-structured view of how money flows through institutional procurement systems. SUNLIGHT consumes that substrate to detect structural and statistical integrity risk for institutional buyers in the multilateral system, with the living MJPIS standard as the calibration layer that makes SUNLIGHT deployable across every country UNDP operates in regardless of that country's local prosecution infrastructure.

SWAMI — the second product on the same substrate, technically led by Hugo — consumes a parallel federal-data version of the substrate to detect the structural fingerprints of companies the US national-security and industrial-policy apparatus is selecting to become future incumbents. SWAMI's buyer category is American Dynamism venture capital funds, defense prime corporate development teams, sovereign-wealth diligence groups, and federal-spending quantitative investors. The two products do not share an analytical engine — SUNLIGHT runs CRI plus TCA plus EVG on procurement data calibrated by jurisdiction profiles and the MJPIS living standard, while SWAMI runs its own engine appropriate to its forward-looking structural-soundness question on federal-contractor data. What the two products share is the substrate underneath, the entity resolution discipline, the graph construction primitives, and the founders. This is the actual platform thesis, and it is why the company being built is not SUNLIGHT alone but the institutional intelligence layer that SUNLIGHT is the first lens on.

The Bloomberg of public-money flows is an empty chair right now, and the SUNLIGHT/SWAMI substrate is the only architecture this conversation is aware of that has both the technical foundation and the institutional credibility chain to fill it.

The path runs through UNDP. The activation moves are the jurisdictional research survey, the real multi-jurisdiction corpus assembly, the MJPIS derivation upgrade, and the Timilsina-aligned Scharff outreach, in that order. Every other strategic question reduces to those four until they are done.

END OF REFERENCE DOCUMENT
