# SUNLIGHT Demo Script — 10 Minutes

**Audience:** World Bank INT, IMF Fiscal Affairs, national audit offices
**Setup:** API running at `$BASE_URL`, demo tenant pre-seeded

---

## 0:00–1:30 — The Problem

> "Global public procurement represents $13 trillion annually. Conservative estimates place fraud losses between 10-25% — that's $1.3 to $3.25 trillion stolen every year from budgets meant to build hospitals, schools, and infrastructure."

> "Current methods catch fraud years after the fact, if at all. Manual audits review less than 1% of contracts. SUNLIGHT changes that equation."

---

## 1:30–2:30 — Create a Tenant (Step 1)

```bash
curl -X POST $BASE_URL/api/v2/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "World Bank Integrity Unit",
    "slug": "wb-int",
    "tier": "enterprise",
    "webhook_url": "https://wb-int.example.com/sunlight-webhook"
  }'
```

**Expected:** Tenant created with `tenant_id`, `webhook_secret` returned.

**Talking point:** "Each client gets a fully isolated environment. Your data never touches another tenant's. We enforce this at both the application and database layers using PostgreSQL Row-Level Security."

---

## 2:30–4:00 — Ingest Contracts (Step 2)

```bash
curl -X POST $BASE_URL/ingest \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample_contracts.csv" \
  -F "format=csv"
```

**Expected:** Ingestion job created. 100 contracts processed in ~3 seconds.

**Talking point:** "You upload your procurement data — CSV, JSON, or PDF. SUNLIGHT normalizes it, validates required fields, and reports any data quality issues before scanning begins."

```bash
curl $BASE_URL/ingest/$JOB_ID  # Check ingestion status
```

---

## 4:00–5:30 — Submit Async Scan (Step 3)

```bash
curl -X POST $BASE_URL/api/v2/scan \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"idempotency_key": "demo-scan-001", "seed": 42}'
```

**Expected:** `{"job_id": "job_...", "status": "QUEUED"}`

Poll for progress:
```bash
curl $BASE_URL/api/v2/jobs/$JOB_ID
# {"status": "RUNNING", "progress_pct": 45, "progress_msg": "Scoring contracts"}
```

**Talking point:** "Scanning is asynchronous. You submit, we process in the background, and deliver results via your webhook. No blocking, no timeouts."

Wait for completion:
```bash
# {"status": "SUCCEEDED", "result": {"tier_counts": {"RED": 3, "YELLOW": 15, "GREEN": 82}}}
```

---

## 5:30–6:30 — Risk Inbox (Step 4)

```bash
curl $BASE_URL/api/v2/risk-inbox?tier=RED
```

**Show in dashboard UI:** RED tab with 3 contracts, sorted by triage priority.

| Contract | Vendor | Amount | Markup CI | Tier |
|----------|--------|--------|-----------|------|
| DOD-2024-0847 | Phantom Defense LLC | $47.2M | 312% | 🔴 RED |
| DOD-2024-1293 | Overcharge Systems | $23.8M | 187% | 🔴 RED |
| STATE-2024-0156 | GlobalConnect Inc | $8.4M | 245% | 🔴 RED |

**Workload banner:** "3 RED flags, 15 YELLOW → 167 flags/1K → estimated 13.5 analyst hours"

**Talking point:** "This is your prioritized investigation queue. RED means the statistical anomaly matches the profile of DOJ-prosecuted cases. Not allegations — risk indicators that warrant investigation."

---

## 6:30–8:30 — Case Packet Deep Dive (Step 5)

Click on DOD-2024-0847 (Phantom Defense LLC):

```bash
curl $BASE_URL/reports/evidence/DOD-2024-0847
```

**Show:**

⚠️ **RISK INDICATOR — NOT AN ALLEGATION**
*SUNLIGHT identifies statistical anomalies. Humans investigate and determine intent.*

**Evidence Summary:**
- **Price Deviation:** 312% above peer median (95% CI: [278%, 347%])
- **Bootstrap Percentile:** 99.2nd percentile among comparable contracts
- **Bayesian Posterior:** 0.87 fraud probability given evidence
- **Peer Comparison:** 47 comparable DoD IT contracts, median $11.4M
- **FDR Status:** Survives Benjamini-Hochberg correction at α=0.10

**Talking point:** "Every flag comes with the full evidence chain. The bootstrap confidence interval tells you the range. The Bayesian posterior combines multiple signals. The FDR correction ensures we're not flagging by chance alone. And this banner — 'risk indicator, not allegation' — is on every single output."

**Export:**
```bash
curl $BASE_URL/reports/evidence/DOD-2024-0847 -H "Accept: application/pdf" -o case_packet.pdf
```

---

## 8:30–9:15 — Portfolio View (Step 6)

```bash
curl $BASE_URL/api/v2/portfolio
```

**Show in dashboard:** Tier distribution donut, top flagged agencies, top flagged vendors.

**Talking point:** "The portfolio view shows you systemic patterns. Which agencies have the highest flag concentration? Which vendors appear repeatedly? This is where you find the networks, not just the individual cases."

---

## 9:15–10:00 — Webhooks & Admin (Step 7)

```bash
curl $BASE_URL/api/v2/webhooks/deliveries
```

**Show:** Delivery log with `scan.completed` event, DELIVERED status, signature header.

**Admin settings:**
```bash
curl $BASE_URL/api/v2/tenants/$TENANT_ID
```

**Talking point:** "Results are delivered to your systems automatically via signed webhooks. You control the thresholds, the rulepack version, who has access. Full audit trail on every action."

---

## Close

> "SUNLIGHT is not a black box. Every detection is explainable, every statistical claim is reproducible, and every output explicitly states it's a risk indicator — not an allegation. This is the infrastructure that makes corruption visible before it causes irreversible harm."

> "We're offering pilot programs starting at $500K annually. Three contracts and we're at $5-15M ARR. Who wants to be first?"

---

## Setup Prerequisites

1. Run `./infra/deploy.sh local` to start the stack
2. Demo tenant auto-seeds with sample data
3. API docs at `$BASE_URL/docs` (OpenAPI/Swagger)
4. Dashboard at `$BASE_URL/dashboard`

## Objection Handling

**"What about false positives?"**
> We've reduced flags/1K from 464 to 167 while maintaining 100% recall on DOJ-prosecuted cases. Our RED tier has 25%+ precision — meaning 1 in 4 RED flags is a real case. That's investigation-worthy.

**"How is this different from existing tools?"**
> No competitor offers DOJ-calibrated detection with full statistical explainability. Our outputs include confidence intervals, Bayesian posteriors, and FDR correction — they hold up to legal scrutiny.

**"Can we integrate with our existing systems?"**
> REST API, webhook delivery, CSV/JSON/PDF ingestion. We fit into your workflow, not the other way around.
