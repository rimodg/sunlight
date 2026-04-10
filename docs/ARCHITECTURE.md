# SUNLIGHT — Architectural Pattern

**Status:** Internal architectural reference, private repository.

**Purpose:** Document the architectural pattern SUNLIGHT implements so that the git history contains a dated, self-contained description of the composition. Establishes internal technical priority; does not constitute a public claim, trademark, or methodology paper.

**Authors:** Rimwaya Ouedraogo, Hugo Villalba.

---

## 1 — What this document is

SUNLIGHT is the first reference implementation of an architectural pattern for building institutional detection systems that preserve precision as scale grows along every axis of growth — more contracts, more jurisdictions, more prosecuted cases in the calibration corpus, more operational feedback. The pattern is composed of seven specific principles. Each principle has been implemented and tested inside SUNLIGHT's v4 core. This document describes the pattern as an architecture, independent of SUNLIGHT as a product, so that the composition can be referenced, cited, and extended in future work.

The pattern name is reserved for a future Phase D decision (see TODO.md item 24). Candidate names include *Perpetual Intelligence Architecture*, *Monotonic Institutional Systems*, and *Scale-Invariant Institutional Intelligence*. Until that decision is locked, this document refers to the pattern as "the architecture."

## 2 — The problem the pattern solves

Institutional detection systems — fraud detection, anti-money-laundering monitoring, tax compliance verification, procurement integrity analysis, claims adjudication — are typically built as single-deployment tools calibrated once against a training dataset and then operated until they drift. The drift comes from four sources: operational volume growing past the calibration envelope, deployment into new jurisdictions whose legal and statistical characteristics differ from the training context, accumulated detection output contaminating the learning signal through feedback loops, and stale ground truth losing relevance as the adversarial landscape evolves. The typical response is periodic manual recalibration, which is expensive, slow, and disconnected from the system's real operational behavior.

The architecture solves this by composing properties that individually are known but together produce a detection system whose accuracy is a monotonically non-decreasing function of every axis of growth: more contracts makes the precision estimate sharper, more jurisdictions does not degrade the statistical calibration, more prosecuted cases entering the external corpus tightens the threshold values, and more operational feedback refines the empirical baseline without contaminating the fraud-pattern signal. The system does not require manual recalibration. It learns continuously, with correctness guarantees at every scale.

## 3 — The seven principles

### Principle 1 — Separate structural invariants from scale-dependent parameters

The detection logic must be expressible as two disjoint components: one that analyzes properties local to the individual object being examined (scale-invariant by construction) and one that supplies the contextual parameters that depend on where and when the object lives (scale-dependent, externalized). The first component never changes as the system scales. The second component is updated through data, not code.

In SUNLIGHT this is TCA (Topological Contradiction Analysis) versus the JurisdictionProfile dataclass. TCA's 16 rules operate on the structural graph of a single contract — stakeholder dependencies, capability requirements, procedural commitments, explicit MISSING nodes for absent capabilities. The rules are identical across every deployment. The jurisdiction-specific constants (fiscal calendar, competitive procurement threshold, currency, legal citations, base rate) live in the profile object and are loaded at the moment a contract enters the pipeline. The build_rules(profile: JurisdictionProfile) -> List[Rule] closure pattern enforces the separation at the code level: rules literally cannot access jurisdiction constants except through the profile passed in at construction time.

### Principle 2 — Use statistical methods whose power is monotonically non-decreasing in sample size

Every statistical procedure the system relies on must have the mathematical property that its accuracy improves or holds constant as the sample size grows, never degrades. This rules out methods with fixed window sizes, methods with manually tuned hyperparameters that do not scale, and methods whose computational cost grows faster than linearly in the corpus.

In SUNLIGHT the statistical layer composes three methods with this property: Bayesian posterior updating (the posterior concentrates around the true parameter as evidence accumulates), bootstrap confidence interval estimation (the CI width shrinks as O(1/sqrt(n)) where n is the sample size), and Benjamini-Hochberg false discovery rate control (the expected proportion of false discoveries among discoveries is bounded above by α regardless of corpus size, which means precision among flagged items has a scale-invariant lower bound by mathematical proof). The bootstrap clean comparison sample is scaled as max(floor, sqrt(total_contracts)) so the CI width automatically sharpens as the deployment corpus grows. The FDR α is fixed at a methodology level, not tuned per deployment, because it encodes the statistical precision floor rather than an operational parameter.

### Principle 3 — Ground truth must come from external validation, not self-generated output

Any detection system that learns what "abnormal" looks like from its own detection output will eventually drift into circular self-reinforcement. The classic failure mode is predictive policing systems that over-patrol neighborhoods where they previously found crime, which generates more recorded crime in those neighborhoods, which reinforces the over-patrolling. The fix is to anchor the learning mechanism in an external ground truth that the system cannot contaminate.

In SUNLIGHT the external ground truth is the Multi-Jurisdiction Procurement Integrity Standard (MJPIS) corpus at research/corpus/prosecuted_cases_global_v0.1.json . Cases enter the corpus only after legal validation by mature prosecutorial systems — US DOJ convictions, UK SFO deferred prosecution agreements, French PNF CJIPs, World Bank INT sanctions. SUNLIGHT does not contribute to the corpus. The corpus contributes to SUNLIGHT's threshold calibration via the derivation function in code/mjpis_derivation.py , which re-runs when the corpus updates and propagates new values through the global parameters registry.

### Principle 4 — Separate empirical baselines (learned from operation) from pattern signatures (learned from ground truth)

The system needs to know two distinct things: what "normal" looks like in the deployment environment, and what "abnormal" looks like in validated ground truth. These two kinds of knowledge must be learned through separate channels that never cross, because mixing them produces the circular drift that Principle 3 forbids. The "normal" channel learns from operational flow because operation is the only way to observe normal at scale. The "abnormal" channel learns from external legal validation because self-learned abnormality patterns drift.

In SUNLIGHT this is enforced by the empirical calibration store ( code/calibration_store.py ) versus the MJPIS corpus ( research/corpus/ ). The calibration store holds per-profile running statistics — total contracts analyzed, verdict counts, rule fire counts, risk score statistics — accumulated monotonically from every batch analysis. It holds operational observations only. It does not hold rule definitions, fraud patterns, threshold values, or anything derived from detection output. The MJPIS corpus holds fraud patterns only and is updated exclusively from external legal validation. The two channels share no state, no update hooks, and no contamination path. This is the circular-drift firebreak enforced at the implementation level.

### Principle 5 — Calibration updates must be a data task, not a code task

The cost of keeping the system calibrated to the world's current state must scale sub-linearly with the number of contexts the system operates in. If every new deployment requires engineering work, the system cannot scale operationally even if it scales mathematically. New jurisdictions, new legal frameworks, new prosecuted cases must be addable through data authoring alone, without modifying detection logic.

In SUNLIGHT adding a new country means authoring a new JurisdictionProfile object with the country's fiscal calendar, competitive threshold, legal citations, currency, and base rate. No rule modifications. No pipeline changes. The same 16 TCA rules produce jurisdiction-appropriate findings under any profile. Similarly, adding new prosecuted cases to the MJPIS corpus means appending JSON entries to the corpus file; the derivation function re-runs at module import time and updated threshold values propagate automatically.

### Principle 6 — Explainability must be structural, not post-hoc

Explainability generated after the fact by a separate model is a second surface that can drift from the first. Explainability generated as the natural output of the detection logic itself cannot drift because it is the same logic producing both the finding and the explanation. For legal defensibility, regulatory review, institutional governance, and long-term drift detection, the only credible approach is structural explainability.

In SUNLIGHT every finding carries a rule-fire history with explicit rule IDs, severity, evidence strings, and legal citations parameterized by the active jurisdiction profile. Every flag is traceable from output back to the specific rules, field values, and statutory grounding that produced it. The explainability is not a report generated by a downstream model — it is the direct output of the TCA rule engine, with the same deterministic correctness guarantees as the detection itself.

### Principle 7 — Invariants must be absolute, not aspirational

Perpetual systems need hard gates that cannot be silently violated. Soft gates drift; hard gates do not. The invariants the system commits to must be encoded in tests that block merges, enforced by CI, and written as absolute thresholds rather than advisory targets.

In SUNLIGHT the hard invariant is 100% recall on the validated prosecution corpus. Every commit preserves this floor with zero tolerance. The CI accuracy check gates it. No refactor, no threshold update, no rule change can merge unless all prosecuted reference cases are detected at CONCERN, COMPROMISED, or CRITICAL verdict. The current corpus is 9 US DOJ cases; it will grow to 40-60 cases across four mature legal systems (US DOJ, UK SFO, French PNF, World Bank INT) through the Jurisprudence Engine work tracked in Phase B of TODO.md . As the corpus grows, the invariant stays absolute: 100% recall on the whole corpus, every commit, forever.

## 4 — Composition and the monotonic property

The seven principles are not independent — they compose. TCA (Principle 1) is scale-invariant. The statistical layer (Principle 2) improves with scale. The external corpus (Principle 3) provides a stable anchor that grows only with legal validation. The empirical baseline channel (Principle 4) sharpens with operational flow without contaminating the pattern signatures. Calibration updates (Principle 5) are cheap because they are data. Explainability (Principle 6) is structural and cannot drift from the detection logic. Invariants (Principle 7) are absolute and encoded in CI.

The composition produces a system whose accuracy is a monotonically non-decreasing function of every growth axis. More contracts does not degrade per-contract accuracy because TCA is local and the statistical calibration sharpens. More jurisdictions does not degrade statistical calibration because local parameters are isolated in profiles. More prosecuted cases in the corpus tightens the threshold values via the derivation function. More operational feedback refines the empirical baseline because the monotonic accumulator in the calibration store only grows. None of these four growth dimensions degrades any of the others. There is no internal axis along which scale imposes a cost on accuracy. That is the architectural property behind the phrase "runs forever at any scale with preserved precision."

## 5 — Applicability beyond procurement integrity

The pattern is domain-agnostic. The principles describe an architecture for detection systems generally, not an architecture for procurement integrity specifically. SUNLIGHT is the first reference implementation because procurement integrity is the problem the founders know deepest, but the same composition applies to any institutional detection problem where: the input can be analyzed as structural properties of individual objects, a statistical framework with monotonic power exists, an external ground truth anchor is accessible, empirical baselines can be separated from pattern signatures, jurisdictional or contextual calibration can be externalized into data, and the output must be explainable for legal or regulatory review.

Candidate domains include anti-money-laundering transaction monitoring, tax fraud detection at revenue authorities, export control and sanctions screening, healthcare claims fraud detection, insurance claim adjudication, environmental compliance monitoring, supply chain integrity verification, academic research integrity, legal discovery, beneficial ownership transparency, financial statement fraud detection, pharmaceutical adverse event detection, and food safety recall prediction. In each domain the specific ground truth anchor and the specific structural rules differ, but the seven-principle composition and the monotonic-accuracy property transfer directly.

## 6 — Relationship to prior work

The architecture builds on foundational work in several fields. Professor Christelle Scharff's i* Strategic Dependency Framework provides the formal dependency-modeling substrate that TCA's graph construction operationalizes. Mihály Fazekas, Luciana Cingolani, and Bence Tóth's 2018 work on objective procurement integrity indicators established the statistical methodology that SUNLIGHT's CRI engine inherits. The Benjamini-Hochberg FDR control procedure (1995) provides the scale-invariant precision guarantee. The bootstrap resampling framework (Efron, 1979) provides the monotonic-convergence confidence interval property.

The architecture's contribution is not any of these components in isolation. The contribution is the specific composition — how structural analysis, monotonic statistics, external ground truth anchoring, channel separation, data-driven calibration, structural explainability, and absolute invariants fit together into a single architecture whose correctness properties hold at every scale and every jurisdiction through mathematical composition rather than through per-deployment engineering.

## 7 — Status and next steps

As of the commit containing this document, the architecture is implemented and running in SUNLIGHT v4 core. Every principle has code backing it on main. The empirical calibration store (Principle 4) is in its observation-only phase — phase two, which consumes the accumulated empirical distributions into the detection path as empirical priors, is tracked as a future sub-task (provisional 2.2.7l). The Jurisprudence Engine (Principles 3 and 7) operates on a 9-case US DOJ seed corpus; expansion to 40-60 cases across four jurisdictions is tracked as Phase B of TODO.md . The formal architecture name, public prior-art repository, methodology paper, and trademark protections are tracked as Phase D.

This document is the dated internal reference. It is not a publication, not a trademark filing, and not a standards body submission. It is the git-committed description of the architectural pattern at the moment of writing, authored by Rimwaya Ouedraogo and Hugo Villalba, stored in the private rimodg/sunlight repository. The git commit hash and timestamp of this file establish the dated internal record of the composition.

---

**End of architectural reference.**
