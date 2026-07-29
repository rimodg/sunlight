# SUNLIGHT — Handover Package

Everything an engineering team needs to deploy SUNLIGHT without the authors in the room.

**Procurement Integrity Verification Infrastructure.** A 16-stage deterministic pipeline
across five sides: procurement integrity, delivery verification, intelligence alerting,
recovery redirection, and independent evidence corroboration.

---

## Read this first: what is NOT yet validated

This package is honest about its own state. Two things must be settled by the deploying
institution before SUNLIGHT is relied upon in production. Neither is a defect; both are
work that can only be done on your side.

### 1. DOJ validation must be re-confirmed on the deploying machine

The five headline metrics were confirmed by **live execution** on the authoring machine
on 2026-07-29, against the full 42,835-contract corpus, with zero drift from the recorded
baseline:

| Metric | Value | Produced by |
|---|---|---|
| Precision | 33.3% | `code/doj_validation.py` |
| Recall | **100.0%** | `code/doj_validation.py` |
| False Positive Rate | 9.0% | `code/doj_validation.py` |
| PR-AUC | 0.7456 | `code/evaluation.py` |
| Flags per 1,000 | 129.2 | `code/evaluation.py` |

Confusion matrix: TP 9 · FN 0 · FP 18 · TN 182. CI gate: PASS on all three checks.

**Note that two different tools produce these numbers.** `doj_validation.py` emits no
PR-AUC at all; `evaluation.py` produces PR-AUC and flags-per-1k. Run both:

```bash
python3 code/doj_validation.py --db <your_db> --cases prosecuted_cases.json \
        --seed 42 --bootstrap 1000 --clean 200
python3 code/evaluation.py     --db <your_db> --cases prosecuted_cases.json \
        --seed 42 --bootstrap 1000 --clean 200 --profile doj_federal
```

`--clean 200` matters. The default is 50, and running the default produces different
numbers for a sampling reason that looks like drift but is not. Sampling is otherwise
deterministic by design, so identical inputs must reproduce identically — any real drift
is signal, not noise.

**The corpus is not in this repository.** It is a SQLite database with a `contracts`
table (42,835 rows in the reference corpus). Without it, validation cannot run and the
in-suite `tests/test_doj_calibration.py` is the only available proxy.

### 2. Side 5 evidence maps are ILLUSTRATIVE, not validated

`data/evidence_maps/ng.json` and `ua.json` both carry `"status": "illustrative"`. They
encode a *plausible* evidence landscape, not a confirmed one.

This is not a formality. `queryable_classes` drives corroboration capacity, which decides
whether Side 5 may draw an adverse conclusion at all. **A map that overstates a country's
registries would unlock findings its evidence base cannot support.** Have the country
office confirm each source is genuinely queryable, then set `"status": "validated"`.
`CountryEvidenceProfile.is_validated()` is the check to gate operational use on.

---

## Contents

| File | What it is |
|---|---|
| `README.md` | This file: quickstart, caveats, verification |
| `ARCHITECTURE.md` | System architecture and the anti-circularity firebreak |
| `SYSTEM_REFERENCE.md` | Full system reference, MJPIS, jurisdiction model |
| `INTEGRATION.md` | Integration guide for institutional pipelines |
| `DOCKER.md` | Container deployment detail |
| `Dockerfile`, `docker-compose.yml` | Build and run |
| `openapi.json` | Full OpenAPI 3 spec, 27 paths (regenerated from the live app) |
| `samples/` | Real request payloads, canonical OCDS shape |
| `samples/expected/` | Verified responses, for deployment self-check |

---

## 10-minute quickstart

### 1. Clone and build (≈3 min)

```bash
git clone https://github.com/rimodg/sunlight.git
cd sunlight
docker build -t sunlight .
```

### 2. Run (≈30 sec)

```bash
docker run -p 8000:8000 sunlight
# or: docker compose up
```

### 3. Confirm it is alive

```bash
curl -s localhost:8000/health
curl -s localhost:8000/version
```

`/version` returns the MJPIS standard version and registered jurisdiction profiles.

### 4. Run one contract through

```bash
curl -s -X POST localhost:8000/analyze \
     -H 'Content-Type: application/json' \
     -d @handover/samples/flagged_contract.json | python3 -m json.tool
```

### 5. Verify your deployment matches ours

```bash
curl -s -X POST localhost:8000/analyze -H 'Content-Type: application/json' \
     -d @handover/samples/flagged_contract.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin); d.pop('processing_time_ms',None); print(json.dumps(d,indent=2,sort_keys=True))" \
  > /tmp/actual.json

python3 -c "
import json
exp=json.load(open('handover/samples/expected/flagged_expected.json')); exp.pop('_note',None)
act=json.load(open('/tmp/actual.json'))
print('MATCH' if exp==act else 'DIFFERS')
"
```

`processing_time_ms` is the only volatile field and is stripped from the expected outputs.
Everything else must match byte-for-byte. The engine is deterministic: same input, same
output, forever.

### 6. Interactive API docs

Open `http://localhost:8000/docs` — auto-generated OpenAPI UI for all 27 endpoints.

---

## The samples, and what they actually produce

| Sample | `gate_verdict` | `structure.verdict` | Confidence | Contradictions |
|---|---|---|---|---|
| `flagged_contract.json` | `yellow` | `compromised` | 0.55 | 2 |
| `clean_contract.json` | `green` | `sound` | 0.95 | 0 |

**Why the flagged sample is YELLOW and not RED — this is expected, not a fault.**

EVG issues RED only when **2 or more** of its three dimensions fire. In the current build:

- `cri_bribery_channel` is **hardcoded to never fire** (`evg.py:145`) — the consumer
  module that would feed it does not exist yet.
- `cri_markup` needs peer-cohort comparables drawn from a contract corpus.

A single contract posted to `/analyze` carries no corpus context, so only
`tca_typologies` can fire. **Gate RED is therefore unreachable via single-contract
`/analyze`; YELLOW is the ceiling.** RED is reachable through the corpus-backed batch
path where markup comparables exist. Budget accordingly when demonstrating the system.

---

## Known issues a receiving team will hit

Stated plainly so you do not spend a day rediscovering them.

**1. `contradictions[].rule_id` is empty in API responses.** The engine emits findings
keyed `rule`; `api.py` reads `rule_id`, so it silently defaults to `""` on every finding.
`severity` and `legal_citations` are likewise never populated — the legal citations do
come through, but in the `evidence` field. The finding text in `description` is correct.
This means the system's "every flag traces to a rule ID" property is not currently visible
through the API. One-line mapping fix; no test covers the field, which is why it survived.

**2. `capacity_budget` does not bind under ties.** Contracts tied at the threshold score
are all admitted, so a budget of 2 over 9 identically-scored contracts returns 9. Tracked
as `xfail(strict=True)` in `tests/test_api.py`. Deferred deliberately: breaking the tie
means choosing which 2 of 9 identical contracts an investigator receives, and every
mechanical answer is arbitrary.

**3. `reportlab` is an optional dependency.** Required only for PDF evidence packets.
The module imports and CSV export works without it; `build_pdf()` raises with the install
command. `pip install reportlab` to enable.

---

## Verifying the build yourself

```bash
PYTHONPATH=code python -m pytest tests/ -q
```

Expect **1,747 passed, 7 skipped, 1 xfailed**. The xfail is item 2 above and is expected —
`strict=True` means the suite fails if it starts passing without the fix being removed.

---

## The five sides

| Side | Question | Stages | Verdicts |
|---|---|---|---|
| 1 — Procurement | Should this contract be awarded? | 1–8 | GREEN / YELLOW / RED |
| 2 — Delivery | Was what was promised delivered? | 9–12 | GREEN / YELLOW / RED |
| 3 — Alerts | Who needs to know, now? | — | CRITICAL → ADVISORY |
| 4 — Recovery | What happened to the money? | — | IDENTIFIED → CLOSED |
| 5 — Evidence | Does independent evidence corroborate it? | 13–16 | VERIFIED / PARTIAL / **UNVERIFIED** / CONTRADICTED |

The loop closes: Side 1 flags a contract → Side 4 tracks the recovered money → Side 2
verifies the replacement was delivered → Side 5 corroborates the outcome against evidence
that never routed through the implementing partner → and only then may Side 4 close the
cycle. Side 3 fires CRITICAL the moment independent evidence contradicts a claim that
passed every documentary gate.

**Delivery GREEN + corroboration CONTRADICTED is the highest-value finding the system can
produce.** Sides 1 and 2 read documents authored by parties with an interest in the
answer, so a clean procurement and delivery file is precisely what a competently executed
false claim looks like. Only independent evidence can reach it.

### The constraint that governs Side 5

**UNVERIFIED is never CONTRADICTED.** Absence of reachable evidence is not evidence of
fraud. A country with no digital land registry, no utility connection database and no
health information system cannot produce the evidence that would corroborate a *true*
claim — so treating its silence as a finding would mean SUNLIGHT systematically finding
against the poorest countries for being poor.

This is enforced structurally rather than by convention, in five independent places, and
the ordering is the mechanism: **corroboration capacity is checked before any finding is
consulted**, so a low-capacity dossier cannot reach an adverse verdict whatever the rules
concluded. Two endpoints exist solely to disclose limits — `/evidence/capacity/{country}`
reports what SUNLIGHT cannot verify in a jurisdiction, and
`/evidence/expected/{outcome_type}` publishes what it will look for *before* anything is
submitted.

---

## What is deliberately NOT in this package

- **The contract corpus.** 76 GB. Supply your own database with a `contracts` table.
- **Secrets.** No keys, tokens, or credentials. `docker-compose.yml` uses environment
  interpolation with safe defaults throughout.
- **MJPIS corpus and derivation internals.** The architecture and properties are
  described in `SYSTEM_REFERENCE.md` and `ARCHITECTURE.md` — both already public in the
  repository — but neither `research/corpus/` nor the derivation implementation is shipped
  here. If the derivation is required for your deployment, request it separately.

---

## Support boundary

Every finding SUNLIGHT produces is a **risk indicator, not an allegation**. Every
allocation is a **recommendation, not a directive**. A CONTRADICTED corroboration verdict
states that independent evidence is inconsistent with the claim as recorded; it does not
assert what did or did not physically occur.

The deploying institution controls data residency, authentication, and routing at the
deployment boundary. SUNLIGHT persists nothing across a restart, and evidence content is
hashed at ingestion and discarded rather than stored.
