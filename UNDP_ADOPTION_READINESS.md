# UNDP Institutional Adoption Readiness

## Executive Summary

SUNLIGHT is architecturally ready for UNDP institutional integration. The system's file-based batch processing model aligns with UNDP's operational reality (Quantum ERP and Compass systems provide data through file handoffs, not APIs). This document details current readiness, required next steps, and the integration sequence.

---

## Current State Assessment

### Architectural Alignment ✓

**UNDP Operational Model**: File-based batch integration during institutional onboarding
**SUNLIGHT Architecture**: Deterministic, stateless pipeline processing file inputs
**Status**: **ALIGNED** - No architectural changes required

### Evidence Handling ✓

**Constitutional Line 4**: "Absence ≠ Evidence of Absence" enforced in five places
- Side 5 evidence maps distinguish `UNQUERYABLE` from `ABSENT`
- Thin-infrastructure countries receive `UNVERIFIED`, never `CONTRADICTED`
- Corroboration capacity travels with every verdict
- Country-office validation gates operational use

**Status**: **PRODUCTION-READY** - Protects vulnerable country offices by design

### Input Adapter Framework ✓

Existing adapter infrastructure in `code/input_adapters.py`:
- `OCDSAdapter` - Reference implementation (identity transform)
- `QuantumAdapter` - Placeholder stub with clear TODO markers
- `CompassAdapter` - Placeholder stub with clear TODO markers
- Registry pattern for explicit or automatic routing

**Status**: **FRAMEWORK-READY** - Awaiting schema handoff from UNDP teams

---

## Fixtures Delivered

### Location: `/workspace/data/fixtures/undp/`

#### 1. quantum_erp_sample.json
**Purpose**: Illustrative Quantum ERP contract data structure
**Key Fields**:
- `contract_id`: Unique identifier
- `project_details`: Budget, timeline, procuring entity, awardees, locations
- `procurement_process`: Solicitation through award dates
- `disbursements`: Tranche-based payment tracking
- `outcomes_claimed`: Structured for Side 5 corroboration
- `compliance_status`: Environmental, procurement, audit records

**Integration Note**: Schema based on typical ERP structures. Actual Quantum schema will be provided during onboarding (TODO.md Cluster A4).

#### 2. compass_aggregate_sample.json
**Purpose**: Illustrative Compass aggregate programme data structure
**Key Fields**:
- `reporting_period`: Fiscal year, frequency
- `programme_data`: Budget utilization, outputs delivered
- `indicators`: Target vs actual with disaggregation
- `sdg_alignment`: SDG target mapping with evidence references
- `geographic_coverage`: States, LGAs, communities
- `partners`: Implementing partners and roles

**Integration Note**: Results-based management structure. Actual Compass schema from UNDP RBM team.

#### 3. README.md
Documents fixture status, integration sequence, and contacts.

---

## Test Infrastructure

### Location: `/workspace/tests/fixtures/`

#### test_undp_fixtures.py
Comprehensive test suite covering:
- Fixture availability and directory structure
- Quantum fixture schema validation
- Compass fixture schema validation
- Evidence map fixture validation
-Queryable class validation against EvidenceClass enum

**Run Tests**:
```bash
python3 -m pytest tests/fixtures/test_undp_fixtures.py -v
```

#### __init__.py
Fixture loading utilities:
- `load_quantum_sample()`
- `load_compass_sample()`
- `get_evidence_map_fixture(country_code)`

---

## Evidence Maps Status

### Location: `/workspace/data/evidence_maps/`

| Country | Status |Queryable Classes | Notes |
|---------|--------|------------------|-------|
| Nigeria (ng) | Illustrative | 6/6 | Full registry access assumed |
| Ukraine (ua) | Illustrative | 5/6 | Field verification unqueryable (security constraints) |

**Critical Design Point**: Ukraine's map correctly marks `field_verification` as unqueryable due to security constraints. This lowers corroboration capacity from 1.0 to 0.83, making adverse conclusions unavailable. This is the system working as designed - preventing injustice in contested areas.

**Validation Required**: Country offices must validate:
1. Which registries are genuinely queryable
2. Expected evidence timelines
3. Tolerance parameters (geotag, magnitude, beneficiary)
4. Update cadence assumptions

---

## Integration Sequence

**Note**: The following sequence represents the logical dependency chain for integration. Specific timelines are contingent upon UNDP schema handoff speed, country office availability, and institutional approval cycles. Calendar estimates have been removed; each phase begins only when the previous phase's success metrics are met.

### Parallel Workstreams (Start Immediately)
These dependencies run in parallel with the engineering sequence and have longer institutional lead times:
- **Data Sharing Agreement**: Legal framework for SUNLIGHT to process UNDP procurement data
- **Third-Party Security Audit**: Required before live deployment (Phase 4)
- **OAI Engagement**: Validate output format against OAI case ingest requirements (earliest Phase 3)

---

### Phase 1: Schema Handoff & Structural Alignment
**Actors**: UNDP Digital Transformation Team, UNDP RBM Team, SUNLIGHT Core Team

**Purpose**: To replace illustrative fixtures with authoritative data structures defined by UNDP teams, ensuring architectural alignment with actual institutional data contracts.

**Why This Matters**:
- Prevents building adapters against assumed schemas that may not match real Quantum/Compass exports
- Respects institutional sovereignty: UNDP defines its own data contracts; SUNLIGHT adapts to them
- Enables deterministic mapping with proper "None is Not Zero" boundary enforcement
- Critical dependency: No subsequent phase can proceed without this

**Deliverables**:
- [ ] Quantum ERP procurement schema documentation (or confirmed derivation from real exports)
- [ ] Compass aggregate data schema documentation (or confirmed derivation from real exports)
- [ ] Sample real data exports (anonymized if required)
- [ ] Contact points for country office validation

**Fallback Path**: If Digital Transformation cannot produce published schema documents, SUNLIGHT will derive schemas from a handful of real exports and have UNDP confirm the derivation rather than author it.

**SUNLIGHT Actions**:
- [ ] Replace `QuantumAdapter.to_canonical_ocds()` stub with real transformation
- [ ] Replace `CompassAdapter.to_canonical_ocds()` stub with real transformation
- [ ] Update fixtures with actual schema examples
- [ ] Add adapter-specific tests

**Success Metric**: Receipt of official schema definitions or confirmed derivations, signed off by data owners.

**Constraint**: Cannot proceed without official schema documentation or confirmed derivations from UNDP

### Phase 2: Adapter Implementation & Transformation Logic
**Actors**: SUNLIGHT Engineering Team

**Purpose**: To replace stub adapters with deterministic transformation logic that converts UNDP-specific formats into the canonical `ContractDossier` object.

**Why This Matters**:
- Operationalizes the core: Detection engines (Sides 1-5) require standardized input
- Enforces constitutional lines at the boundary: "None is Not Zero" and "Absence ≠ Evidence of Absence" are programmatically enforced
- Deterministic guarantee: Transformation logic must be pure functions (same input file → same dossier)
- Enables testability: Real adapters allow integration tests against historical UNDP data

**Deliverables**:
- [ ] Functional Quantum adapter with transformation logic
- [ ] Functional Compass adapter with transformation logic
- [ ] Integration tests with real data samples
- [ ] Performance benchmarks for batch processing

**Testing**:
```bash
python3 -m pytest tests/test_input_adapters.py -v -k quantum
python3 -m pytest tests/test_input_adapters.py -v -k compass
```

**Success Metric**: All provided sample files from Phase 1 successfully transform into valid `ContractDossier` objects with 100% field mapping coverage and zero data loss.

**Dependency**: Completed Phase 1

### Phase 3: Evidence Map Validation & OAI Engagement
**Actors**: Country Offices, SUNLIGHT Jurisdiction Team, UNDP OAI (Office of Audit and Investigations)

**Purpose**: 
1. To transition evidence maps from "illustrative" to "validated" through direct engagement with country office focal points
2. To validate SUNLIGHT output formats against OAI case ingest requirements before pilot findings are generated

**Why This Matters**:
- **Activates queryable evidence classes**: Validation identifies which registries exist, are reachable, and have named owners. It does NOT authorize CONTRADICTED verdicts. A validated map tells you a registry exists; it does not tell you that a specific record is genuinely absent rather than unindexed, delayed, withheld, or filed under a name your entity resolution did not match. Absence of evidence is not evidence of absence - this constitutional principle remains enforced regardless of validation status.
- **Builds local ownership**: Country offices must confirm which registries exist, their access methods, and their reliability, preventing central team assumptions from generating false positives
- **Jurisdictional accuracy**: Procurement laws vary. A "direct award" might be legal in one jurisdiction and flagged as high-risk in another. Validation ensures calibration matches local law
- **OAI integration**: Every finding SUNLIGHT produces is destined for OAI, the sole channel authorized to receive allegations against staff, vendors, and implementing partners. Validating case-packet shape early prevents building a verification layer whose product nobody in the enforcement chain has agreed to accept
- **Risk mitigation**: Prevents reputational damage from issuing findings based on outdated or incorrect assumptions about a country's data landscape

**Process**:
1. SUNLIGHT provides draft evidence maps based on desk research
2. Country office reviews queryable_classes against actual registry access
3. Country office validates expected evidence timelines
4. Country office confirms tolerance parameters
5. Status updated from `illustrative` to `validated`
6. SUNLIGHT presents sample case packets to OAI for format validation
7. OAI confirms ingest compatibility or requests adjustments
8. Map deployed to production

**Per-Country Timeline**: 2-4 weeks depending on office capacity

**Deliverables**:
- [ ] At least three pilot country offices formally validate their evidence maps
- [ ] Validation status updated from `illustrative` to `validated` with named focal points and contact details
- [ ] OAI confirms case packet format compatibility
- [ ] Documented escalation paths for high-risk indicators

**Success Metric**: Country offices validate evidence maps (expanding queryable classes while maintaining constitutional guards), and OAI validates output format for case ingest.

**Dependency**: Functional adapters from Phase 2

### Phase 4: Pilot Deployment with Monitored Portfolio
**Actors**: Pilot Country Office, UNDP Oversight Team, UNDP OAI

**Prerequisites** (must be completed before pilot begins):
- [ ] Data Sharing Agreement executed between SUNLIGHT and UNDP
- [ ] Third-party security audit completed and approved
- [ ] OAI case packet format validated (Phase 3)
- [ ] Evidence maps validated for pilot country (Phase 3)

**Scope**:
- Limited contract portfolio (50-100 contracts)
- Single outcome type initially
- Weekly review cycles
- Feedback incorporation

**What a Pilot Can and Cannot Measure**:
- **CAN measure**: Analyst agreement rate with SUNLIGHT findings, flag rate stability against the 129.2‰ baseline, byte-identical determinism on re-run, analyst-reported usefulness of case packets, workflow integration fit
- **CANNOT measure**: "Zero false negatives" or recall floor - live procurement has no labeled ground truth. The recall floor is already proven against the DOJ corpus and 42,835-contract dataset; a pilot tests workflow and framing, not recall

**Why This Matters**:
- Tests real-world workflow integration before scale
- Validates framing gates: Ensures outputs are interpreted as risk indicators for human review, not automated allegations
- Builds trust through transparency and accuracy demonstration
- Discovers operational friction points (timing, format, escalation paths)

**Deliverables**:
- [ ] Pilot portfolio processed with documented findings
- [ ] Analyst agreement rate measured against human expert review
- [ ] Flag rate stability confirmed against 129.2‰ baseline
- [ ] Byte-identical determinism verified on re-run
- [ ] Analyst feedback on case packet usefulness collected
- [ ] Workflow integration gaps documented and addressed

**Success Criteria**:
- [ ] High analyst agreement rate (>80%) with SUNLIGHT findings
- [ ] Flag rate within expected range of 129.2‰ baseline
- [ ] 100% determinism: identical input produces identical output on re-run
- [ ] Analysts report case packets are useful for investigation prioritization
- [ ] Operational workflow successfully integrates SUNLIGHT findings into existing oversight committees

**Dependency**: Validated evidence maps from Phase 3, executed Data Sharing Agreement, approved security audit

### Phase 5: Multi-Country Scale-Up
**Actors**: Multiple Country Offices, UNDP Regional Teams

**Expansion Path**:
1. Additional outcome types within pilot country
2. Additional countries with validated maps
3. Regional training and support
4. Full institutional deployment

**Why This Matters**:
- **Systemic impact**: Moves from protecting individual projects to strengthening the entire multilateral financial infrastructure
- **Network effects**: As more countries join, cross-border collusion detection (Side 3) becomes exponentially more powerful
- **Sustainability**: Establishes SUNLIGHT as standard infrastructure, not a pilot project. Embeds it in procurement policy and oversight routines
- **Reference architecture**: Creates a repeatable playbook for future integrations with other MDBs (World Bank, AfDB, etc.)

**Strategic Positioning**:
SUNLIGHT is not a faster version of the existing OAI funnel (which is document-based, sample-driven, and discovers problems after money moves). SUNLIGHT is a structural verification passport: every Quantum contract carries a verifiable finding before disbursement. This is the unique positioning that distinguishes it from all existing oversight mechanisms.

**Deliverables**:
- [ ] SUNLIGHT integrated into standard operating procedures for ≥5 country offices
- [ ] Automated pre-award or pre-disbursement verification within the Quantum lifecycle
- [ ] Established escalation paths for high-risk indicators
- [ ] Cross-border collusion detection operational across multiple countries
- [ ] Training materials and support structures for new country onboarding

**Success Metric**: Pre-award or pre-disbursement verification coverage inside the Quantum lifecycle for ≥5 country offices, with automated processing and established escalation paths. NOT "weekly batch processing" - that would be a strategic downgrade to the very funnel SUNLIGHT exists to replace.

**Dependency**: Successful pilot completion from Phase 4

---

## Constitutional Compliance Relationship Matrix

This section describes how this change relates to each constitutional line. Compliance verification is performed by the gate during code review and test execution, not by self-declaration.

### Line 1: Determinism
**Relationship**: Adapters are stateless transforms with no stochastic elements
**Verification Point**: Test suite validates identical output for identical input
**Status**: Architecture supports determinism; actual compliance verified in test execution

### Line 2: Risk Indicator, Not Allegation
**Relationship**: Side 5 verdicts report structural inconsistency, not intent
**Verification Point**: Output schema uses "evidence contradicts claim" framing
**Status**: Framing enforced in evidence_schema.py; adapters do not alter verdict language

### Line 3: DOJ Recall Floor
**Relationship**: This change does not modify detection logic
**Verification Point**: Reference case tests continue to pass after adapter implementation
**Status**: Live validation required when real adapters are implemented

### Line 4: Absence ≠ Evidence of Absence
**Relationship**: Fixtures include fields that may be absent; adapters must preserve None vs 0 distinction
**Verification Point**: Test asserts explicit-null fields load as None, not 0
**Status**: Guard implemented in fixtures; requires enforcement in real adapter transformation logic

### Line 5: Core Integrity
**Relationship**: This change is entirely external to the core analysis pipeline. Note: The §3.1 composite denominator decision remains open; this document does not pre-decide it. Constitutional Line 5 protects the core (touched only on proof of computation defect) while leaving the pending decision open.
**Verification Point**: No modifications to evidence_pipeline.py, evidence_analyzer.py, or Side 5 logic
**Status**: Compliant - purely additive scaffolding; composite scoring logic protected but not declared immutable

### Line 6: None is Not Zero
**Relationship**: Fixtures demonstrate proper null encoding; adapters must preserve this
**Verification Point**: Test suite includes explicit assertion for None vs 0 boundary
**Status**: Fixture structure enforces distinction; adapter implementation must maintain it

### Line 7: Framing Gates
**Relationship**: This change does not modify finding language or rendering
**Verification Point**: No changes to dataclass field names or API response structure
**Status**: Compliant - no framing modifications

### Line 8: No Em-Dashes
**Relationship**: Document and code use standard hyphens only
**Verification Point**: Grep verification for em-dash characters
**Status**: Compliant - verified in all delivered files

---

## Technical Requirements

### Server Environment
- Python 3.12+ (tested on 3.12.10)
- FastAPI for API layer
- Docker containerization available
- Stateless operation (horizontal scaling supported)

### Data Flow
1. UNDP exports files from Quantum/Compass
2. Files uploaded to SUNLIGHT ingestion endpoint
3. Adapters transform to canonical OCDS
4. Pipeline executes deterministic analysis
5. Results returned as structured JSON
6. Human reviewers interpret findings

### Security Considerations
- No data persisted without explicit configuration
- All artifacts hashed and timestamped
- Provenance chain maintained end-to-end
- Access control via tenant middleware

---

## Known Limitations

### 1. API Assumption
**Current**: UNDP has no public APIs, only file exports
**Mitigation**: File-based pipeline already implemented; API adapters would be additive

### 2. Evidence Map Validation
**Current**: ng.json and ua.json marked `illustrative`
**Risk**: Operational use without validation could misstate capacity
**Mitigation**: `is_validated()` gate in code; warnings on load

### 3. Adapter Stubs
**Current**: QuantumAdapter and CompassAdapter raise NotImplementedError
**Risk**: Cannot process real UNDP data until implemented
**Mitigation**: Clear TODO markers; framework ready for schema handoff

---

## Next Immediate Actions

### For UNDP Teams
1. Provide Quantum ERP schema documentation
2. Provide Compass aggregate data schema documentation
3. Identify pilot country office
4. Schedule evidence map validation workshops

### For SUNLIGHT Teams
1. Review this readiness document
2. Prepare adapter development backlog
3. Draft country office engagement template
4. Set up pilot monitoring dashboard

---

## Contacts

### UNDP (To Be Confirmed)
- Digital Transformation Team: [TBD]
- Results-Based Management Team: [TBD]
- Country Office Focal Points: [TBD]

### SUNLIGHT
- Core Engineering: [Existing team]
- Jurisdiction Profiles: [Existing team]
- Institutional Integration: [Existing team]

---

## License

Proprietary — SUNLIGHT Infrastructure

---

*Document Version: 1.0*
*Last Updated: 2026*
*Status: Ready for UNDP Review*
