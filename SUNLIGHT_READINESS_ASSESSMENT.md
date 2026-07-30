# SUNLIGHT — Readiness Assessment

**Date:** 2026-07-30
**Commit at assessment:** `36b30ef`
**Assessed by:** full-system intelligence sweep, all five sides
**Audience:** the founding team, and a hostile institutional due-diligence team

---

## How to read this document

This is not a status report. It is the honesty surface for the entire system,
written on the assumption that a due-diligence team will try to find the gap
between what SUNLIGHT claims and what it does. Every claim below was checked
against code, and where the check failed, the failure is recorded rather than
softened.

Three things follow from that intent:

1. **Every number here is measured, not recalled.** Where a figure came from a
   live execution, the command is given.
2. **Findings that look like defects but are correct are documented as
   correct**, with the reasoning, so no future reader re-litigates them.
3. **What the sweep could not close is named in Section 5**, not buried.

The sweep operated under a hard authority boundary: output-layer defects were
fixed directly; anything touching detection rules, thresholds, scoring
computation, or the DOJ path could only be proposed. The DOJ regression floor
was treated as immutable and re-validated live after every phase.

---

## 1. VERIFIED GROUND TRUTH

Each claim, the check performed, the result.

| # | Claim | Verification method | Result |
|---|---|---|---|
| 1 | DOJ floor: 33.3% / 100% / 9.0% / 0.7456 / 129.2 | Live execution, both validators, full 42,835-contract corpus | **CONFIRMED** |
| 2 | 100% recall — no prosecuted case missed | Live: TP 9, FN 0 | **CONFIRMED** |
| 3 | Test suite green | `pytest tests/ -q` | **CONFIRMED** — 1,889 passed, 7 skipped, 1 xfailed |
| 4 | Every module imports | Import sweep of `code/*.py` | **CONFIRMED** — 113/113 |
| 5 | 16-stage pipeline (1–8 / 9–12 / 13–16) | Counted the pipeline's executed sequence | **CONFIRMED** — Side 1 = 8, Side 2 = 4, Side 5 = 4 |
| 6 | Deterministic; no model in the analytical path | AST sweep of all 39 modules reachable from `api.py`, `doj_validation.py`, `evaluation.py` | **CONFIRMED** |
| 7 | Every finding traces to a legal citation | All three rule engines enumerated | **CONFIRMED** — 44 rules, 0 uncited |
| 8 | Every finding names its rule | Live response inspection, single and batch | **CONFIRMED** — 0 empty attribution fields |
| 9 | Composite = mean of sub-scores, verifiable by hand | Arithmetic assertion in tests | **CONFIRMED** — exact to published precision |
| 10 | Fazekas mapping is conservative | Table audited rule by rule against conditions | **CORRECTED** — see §2 |
| 11 | Jurisdiction fiscal calendars | Profile inspection | **CONFIRMED** — US Sept 30, UK Mar 31 |
| 12 | No contract can silently vanish | 11 hostile inputs through `/batch` | **CONFIRMED** — 10/10 accounted for by ocid |

### 1.1 The DOJ floor, live

Run against `/Users/rimodg/brain/SUNLIGHT/data/sunlight.db` — 176 MB, `contracts`
table, **42,835 rows**, the figure the README cites.

```
python3 code/evaluation.py     --db <corpus> --cases prosecuted_cases.json \
        --seed 42 --bootstrap 1000 --clean 200 --profile doj_federal
python3 code/doj_validation.py --db <corpus> --cases prosecuted_cases.json \
        --seed 42 --bootstrap 1000 --clean 200
```

| Metric | Floor | Live | Status |
|---|---|---|---|
| Precision | 33.3% | 33.3% | MATCH |
| Recall | 100.0% | 100.0% | MATCH |
| False positive rate | 9.0% | 9.0% | MATCH |
| PR-AUC | 0.7456 | 0.7456 | MATCH |
| Flags per 1,000 | 129.2 | 129.2 | MATCH |

Confusion matrix `TP 9 · FN 0 · FP 18 · TN 182`, **identical from both tools
independently**. CI gate PASS on all three checks. Value recall 100% — all
$941.4M of prosecuted fraud value detected.

Re-validated live after **every phase** of this sweep. Byte-identical throughout.

**Two things a due-diligence team should know about these numbers.** First, they
come from **two different tools**: `doj_validation.py` produces precision,
recall, FPR and the confusion matrix and emits **no PR-AUC at all**;
`evaluation.py` produces PR-AUC and flags-per-1k. They have been cited as one
baseline. Second, `--clean 200` is load-bearing — the default is 50, and running
the default changes the numbers for a sampling reason that reads exactly like
drift.

### 1.2 Determinism, proven mechanically

This claim is load-bearing for the whole institutional case, so it was proven
rather than asserted.

- **AST sweep of the 39 modules** transitively reachable from the API and both
  validators. **Zero** ML/LLM/model calls. The only two matches in the entire
  path are *docstrings* in `tca_rules.py` describing the LLM's research-time
  role in authoring rules — no runtime dependency.
- **Every `np.random` call is explicitly seeded.** Per-contract seeds are
  derived as `sha256(f"{run_seed}:{contract_id}")`, so each contract gets a
  stable, reproducible draw. Bootstrap resampling carries an explicit
  `np.random.seed(42)` commented "Reproducibility for court".
- **`uuid4` appears 13 times, all in identity fields** (`alert_id`,
  `dossier_id`, `report_id`). Verified not to reach computation: verdict,
  structure and composite are identical across runs while IDs differ.
- **Determinism asserted per engine**, not only on the DOJ path — Side 1 single
  and batch, structural scoring, Side 2, Side 5, Side 3. Ten repeated runs of
  the same contract yield one verdict.

### 1.3 Citation coverage

| Engine | Rules | Uncited |
|---|---|---|
| Side 1 TCA | 16 | 0 |
| Side 2 delivery | 12 | 0 |
| Side 5 evidence | 16 | 0 |
| **Total** | **44** | **0** |

---

## 2. WHAT THE SWEEP CLOSED

Every fix below is output-layer. The scoring path — `tca_rules`, `tca_analyzer`,
`tca_procurement`, `evg`, `cri`, `doj_validation`, `evaluation`,
`institutional_pipeline`, `institutional_statistical_rigor`,
`global_parameters`, `sunlight_core` — has **zero diff** across the entire sweep.

### 2.1 An unassessable axis no longer renders as a clean zero *(Verdict A)*

A sub-score of `0.0` previously meant either "assessed and genuinely clean" or
"no basis to look", and displayed identically. Those are epistemically opposite.
Indeterminate axes now report `null` with an explicit status, the requirement
they lack, and the rules that could not evaluate.

**A correction to the specification was necessary here, and it matters.** The
change was specified in terms of "insufficient comparables". Reading every
contradiction-capable rule condition establishes that **the four structural axes
never touch corpus comparables** — the word does not appear in `tca_rules.py`.
They read intra-contract fields: procurement method, bidder count, the
contract's own tender-vs-award values, its own party list, its own award date.
Comparables belong to the CRI price engine, a different axis. Implementing the
literal criterion would have marked all four axes indeterminate on every
single-contract call, including procedural, which is genuinely assessable from
one contract. Determinacy is therefore **input availability**, per axis, derived
from the same `tca_rules._extract` the rules use — so what the output calls
assessable cannot drift from what the rules read.

**The first predicate written was too permissive and was caught against a real
sample.** A contract with one supplier, no addresses and no supplier countries
has nothing for `ENT-001`/`ENT-002`/`GEO-001` to evaluate, yet carries a
non-empty `country_code` — so it reported `network_score: 0.0` with SUFFICIENT
CONTEXT, the exact false clean-zero the change exists to prevent. Determinacy is
now per-axis and mirrors what each axis's rules genuinely require: a pair to
compare, two values, a date.

### 2.2 Composite over determinate axes only *(approved change)*

An axis with no basis for assessment is excluded from the mean rather than
entered as zero. Entering it as zero let absence of information pull the score
toward clean — the same error as treating absence as guilt, in the opposite
direction. No determinate axis yields a `null` composite and `null` band, never
`0.0`; a zero there would be a fabricated clean bill.

**Guard:** a composite resting on one axis is qualified LOW CONTEXT /
single-axis in the output, and the band carries the qualification too.

### 2.3 Corpus-state stamping *(Verdict A)*

Every score now carries comparison-set size, a fingerprint (SHA-256 over sorted
comparison-set identifiers — stable under reordering, changing with membership),
jurisdiction profile name and version, and `computed_at`. An empty set yields a
`null` fingerprint rather than the digest of an empty string, so "no corpus"
cannot be confused with a corpus that happened to hash to that value.

A later score change for the same contract is now attributable to a documented
change in this stamp rather than indistinguishable from drift.

### 2.4 Reconstructability was off by 2.5e-7 *(Verdict A)*

Sub-scores were rounded at serialisation while the composite was computed from
unrounded values, so the published sub-scores did not reconstruct the published
composite. An evaluator adding the four numbers and dividing landed
`0.13333325` where the output said `0.133333`. That quietly breaks the
"verify the rollup by hand" property the formula is published for. Rounding now
happens once at computation, `composite_formula` states the rounding step, and
reconstruction is **exact**.

### 2.5 Missing core dependency *(Verdict A — deployment blocker)*

**`numpy` was absent from `requirements.txt`** while being imported by 13
modules and reachable transitively from **both DOJ validators**. The Dockerfile
installs only from that manifest, so a built image could serve `/analyze` but
could **not run the regression** — a receiving institution following the
handover instruction to re-confirm the floor on its own machine would have hit
an `ImportError` instead of a number.

The manifest was rebuilt by walking the AST of every module and resolving
transitively, then grouped by what breaks without each package: API surface,
statistical core, extended analysis, data acquisition. `reportlab` and `locust`
remain commented as genuinely optional.

### 2.6 Batch/single output parity *(Verdict A)*

`/batch` returned `structural_scoring: null` while `/analyze` populated it. The
same response model meaning different things depending on which endpoint a
consumer called is a trap. Both paths now populate it and agree on the
composite; isolation is derived from whether a comparison set exists rather than
hardcoded per path, so they cannot diverge again.

### 2.7 The Fazekas F7 mapping was wrong *(Verdict A)*

`ENT-003` was mapped to F7 (spending/market concentration) as **CONFIRMS**, on
the strength of its name, "Single supplier dominance". The rule itself:

```
condition : supplier_count == 1 and number_of_tenderers >= 3
edge      : EXPRESSES — ignored for scoring entirely
own text   : "Single supplier won against N bidders — normal competitive outcome"
```

It marks a **normal competitive result**. Claiming it confirms F7 would have
told an institution SUNLIGHT structurally verifies market concentration when no
rule in the engine measures concentration at all. No output was ever wrong — the
`EXPRESSES` edge means it cannot reach the scoring layer — but the **published
table** would have been, and the table is what an institution reads.

### 2.8 Documentation discrepancies *(Verdict A)*

- Test count 1,747 → **1,889**, per-side figures re-measured, and the two
  cross-cutting suites named rather than folded into Side 1.
- TCA layers were listed as "procurement, financial, compliance, temporal,
  vendor". **Two of five names do not exist** — the registry has `entity` and
  `network`, not `compliance` and `vendor`. Now listed with per-layer counts so
  the claim is checkable by eye.

---

## 3. CORE CHANGE PROPOSALS — REQUIRING HUMAN APPROVAL

**One item. Not implemented.**

### 3.1 The sub-score denominator caps the scale below its own alarm threshold

**This is the most consequential finding of the sweep.**

**Proof.** Executing each rule's edge function shows only **7 of 16 rules** emit
`REMOVES` and can reach a contradiction:

```
PROC-001 REMOVES ✓    PROC-005 BOUNDS    → ignored for scoring
PROC-002 REMOVES ✓    ENT-003  EXPRESSES → ignored for scoring
ENT-001  REMOVES ✓    FIN-002  BOUNDS    → ignored for scoring
ENT-002  REMOVES ✓    TIME-002 BOUNDS    → ignored for scoring
FIN-001  REMOVES ✓    PROC-004 VERIFIES  → exculpatory
TIME-001 REMOVES ✓    FIN-003  VERIFIES  → exculpatory
GEO-001  REMOVES ✓    TIME-003 VERIFIES  → exculpatory
PROC-003 SEEKS → unproven, then dropped in serialisation
```

`compute_sub_scores` normalises against **all 16**. With every
contradiction-capable rule firing simultaneously:

| Axis | Max achievable | Numerator / denominator |
|---|---|---|
| procedural | 0.4000 | 2.0 / 5 |
| financial | 0.3333 | 1.0 / 3 |
| temporal | 0.3333 | 1.0 / 3 |
| network | 0.6000 | 3.0 / 5 |
| **Composite** | **0.4167** | vs RED cutoff 0.60 |

**RED is mathematically unreachable.** The band at absolute maximum structural
failure is YELLOW. Not "hard to reach" — structurally impossible.

**Note this is a defect in the OUTPUT layer** (`structural_scoring.py`), not the
core. The rules and edge types are correct. It is listed here rather than in §2
because fixing it materially changes the scores institutions will see, and that
warrants explicit sign-off even though the authority boundary permits it.

**Proposed scoped change.** Derive each layer's denominator from the rules that
can actually produce a contradiction, by executing each rule's edge function
rather than hardcoding a list — so it self-corrects if a rule's edge type
changes. Additionally surface the `unproven` findings currently dropped in
serialisation, which also revives the `severity="medium"` weight class that is
presently dead code (nothing can produce it).

**Expected effect.** Sub-scores span the full 0–1 range; composite becomes
capable of reaching RED under the default cutoffs. Existing band assignments
shift upward. DOJ unaffected — the DOJ path never invokes this layer (§4.2).

**Risk.** Any institution that has already calibrated cutoffs against current
outputs would need to recalibrate. Nothing else consumes these values.

---

## 4. UNDERSTOOD AND CORRECT

Findings that look like defects and are not. Documented so no future reader
re-opens them.

### 4.1 Boeing scores 0.133 and lands GREEN *(Verdict C)*

Boeing was a **price** fraud — 450% markup on parts with known commercial
prices. The structural composite averages the four TCA layers and **excludes the
CRI price dimension entirely**. What catches Boeing is the CRI markup signal,
reported separately in `gate_outcome`. Its structural profile is an unremarkable
sole-source defence award whose tender and award values are identical, so even
`FIN-001` stays silent.

Presenting Boeing as the structural-scoring demo would misrepresent what the
number measures. The demonstration case for structural scoring is a genuinely
structural contract, which is in the suite: all four axes live, composite 0.317,
and three findings with **no CRI counterpart at all**.

### 4.2 Zero populated axes across the DOJ corpus *(Verdict C)*

Measured across 400 real corpus rows: **0.00 of 4 axes determinate**. Two
independent reasons, both correct:

1. **The corpus schema carries no structural fields.** It has `contract_id,
   award_amount, vendor_name, agency_name, description, start_date, location`.
   No tender value (so `FIN-001` has nothing to compare), no procurement method,
   no bidder count, no party list. It is a **price** corpus.
2. **The DOJ path never invokes the structural layer.** Zero references to
   `structural_scoring` or any `tca_*` module in `doj_validation.py`,
   `evaluation.py`, `institutional_pipeline.py`, or
   `institutional_statistical_rigor.py`. `score_contract` computes no sub-score.

**This is why the floor holds by construction rather than by coincidence** — the
changes are in a code path the DOJ evaluation never executes. That is a stronger
guarantee than matching numbers.

**The consequence is a real gap, recorded in §5:** nothing validates the
structural scoring at corpus scale.

### 4.3 The 16-stage claim *(Verdict C — and a correction to this sweep's own
Phase 0 report)*

Phase 0 flagged "16 stages, 1–8 procurement" as a discrepancy on the basis that
`PipelineStage` has 10 non-terminal members. **That was wrong.** The executed
sequence is exactly 8 processing stages (`NORMALIZED` → `LEADS_GENERATED`);
`INGESTED` is an initial state and `CERTIFIED` is never assigned. Side 1 = 8,
Side 2 = 4, Side 5 = 4, total 16. **The README claim is confirmed and stands.**

The one genuine finding: **`PipelineStage.CERTIFIED` is vestigial** —
declared and documented at `sunlight_core.py:76`, never set by any code path.
Left in place; removing an enum member is core-adjacent and it costs nothing.

### 4.4 The capacity_budget tie defect remains `xfail(strict=True)` *(deferred, not forgotten)*

Contracts tied at the threshold score are all admitted, so a budget of 2 over 9
identically-scored contracts returns 9. Breaking the tie means deciding which 2
of 9 **identical** contracts an investigator receives, and every mechanical
answer is arbitrary: batch order makes output depend on submission sequence,
admitting none discards real signal. The honest fix is to surface the tied group
and let the institution choose — a product decision, not a code change. The
xfail reason states this explicitly.

### 4.5 Schema-invalid input rejects the whole batch *(Verdict C, with a scale caveat)*

A contract missing `ocid` causes Pydantic to reject the entire request with a
pointer to the offending element. That is **loud and correct** — nothing is
silently lost. But it means one malformed record costs a 1,000-contract batch.
Recorded as a scale limitation in §7 rather than treated as a defect.

### 4.6 The 7 skipped tests *(Verdict C)*

All seven are `tests/test_docker_live.py`, gated on Docker availability.
Skipping when Docker is absent is correct. **It does mean the container path in
the handover package is not verified by this suite run** — stated here so
"1,889 green" is not read as implying container coverage.

### 4.7 The "22 pre-existing failures" do not exist

The sweep was asked to investigate 22 pre-existing evidence-scenario and
recovery failures. **There are none.** The suite has zero failures; no
`evidence_scenarios` file exists in the repository; `test_recovery_api.py` and
`test_recovery_ledger.py` pass fully. A repo-wide collection ignoring
`pytest.ini` found 1,829 vs 1,889 — the difference is script-shaped files in
`scripts/` that collect zero tests, plus one genuine collection error
(`scripts/load_test.py`, missing the optional `locust`).

---

## 5. CONFIRMED-OPEN ITEMS

What this sweep cannot close. Each named, each explained, none buried.

| # | Item | Why it is open | Who closes it |
|---|---|---|---|
| 1 | **Evidence maps are illustrative** | `ng.json` and `ua.json` both carry `status: "illustrative"`. `queryable_classes` drives corroboration capacity, which decides whether Side 5 may draw an adverse conclusion at all. An unvalidated map that overstates a country's registries would unlock findings its evidence base cannot support. | Country offices, per country |
| 2 | **No structural ground truth at corpus scale** | The 42,835-contract corpus is a price corpus with no structural fields (§4.2). The DOJ floor validates the price engine; **nothing validates the structural scoring** on real data at volume. | Requires an OCDS-shaped labelled corpus |
| 3 | **Band cutoffs are uncalibrated** | Defaults 0.3/0.6 are documented starting points, not empirically derived. Given §3.1 they are currently unreachable at the top; even after that fix they need calibration against real data. | Institution, post-§3.1 |
| 4 | **Legal foundation** | Findings cite UNCAC, FAR, UNEG, OECD-DAC and jurisdiction statutes. No counsel has reviewed whether the citations support the inferences drawn, or the "risk indicator, not allegation" framing under any specific jurisdiction's defamation exposure. | External counsel |
| 5 | **Independent security audit** | No third-party review. `docs/security_threat_model.md` is self-authored. Auth is deployment-boundary; the API ships with `SUNLIGHT_AUTH_ENABLED` defaulting false. | External security firm |
| 6 | **UNDP data agreement** | No agreement covering procurement data access, residency, or retention. Side 5's provenance model assumes the institution supplies evidence artifacts. | UNDP / institution legal |
| 7 | **Container path unverified in CI** | The 7 Docker tests skip without Docker (§4.6). The handover quickstart leads with `docker build`. | CI with Docker available |
| 8 | **MJPIS derivation not shipped** | The handover describes MJPIS architecture but excludes `research/corpus/` and the derivation implementation. A deployment needing the living standard must request it. | Founders' disclosure decision |

---

## 6. THE FAZEKAS / CRI POSITION

Fazekas & Kocsis (2020) defines the seven-flag Corruption Risk Index that UNDP
and GTI standardised on in 2024. This is the frame an institution already
trusts, so every SUNLIGHT finding declares its correspondence to it.

### 6.1 What SUNLIGHT structurally confirms

| Flag | Name | SUNLIGHT | Via |
|---|---|---|---|
| **F1** | Single bidding | **CONFIRMS** | `PROC-001`, `PROC-002` |
| **F3** | Non-open / exceptional procedure | **CONFIRMS** | `PROC-001` |
| F6 | Short/anomalous decision period | **RELATED only** | `TIME-001`, `TIME-002` |
| F2 | No call for tender published | no rule | — |
| F4 | Short advertisement period | no rule | — |
| F5 | Subjective evaluation criteria | no rule | — |
| F7 | Spending/market concentration | no rule | — |

**Two of seven confirmed. Five never confirmed.** F6 has two rules mapped but
deliberately labelled RELATED, never upgraded — F6 measures the decision
interval, SUNLIGHT measures fiscal-calendar clustering. Calling that a
confirmation would overclaim.

This is a smaller number than an earlier draft of the mapping asserted, and it
is the honest one (§2.7). **It is also a better position to walk an institution
through**, because it is defensible line by line.

### 6.2 What SUNLIGHT sees that no CRI indicator can

These findings have **no counterpart in the seven-flag index** — not because the
index is wrong, but because indicator methods measure observable procedural
attributes while structural analysis measures contradictions in the dependency
topology:

| Rule | Finding | Why no flag covers it |
|---|---|---|
| `ENT-001` | Bidders share a registered address | A relationship *between entities*. No flag inspects entity relationships; the index sees a competitive tender. |
| `ENT-002` | Duplicate entity identifiers among bidders | A contradiction in the party topology. Indicator methods count bidders and see competition. |
| `FIN-001` | Award materially exceeds tender value | No flag compares award against estimate. The seven describe how a contract was advertised and decided, not whether its value moved. |
| `GEO-001` | Supplier jurisdiction mismatch | A dependency between supplier and execution country. No flag examines it. |
| `PROC-003` | No oversight body in the record | No flag measures whether a review body exists. |
| Sides 2, 4, 5 | Delivery, reconciliation, corroboration | Beyond the paradigm — the index describes a procurement *event*; these describe what happened afterwards. |

### 6.3 The line to walk an institution through

> *"Your index and ours agree on F1 and F3, and we confirm them structurally —
> from the dependency graph rather than from a procedure-type field that can be
> mislabelled. On F2, F4, F5 and F7 we add nothing; your index is the
> instrument there. What we add is six classes of finding your index has no
> flag for, because they are not attributes of the tender — they are
> contradictions between the parties, the values, and the timeline. And Side 5
> asks a question no indicator asks at all: did the thing you paid for actually
> happen, according to evidence that never passed through the party being
> verified."*

---

## 7. LONGEVITY AND SCALE ASSESSMENT

### 7.1 Determinism under load — **holds**

Verified per engine, not only on the DOJ path. Ten repeated runs of the same
contract yield one verdict. All randomness is seeded, with per-contract seeds
derived by hash. `uuid4` is confined to identity fields. The only volatile field
in the scoring output is `computed_at`, which is **declared as such** and
excluded by `strip_volatile()` — the canonical form determinism is asserted
over.

### 7.2 No silent drop — **proven**

The failure that matters most at ingestion rate is not a wrong score; it is a
contract that enters and vanishes, because at volume that is indistinguishable
from one never sent and it invalidates every downstream count. Eleven inputs
including ten hostile ones: **10/10 accounted for by ocid**, two failing loudly
with `stage=failed` and a stated cause, no neighbour affected.

### 7.3 Comparability integrity as the corpus grows — **now attributable**

Before this sweep, the same contract scoring differently next quarter was
indistinguishable from drift. The corpus stamp makes a change attributable: a
fingerprint over the comparison set, plus profile version. "The corpus grew" and
"the engine changed" are very different explanations to owe an institution, and
they are now distinguishable.

### 7.4 The isolation-vs-compared distinction — **closed**

The single most dangerous output ambiguity at scale was a `0.0` that could mean
either "clean" or "unassessed". At one contract a human might catch it. At
100,000 contracts feeding a dashboard, it becomes a systematic false-clean
signal. Indeterminate axes now report `null` with an explicit status, and
single-axis results are qualified LOW CONTEXT.

### 7.5 Where scale pressure remains

| Concern | Assessment |
|---|---|
| **Whole-batch rejection** | One schema-invalid record rejects a 1,000-contract batch. Loud, not silent — but operationally costly at rate. Per-item validation with partial success would be better. |
| **In-process dossier cache** | `/evidence/dossier/{id}` is backed by a bounded 500-entry in-memory cache that does not survive restart, and says so in its own response. Not a database. Any durable audit trail needs real persistence. |
| **In-memory recovery ledger** | `RecoveryLedger` is explicitly documented as in-memory, sufficient for single-session operation. Production needs a database. |
| **No load evidence in this sweep** | `scripts/load_test.py` cannot run (`locust` absent). No throughput or latency figures were produced. Observed round-trip on single `/analyze` is ~1–22 ms, engine time 0.16–0.55 ms — indicative only, not a load test. |

### 7.6 Honest verdict on scale

The **credibility guarantees** — determinism, attribution, no silent drop,
isolation honesty, corpus attributability — hold at volume, and are now tested
rather than asserted. The **operational substrate** does not: two stores are
in-memory by design and there is no load evidence. Those are engineering tasks
with known shapes, not architectural doubts.

---

## 8. SCOPED VERDICT

### Technical readiness: **CERTIFIED**, within a stated scope

Evidence: DOJ floor confirmed live and byte-identical after every phase of this
sweep; 1,889 tests green with zero regressions; 113/113 modules import; 44 rules
with zero uncited; determinism proven mechanically across 39 modules; no silent
drop proven against hostile input; every finding fully attributed on every code
path.

**Scope of that certification:** the **price engine** is validated against a
real 42,835-contract corpus with 100% recall on 9 prosecuted price-fraud cases.
The **structural scoring layer** is validated for internal consistency,
decomposability and determinism — **not** against labelled structural ground
truth, which does not exist in this repository (§5.2). And per §3.1 its upper
range is currently unreachable pending an approved fix.

These are different strengths of claim and should never be presented as one.

### Adoption readiness: **PENDING**, on eight named items

Section 5 lists them. Three are outside engineering entirely — legal review,
security audit, data agreement. Two require data the project does not have —
country-office validation of evidence maps, structural ground truth. Three are
tractable in-house — band calibration after §3.1, Docker CI, MJPIS disclosure
decision.

**Neither word is inflated.** The system does what it says on the paths that are
validated, and the paths that are not validated are named.

---

## 9. HONEST BOTTOM LINE

**What SUNLIGHT is.** A deterministic procurement integrity engine that detects
price fraud with 100% recall on a real prosecuted corpus, and structural
contradictions that indicator-based methods architecturally cannot produce.
Every finding names its rule and its statute. Every score decomposes to the
rules that produced it and can be rebuilt by hand. It refuses to convert absence
of evidence into a finding, and it says so in its own output — which is why it
can be handed to a country office with thin registries without becoming an
instrument against them.

**What SUNLIGHT is not yet.** Validated on structural ground truth — there is
none. Calibrated — the bands are documented defaults, and per §3.1 the top of
the scale is currently unreachable. Legally reviewed. Security audited.
Operationally durable — two stores are in-memory by design. And its evidence
maps are plausible sketches, not country-office fact.

**What stands between it and UNDP adoption.** Not engineering. The eight items
in §5 are dominated by things only an institution can supply: a data agreement,
counsel, an audit, and country offices willing to validate what SUNLIGHT should
expect to find in their jurisdiction. The technical gap that remains — structural
ground truth — is a data problem, not a code problem.

**The single next move.** Approve or reject §3.1. It is the one finding that
changes what institutions see, it is fully proven, and until it is settled every
band shown to anyone is capped at YELLOW regardless of how bad a contract is.
Nothing else in this document blocks a demonstration; that one does.

---

*Produced by full-system sweep at commit `36b30ef`. Every figure measured. The
DOJ floor was re-validated live against the full corpus after every phase and
was byte-identical throughout. Where this sweep made an error — the Phase 0
stage-count claim in §4.3 — the error is recorded rather than removed.*
