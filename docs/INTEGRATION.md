# SUNLIGHT Integration Guide

**For institutional integration teams deploying SUNLIGHT into procurement integrity pipelines.**

---

## 1. What SUNLIGHT Is and What Integration Looks Like

SUNLIGHT is procurement integrity analysis infrastructure exposed as a containerized HTTP service. It performs structural analysis on individual procurement contracts using Topological Contradiction Analysis (TCA), statistical risk indicators, and evidence verification gates, returning explainable tiered risk assessments with full legal citations.

Integration means deploying the SUNLIGHT container inside the institution's private network, routing contract data through HTTP endpoints (POST /analyze for single contracts, POST /batch for bulk processing), and consuming the structural findings in the institution's investigation workflow. The service is stateless and horizontally scalable — each request is independent, and multiple instances can run behind a load balancer for high throughput.

SUNLIGHT is designed for five institutional integration points: **(1) Quantum pre-award verification** — structural validation before contract execution in UNDP's Quantum ERP system, **(2) OAI tip triage** — prioritizing external whistleblower tips by structural risk score in the Office of Audit and Investigations workflow, **(3) Compass drill-down depth layer** — providing contract-level integrity analysis beneath the aggregate indicators displayed in UNDP's Global Anti-Corruption Data Dashboard, **(4) reconstruction integrity scanning** — validating the structural coherence of contracts entering disaster recovery or post-conflict reconstruction databases, and **(5) donor reporting impact quantification** — measuring corruption exposure reduction in portfolio reporting to bilateral and multilateral funders. The full architectural description is in `SUNLIGHT_SYSTEM_REFERENCE.md` at the repository root.

---

## 2. Quick Start

A minimal working deployment takes under 10 minutes. This quick start verifies that the service runs and processes a single contract.

**Prerequisites:** Docker and Docker Compose installed, git available.

**Step 1 — Clone the repository:**

```bash
git clone https://github.com/rimodg/sunlight.git
cd sunlight
```

**Step 2 — Start the service:**

```bash
docker compose up -d
```

The service builds and starts in detached mode. Initial build takes 1-2 minutes.

**Step 3 — Verify the service is running:**

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "profiles_available": 2,
  "timestamp": "2026-04-10T20:30:00.000000Z"
}
```

**Step 4 — Analyze a single contract:**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d @examples/single_contract.json
```

Expected response structure:

```json
{
  "ocid": "ocds-example-001",
  "stage": "structure",
  "profile_used": "us_federal",
  "structure": {
    "confidence": 0.85,
    "verdict": "SOUND",
    "contradictions": [],
    "feedback_traps": []
  },
  "gate_verdict": null,
  "errors": [],
  "processing_time_ms": 45.2,
  "recommended_for_investigation": false
}
```

The `structure.verdict` field indicates the overall structural assessment (SOUND, CONCERN, COMPROMISED, or CRITICAL). The `contradictions` array lists any structural integrity violations detected by the TCA rule engine.

**Step 5 — Stop the service:**

```bash
docker compose down
```

---

## 3. Deployment

### Container Image

The Docker image is built using a multi-stage Dockerfile with:
- **Builder stage:** Python dependencies installed in a virtual environment
- **Runtime stage:** Non-root user (`sunlight:1000`), minimal attack surface, health check configured

The service runs as a non-root user for security. The Dockerfile is located at the repository root.

### Docker Compose

The `docker-compose.yml` file at the repository root defines the production deployment. Key configuration:

- **Port mapping:** `8000:8000` (host:container). Configurable via `SUNLIGHT_PORT` environment variable.
- **Health check:** Runs `GET /health` every 30 seconds with 3-second timeout and 5-second startup grace period.
- **Calibration store:** Persists in a named Docker volume `sunlight_calibration` so empirical statistics survive container restarts.
- **Resource limits:** Memory capped at 2GB, no swap allowed.
- **Security:** Capabilities dropped, read-only root filesystem, tmpfs for /tmp.

For multi-container deployments (API + database + webhook workers), see `docker-compose.full.yml`.

### Network Exposure and Authentication

**CRITICAL:** The default deployment has **no authentication, authorization, rate limiting, or audit logging** inside the container. The service is designed for localhost or private-network deployment only. Public network exposure requires adding an authentication/authorization layer at a reverse proxy or API gateway in front of SUNLIGHT.

For production deployments, the minimum security requirements are:
1. **TLS termination** at the edge (reverse proxy, API gateway)
2. **Authenticated access** via OAuth2, JWT, mTLS, or the institution's SSO infrastructure
3. **Rate limiting** per client to prevent resource exhaustion
4. **Audit logging** of every request at the gateway layer
5. **Network isolation** so SUNLIGHT is not reachable from the public internet

See the module docstring at the top of `code/api.py` for the explicit security constraint documentation.

### Environment Configuration

The service accepts these environment variables:

- `SUNLIGHT_PORT`: Port to listen on (default: `8000`)
- `LOG_LEVEL`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`; default: `INFO`)

The calibration store base directory is `calibration/` inside the container, mapped to the `sunlight_calibration` volume.

---

## 4. API Reference

All endpoints return JSON. The service uses FastAPI with auto-generated OpenAPI documentation at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` (ReDoc).

### GET /health

**Purpose:** Service health and readiness check.

**Request:** None

**Response:** `HealthResponse`

**Example:**

```bash
curl http://localhost:8000/health
```

**Response:**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "profiles_available": 2,
  "timestamp": "2026-04-10T20:30:00.000000Z"
}
```

The `status` field is `"ok"` when operational or `"degraded"` if the analysis engines fail to load.

---

### GET /version

**Purpose:** Deployment metadata and version information.

**Request:** None

**Response:** `VersionResponse`

**Example:**

```bash
curl http://localhost:8000/version
```

**Response:**

```json
{
  "sunlight_version": "4.0.0+bd44ace",
  "mjpis_version": "0.1",
  "profiles": ["us_federal", "uk_central_government"],
  "api_version": "v1"
}
```

The `sunlight_version` includes the git commit hash. The `mjpis_version` indicates the Multi-Jurisdiction Procurement Integrity Standard corpus version.

---

### GET /profiles

**Purpose:** List all available jurisdiction profiles with metadata.

**Request:** None

**Response:** `ProfileListResponse`

**Example:**

```bash
curl http://localhost:8000/profiles
```

**Response:**

```json
{
  "profiles": [
    {
      "name": "us_federal",
      "country_code": "US",
      "currency": "USD",
      "fiscal_year_end": "9/30",
      "description": "Jurisdiction profile for US"
    },
    {
      "name": "uk_central_government",
      "country_code": "GB",
      "currency": "GBP",
      "fiscal_year_end": "3/31",
      "description": "Jurisdiction profile for GB"
    }
  ]
}
```

---

### GET /input-formats

**Purpose:** List all registered input format adapters.

**Request:** None

**Response:** JSON object with `available_formats` array

**Example:**

```bash
curl http://localhost:8000/input-formats
```

**Response:**

```json
{
  "available_formats": ["ocds_release", "undp_quantum", "undp_compass"],
  "description": "Input format adapters convert heterogeneous procurement data formats into canonical OCDS release shape for SUNLIGHT ingestion. Use the 'input_format' field in analyze/batch requests to select an adapter explicitly, or omit it for automatic format detection."
}
```

Note: `undp_quantum` and `undp_compass` are placeholder adapters that currently raise `NotImplementedError`. See Section 7 for details.

---

### POST /analyze

**Purpose:** Analyze a single contract with jurisdiction calibration.

**Request:** `AnalyzeRequest`

**Response:** `AnalyzeResponse`

**Required fields:**
- `contract`: OCDS release payload with at minimum an `ocid` field
- `profile`: Jurisdiction profile name (e.g., `"us_federal"`, `"uk_central_government"`)

**Optional fields:**
- `include_graph`: Boolean, includes full TCA structural graph in response (default: `false`)
- `input_format`: String, explicit input format adapter name (default: `null`, auto-routing)

**Example (auto-routing, no input_format specified):**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d @examples/single_contract.json
```

**Example (explicit input_format):**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "contract": {
      "ocid": "ocds-test-002",
      "tender": {"value": {"amount": 150000, "currency": "USD"}},
      "parties": [],
      "awards": []
    },
    "profile": "us_federal",
    "input_format": "ocds_release"
  }'
```

**Response:**

```json
{
  "ocid": "ocds-test-002",
  "stage": "structure",
  "profile_used": "us_federal",
  "structure": {
    "confidence": 0.72,
    "verdict": "CONCERN",
    "contradictions": [
      {
        "rule_id": "TCA_RULE_005",
        "severity": "moderate",
        "description": "Missing competitive tender documentation",
        "evidence": "No tenderer information found for competitive procurement",
        "legal_citations": ["41 USC 3301", "48 CFR 15.101"]
      }
    ],
    "feedback_traps": []
  },
  "gate_verdict": null,
  "errors": [],
  "processing_time_ms": 52.3,
  "recommended_for_investigation": true
}
```

The `structure.verdict` field has four possible values:
- `SOUND`: No structural integrity concerns detected
- `CONCERN`: Minor structural irregularities detected, recommended for review
- `COMPROMISED`: Significant structural contradictions detected, recommended for investigation
- `CRITICAL`: Severe structural violations detected, recommended for immediate investigation

The `recommended_for_investigation` boolean is `true` when the structural verdict is CONCERN or higher (risk score >= 2.0).

---

### POST /batch

**Purpose:** Analyze multiple contracts in batch with jurisdiction calibration and capacity-calibrated thresholds.

**Request:** `BatchAnalyzeRequest`

**Response:** `BatchAnalyzeResponse`

**Required fields:**
- `contracts`: Array of OCDS release payloads (max 1000 contracts per batch)
- `profile`: Jurisdiction profile name for all contracts

**Optional fields:**
- `capacity_budget`: Integer, analyst investigation capacity for this batch (default: `null`, no capacity ceiling)
- `input_format`: String, explicit input format adapter name (default: `null`, auto-routing)

**Example (no capacity_budget, auto-routing):**

```bash
curl -X POST http://localhost:8000/batch \
  -H "Content-Type: application/json" \
  -d @examples/batch_contracts.json
```

**Example (with capacity_budget):**

```bash
curl -X POST http://localhost:8000/batch \
  -H "Content-Type: application/json" \
  -d '{
    "contracts": [
      {"ocid": "ocds-batch-001", "tender": {"value": {"amount": 100000, "currency": "USD"}}, "parties": [], "awards": []},
      {"ocid": "ocds-batch-002", "tender": {"value": {"amount": 200000, "currency": "USD"}}, "parties": [], "awards": []},
      {"ocid": "ocds-batch-003", "tender": {"value": {"amount": 150000, "currency": "USD"}}, "parties": [], "awards": []}
    ],
    "profile": "us_federal",
    "capacity_budget": 2
  }'
```

**Response:**

```json
{
  "results": [
    {
      "ocid": "ocds-batch-001",
      "stage": "structure",
      "profile_used": "us_federal",
      "structure": {"confidence": 0.65, "verdict": "SOUND", "contradictions": [], "feedback_traps": []},
      "gate_verdict": null,
      "errors": [],
      "processing_time_ms": 38.1,
      "recommended_for_investigation": false
    },
    {
      "ocid": "ocds-batch-002",
      "stage": "structure",
      "profile_used": "us_federal",
      "structure": {"confidence": 0.80, "verdict": "CONCERN", "contradictions": [...], "feedback_traps": []},
      "gate_verdict": null,
      "errors": [],
      "processing_time_ms": 45.2,
      "recommended_for_investigation": true
    },
    {
      "ocid": "ocds-batch-003",
      "stage": "structure",
      "profile_used": "us_federal",
      "structure": {"confidence": 0.78, "verdict": "CONCERN", "contradictions": [...], "feedback_traps": []},
      "gate_verdict": null,
      "errors": [],
      "processing_time_ms": 42.7,
      "recommended_for_investigation": true
    }
  ],
  "total_processed": 3,
  "total_errors": 0,
  "verdict_distribution": {
    "SOUND": 1,
    "CONCERN": 2
  },
  "threshold_metadata": {
    "statistical_threshold": 2.0,
    "capacity_budget": 2,
    "capacity_threshold": 2.78,
    "binding_threshold": 2.78,
    "recommended_count": 2
  }
}
```

The `threshold_metadata` object reports:
- `statistical_threshold`: The minimum risk score for investigation recommendation (fixed at 2.0, corresponding to CONCERN verdict floor)
- `capacity_budget`: The requested capacity (if provided, else `null`)
- `capacity_threshold`: The risk score quantile corresponding to the capacity budget (if provided, else `null`)
- `binding_threshold`: The actual threshold applied (`max(statistical_threshold, capacity_threshold)`)
- `recommended_count`: The number of contracts in this batch with `recommended_for_investigation: true`

When `capacity_budget` is `null`, all contracts clearing the statistical threshold are recommended. When `capacity_budget` is provided, at most `capacity_budget` contracts are recommended, selected as the highest-risk contracts that also clear the statistical floor.

---

### GET /calibration/{profile_name}

**Purpose:** Return the current empirical calibration state for a jurisdiction profile.

**Request:** Path parameter `profile_name` (e.g., `us_federal`)

**Response:** `CalibrationStateResponse`

**Example:**

```bash
curl http://localhost:8000/calibration/us_federal
```

**Response:**

```json
{
  "profile_name": "us_federal",
  "total_contracts_analyzed": 1247,
  "verdict_counts": {
    "SOUND": 1050,
    "CONCERN": 142,
    "COMPROMISED": 48,
    "CRITICAL": 7
  },
  "rule_fire_counts": {
    "TCA_RULE_001": 89,
    "TCA_RULE_005": 142,
    "TCA_RULE_008": 63
  },
  "mean_risk_score": 1.42,
  "variance_risk_score": 0.68,
  "risk_score_min": 1.0,
  "risk_score_max": 4.85,
  "first_observation_utc": "2026-04-08T14:23:00Z",
  "last_observation_utc": "2026-04-10T19:45:00Z",
  "schema_version": "1.0"
}
```

Returns fresh zero-initialized state if no observations have been recorded yet for this profile (not a 404 error). The state accumulates observations from every batch analysis using this profile. See Section 8 for the calibration store architecture.

---

## 5. Jurisdiction Profiles

SUNLIGHT's detection calibration depends on the jurisdiction profile specified in the request. Each profile encodes:

- **Fiscal calendar:** Fiscal year end month/day for time-window calculations
- **Competitive procurement threshold:** The monetary value above which competitive tender is legally required
- **Currency:** The profile's default currency (USD, GBP, EUR, etc.)
- **Legal citations:** Jurisdiction-specific statute and regulation references used in finding descriptions
- **Base rate:** An estimate of the background corruption prevalence in the jurisdiction's procurement environment

Two profiles ship with SUNLIGHT today:

1. **`us_federal`**: United States federal procurement (fiscal year ends September 30, competitive threshold $250,000, legal framework anchored in 41 USC and 48 CFR)
2. **`uk_central_government`**: United Kingdom central government procurement (fiscal year ends March 31, competitive threshold £138,760, legal framework anchored in Public Contracts Regulations 2015)

The canonical profile definitions are in `code/jurisdiction_profile.py`. The architectural rationale for jurisdiction-specific calibration is in `SUNLIGHT_SYSTEM_REFERENCE.md` Section 3.2.

### Adding New Jurisdiction Profiles

Adding a new country profile is a **data task**, not a code task. No modifications to the analysis engine are required. To add a new jurisdiction:

1. Author a new `JurisdictionProfile` object in `code/jurisdiction_profile.py` with the country's fiscal calendar, competitive threshold, currency, legal citations, and base rate estimate
2. Register the profile in the `_PROFILE_REGISTRY` dict in `code/api.py`
3. Verify the profile appears in `GET /profiles` response

The TODO.md Phase B Jurisprudence Engine work (sub-tasks 2.3.1 through 2.3.9) expands the validation corpus beyond the current US DOJ seed corpus to include UK SFO Deferred Prosecution Agreements, French PNF CJIPs, and World Bank INT Sanctions Board cases. This multi-jurisdiction corpus will calibrate threshold values and legal citation mappings for the expanded profile set.

---

## 6. Capacity-Calibrated Thresholds

The `capacity_budget` parameter on POST /batch addresses a fundamental scaling problem in institutional procurement integrity: UNDP processes approximately 9 million contracts per year against investigator capacity of 10,000-20,000 analyst-hours annually. Even at 1% precision, a detection system would generate 90,000 flags per year — 4-9x the investigation capacity. SUNLIGHT solves this with capacity-calibrated thresholds that respect analyst throughput limits while preserving statistical precision.

### Mechanics

Every contract analysis produces a **risk score** combining the structural verdict (primary) with confidence (secondary tiebreaker):

- CRITICAL verdict → risk score 4.0 + confidence
- COMPROMISED verdict → risk score 3.0 + confidence
- CONCERN verdict → risk score 2.0 + confidence
- SOUND verdict → risk score 1.0 + confidence

The **statistical threshold** is fixed at 2.0 (CONCERN verdict floor). This is the statistical precision floor below which SUNLIGHT will not recommend a contract for investigation, regardless of capacity pressure.

When `capacity_budget` is provided, SUNLIGHT computes a **capacity threshold** as the risk score corresponding to the top-N quantile, where N = capacity_budget. The **binding threshold** is `max(statistical_threshold, capacity_threshold)`.

The `recommended_for_investigation` boolean on each contract result is `true` when the contract's risk score >= binding threshold.

### Example

Request with `capacity_budget: 2` over a batch of 5 contracts:

```json
{
  "contracts": [
    {"ocid": "A", ...},  // Risk score: 1.65 (SOUND)
    {"ocid": "B", ...},  // Risk score: 2.80 (CONCERN)
    {"ocid": "C", ...},  // Risk score: 3.45 (COMPROMISED)
    {"ocid": "D", ...},  // Risk score: 2.30 (CONCERN)
    {"ocid": "E", ...}   // Risk score: 4.20 (CRITICAL)
  ],
  "profile": "us_federal",
  "capacity_budget": 2
}
```

**Risk scores sorted descending:** 4.20, 3.45, 2.80, 2.30, 1.65

**Capacity threshold:** The 2nd-highest risk score = 3.45

**Binding threshold:** `max(2.0, 3.45)` = 3.45

**Recommended contracts:** E (4.20 >= 3.45), C (3.45 >= 3.45) — exactly 2 contracts

**Response `threshold_metadata`:**

```json
{
  "statistical_threshold": 2.0,
  "capacity_budget": 2,
  "capacity_threshold": 3.45,
  "binding_threshold": 3.45,
  "recommended_count": 2
}
```

When `capacity_budget` is `null`, the capacity threshold is effectively -∞, the binding threshold equals the statistical threshold (2.0), and all contracts with CONCERN or higher verdicts are recommended.

---

## 7. Input Format Adapters

SUNLIGHT accepts canonical OCDS release payloads natively. The `InputAdapter` protocol in `code/input_adapters.py` allows additional procurement data formats to be plugged into the ingestion pipeline without modifying the analysis engine.

### Currently-Registered Adapters

Three adapters are registered in the production registry returned by `GET /input-formats`:

1. **`ocds_release`** (OCDSAdapter): Reference implementation, fully operational. Accepts both single OCDS releases (dict with `ocid` at top level) and OCDS release packages (dict with `releases` array wrapping releases). For release packages, the adapter extracts the first release and discards the package wrapper. This is the adapter used when `input_format` is omitted (automatic routing) and the payload has an `ocid` field.

2. **`undp_quantum`** (QuantumAdapter): Placeholder for UNDP Quantum ERP procurement format payloads. The Quantum schema is not publicly documented and will be provided by UNDP integration teams during institutional onboarding. The adapter currently raises `NotImplementedError` with a descriptive message pointing to the TODO.md institutional onboarding sequence (Cluster A4, Phase B work). The `can_handle()` method returns `false` unconditionally, so this adapter never matches during automatic routing and must be invoked explicitly via `input_format: "undp_quantum"` once the schema is integrated.

3. **`undp_compass`** (CompassAdapter): Placeholder for UNDP Compass (Global Anti-Corruption Data Dashboard) aggregate procurement format payloads. The Compass schema is not publicly documented and will be provided by UNDP integration teams during institutional onboarding. The adapter currently raises `NotImplementedError`. Like QuantumAdapter, it returns `false` from `can_handle()` and must be invoked explicitly once integrated.

### Why Placeholders Exist

The placeholder adapters make extension points **explicit** for institutional integration teams. When UNDP developers read the codebase, they see `undp_quantum` and `undp_compass` in the registry listing and understand these are planned formats, not oversights. The placeholder stubs signal reserved extension points and prevent naming collisions during future schema integration work.

### Adapter Routing

When the `input_format` field is omitted from a POST /analyze or POST /batch request, SUNLIGHT uses **automatic routing**: the registry iterates registered adapters and selects the first one whose `can_handle(payload)` method returns `true`. For canonical OCDS payloads, this resolves to OCDSAdapter.

When `input_format` is explicitly specified (e.g., `"input_format": "ocds_release"`), SUNLIGHT uses the named adapter directly. If the named adapter does not exist, the request returns HTTP 400 with error message `"No adapter registered for format 'X'"`.

### Future Schema Integration

TODO.md Cluster A4 tracks the sequence for integrating Quantum and Compass schemas:

1. UNDP provides the canonical Quantum/Compass procurement data schema documentation
2. An integration team implements the `can_handle()` shape recognition logic (inspecting payload structure to detect Quantum vs. Compass vs. other formats)
3. The team implements the `to_canonical_ocds(payload)` transformation that converts Quantum/Compass payloads into the canonical OCDS release dict shape SUNLIGHT's pipeline expects
4. The `NotImplementedError` stub is replaced with the working transformation
5. The adapter becomes operational and automatic routing begins matching Quantum/Compass payloads

The architecture guarantees that once a schema is integrated, **no modifications to the analysis engine are required**. The adapter handles format heterogeneity; the pipeline consumes canonical OCDS uniformly.

---

## 8. Empirical Calibration Store

SUNLIGHT accumulates running empirical statistics per jurisdiction profile as batch analyses flow through the system. The calibration store is exposed via `GET /calibration/{profile_name}` and persists in the `sunlight_calibration` Docker volume.

### What the Store Observes

For each batch analysis, the calibration store records:

- **Total contracts analyzed:** Monotonic counter incremented by batch size
- **Verdict distribution:** Counts of SOUND, CONCERN, COMPROMISED, CRITICAL verdicts
- **Rule fire counts:** Per-rule counters tracking how often each TCA rule fired
- **Risk score statistics:** Running mean, variance, min, max of risk scores
- **Observation timestamps:** First and last observation times (UTC)

The store learns **what normal looks like** from operational flow. It does not store individual contract data, only aggregate distributions.

### Current Phase: Observation Only

The calibration store is currently in **observation-only mode** (Phase 1). It accumulates empirical distributions but does not yet feed them back into the detection path. The future phase (provisional sub-task 2.2.7l in TODO.md) will wire the accumulated distributions into the detection logic as empirical priors, tightening risk score calibration as operational volume grows.

### Architectural Separation: The Circular-Drift Firebreak

The calibration store embodies a critical architectural principle documented in `docs/ARCHITECTURE.md` Principle 4: **Separate empirical baselines (learned from operation) from pattern signatures (learned from ground truth)**.

SUNLIGHT needs to know two distinct things:
1. **What "normal" looks like** in the deployment environment (learned from operational flow via the calibration store)
2. **What "fraud" looks like** in validated ground truth (learned from the Multi-Jurisdiction Procurement Integrity Standard corpus at `research/corpus/prosecuted_cases_global_v0.1.json`)

These two knowledge channels must never cross. The calibration store learns only from operation. The fraud-pattern corpus updates only from external legal validation (US DOJ convictions, UK SFO DPAs, French PNF CJIPs, World Bank INT sanctions). The two channels share no state, no update hooks, and no contamination path.

This separation prevents **circular drift** — the failure mode where a detection system learns what "abnormal" looks like from its own detection output, eventually drifting into self-reinforcing false positives. The calibration store cannot contaminate the fraud-pattern channel because it never writes to the corpus. The corpus cannot contaminate the empirical baseline because validated cases are excluded from the operational statistics.

The firebreak is enforced at the implementation level: the calibration store (`code/calibration_store.py`) and the MJPIS derivation function (`code/mjpis_derivation.py`) operate on disjoint data structures with no shared write paths.

---

## 9. Security Posture

**The current SUNLIGHT deployment has no authentication, authorization, rate limiting, or audit logging inside the container.** This is an explicit design constraint documented in the module docstring at the top of `code/api.py`. Security is enforced at the deployment boundary and is the responsibility of the institution deploying SUNLIGHT.

### Current State

The Docker container:
- ✅ Runs as a non-root user (`sunlight:1000`)
- ✅ Drops unnecessary Linux capabilities
- ✅ Uses a read-only root filesystem with tmpfs for `/tmp`
- ✅ Enforces memory limits (2GB cap, no swap)
- ❌ Has **no authentication** — any client that can reach port 8000 can call any endpoint
- ❌ Has **no authorization** — no role-based access control, no per-client permissions
- ❌ Has **no rate limiting** — a single client can exhaust resources
- ❌ Has **no audit logging** — no record of who called what endpoint when

### Deployment Architecture for Production

SUNLIGHT is designed for **localhost or private-network deployment** with security enforced at the edge:

```
Internet → Institutional Gateway (auth + rate limiting + audit)
       → Private Network
       → SUNLIGHT API (localhost:8000, no auth)
       → SUNLIGHT pipeline
```

### Minimum Production Requirements

For production deployments where SUNLIGHT processes real institutional procurement data, the minimum security requirements are:

1. **TLS termination at the edge:** The reverse proxy or API gateway must terminate TLS 1.2+ and enforce certificate validation. SUNLIGHT's HTTP-only internal traffic never leaves the private network.

2. **Authenticated access:** The gateway must authenticate every request using the institution's identity infrastructure:
   - **OAuth2/OIDC** for browser-based institutional dashboards
   - **JWT** for service-to-service API calls (e.g., Quantum → SUNLIGHT)
   - **mTLS** for high-assurance institutional systems
   - **API keys** for legacy integrations (rotate regularly, scope narrowly)

3. **Rate limiting per client:** The gateway must enforce per-client rate limits to prevent resource exhaustion. Suggested starting limits: 10 requests/second for single-contract analysis, 1 request/minute for batch analysis.

4. **Audit logging at the gateway:** Every request must be logged with: timestamp, authenticated client identity, endpoint called, request payload hash (not full payload, to avoid logging PII), response status code, processing time. Logs must be tamper-evident and retained per institutional data retention policy.

5. **Network isolation:** SUNLIGHT must not be reachable from the public internet. Deploy inside the institution's private network or a dedicated VPC with firewall rules blocking inbound traffic from external networks.

### What SUNLIGHT Does NOT Provide

SUNLIGHT does **not** provide:
- User management or identity federation
- Role-based access control (RBAC) or attribute-based access control (ABAC)
- Multi-tenancy isolation (the calibration store is shared across all requests using the same profile)
- Data encryption at rest (the calibration store persists unencrypted in the Docker volume)
- Compliance certification (GDPR, SOC 2, ISO 27001, etc.)

These are the responsibility of the institution's deployment infrastructure and the gateway layer fronting SUNLIGHT.

---

## 10. Troubleshooting

### Container Fails to Start

**Symptom:** `docker compose up -d` exits with error, or `docker ps` shows the container is not running.

**Diagnosis:**

```bash
docker compose logs api
```

**Common causes:**

1. **Port 8000 already in use:** Another service is listening on port 8000. Change the port in `docker-compose.yml` under `ports:` to `8001:8000` or set the `SUNLIGHT_PORT` environment variable.

2. **Insufficient memory:** The container requires at least 2GB of available memory. Check `docker stats` to see current memory usage. Increase Docker Desktop's memory allocation in Preferences → Resources → Advanced.

3. **Build failure:** Dependency installation failed during the Docker build. Check the build logs for Python package installation errors. Common fix: ensure you have the latest `docker-compose.yml` and `Dockerfile` from the repository.

### GET /health Returns "degraded"

**Symptom:** `/health` endpoint returns `{"status": "degraded", ...}` instead of `{"status": "ok", ...}`.

**Diagnosis:** The analysis engines (TCA grapher, structure engine) are not loading successfully.

**Common causes:**

1. **Missing dependencies:** The Python environment inside the container is missing required packages. Rebuild the container: `docker compose down && docker compose build --no-cache && docker compose up -d`.

2. **Corrupted calibration store:** The calibration store database is corrupted. Remove the volume and restart: `docker compose down -v && docker compose up -d`.

3. **Filesystem permissions:** The non-root user cannot write to the `/app/calibration/` directory. This should not happen in the default Docker image but can occur if volumes are mounted from the host with incorrect permissions.

### POST /analyze Returns 400: "No registered adapter recognizes the payload shape"

**Symptom:**

```json
{
  "error": "Input format adapter error: No registered adapter recognizes the payload shape. Registered formats: ['ocds_release', 'undp_quantum', 'undp_compass']"
}
```

**Cause:** The input payload is not canonical OCDS (missing `ocid` field and not a release package) and no explicit `input_format` was specified.

**Fix 1 — Add the ocid field:**

Ensure the contract payload has an `ocid` field at the top level:

```json
{
  "contract": {
    "ocid": "ocds-your-identifier-here",
    "tender": {...},
    "parties": [...],
    "awards": [...]
  },
  "profile": "us_federal"
}
```

**Fix 2 — Specify input_format explicitly:**

If the payload is valid OCDS but the auto-routing fails, specify `input_format: "ocds_release"`:

```json
{
  "contract": {...},
  "profile": "us_federal",
  "input_format": "ocds_release"
}
```

### POST /analyze Returns 404: Profile Not Found

**Symptom:**

```json
{
  "detail": "Profile 'canada_federal' not found. Available: us_federal, uk_central_government"
}
```

**Cause:** The requested jurisdiction profile name is not registered.

**Fix:** Check the available profiles via `GET /profiles`:

```bash
curl http://localhost:8000/profiles
```

Use one of the profile names from the response (e.g., `us_federal` or `uk_central_government`).

If you need a profile for a jurisdiction not yet supported, see Section 5 for how to add new jurisdiction profiles.

### Batch Analysis Is Slower Than Expected

**Symptom:** POST /batch takes longer than anticipated for large batches.

**Cause:** TCA graph construction is per-contract and CPU-bound. A single instance processes contracts sequentially within a batch.

**Optimization strategies:**

1. **Parallelize across multiple SUNLIGHT instances:** Deploy multiple SUNLIGHT containers behind a load balancer. Split large batches into smaller batches and distribute them across instances. Each instance processes its batch independently.

2. **Right-size batch requests:** The maximum batch size is 1000 contracts per request. For very large datasets (100K+ contracts), split into multiple batches of 500-1000 contracts each and issue concurrent requests.

3. **Use capacity_budget to limit output volume:** If the bottleneck is downstream investigation capacity rather than SUNLIGHT throughput, use `capacity_budget` to limit the number of flagged contracts. This reduces the volume of results that must be processed by institutional workflows.

4. **Profile the workload:** If throughput is critical, measure the per-contract processing time via the `processing_time_ms` field in the response. Typical processing time for a contract with moderate complexity is 40-80ms. If you observe >200ms per contract, investigate whether the contract payloads contain unusually large `parties` arrays or deeply nested structures.

---

## 11. Support and Contribution

SUNLIGHT is currently under active development by Rimwaya Ouedraogo and Hugo Villalba.

### Documentation

- **Full system reference:** `SUNLIGHT_SYSTEM_REFERENCE.md` at the repository root describes the complete v4 architecture, the eight-stage pipeline, and the four analysis engines.
- **Architectural pattern:** `docs/ARCHITECTURE.md` documents the seven principles behind SUNLIGHT's scale-invariant institutional intelligence architecture.
- **Session planning:** `TODO.md` tracks the development roadmap, current priorities, and the integration-readiness arc.

### Integration Support

Integration teams with questions about deploying SUNLIGHT into institutional procurement pipelines should reach out to the maintainers through the channels established during their institutional engagement (typically direct email contact initiated by the engagement sponsor).

For institutions evaluating SUNLIGHT for adoption, the primary contact point is through the academic supervisor network (Professor Christelle Scharff at Pace University or equivalent institutional sponsor).

### Contribution Guidelines

SUNLIGHT is currently in a private development phase focused on completing the integration-readiness arc before the UNDP institutional outreach. Contribution guidelines for external developers will be published when the repository transitions to public open-source release (tracked in TODO.md Phase D).
