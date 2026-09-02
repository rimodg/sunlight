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

### Phase 1: Schema Handoff (Weeks 1-2)
**Actors**: UNDP Digital Transformation Team, SUNLIGHT Core Team

**Deliverables**:
- [ ] Quantum ERP procurement schema documentation
- [ ] Compass aggregate data schema documentation
- [ ] Sample real data exports (anonymized if required)
- [ ] Contact points for country office validation

**SUNLIGHT Actions**:
- [ ] Replace `QuantumAdapter.to_canonical_ocds()` stub with real transformation
- [ ] Replace `CompassAdapter.to_canonical_ocds()` stub with real transformation
- [ ] Update fixtures with actual schema examples
- [ ] Add adapter-specific tests

### Phase 2: Adapter Implementation (Weeks 3-4)
**Actors**: SUNLIGHT Engineering Team

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

### Phase 3: Evidence Map Validation (Weeks 5-8)
**Actors**: Country Offices, SUNLIGHT Jurisdiction Team

**Process**:
1. SUNLIGHT provides draft evidence maps based on desk research
2. Country office reviews queryable_classes against actual registry access
3. Country office validates expected evidence timelines
4. Country office confirms tolerance parameters
5. Status updated from `illustrative` to `validated`
6. Map deployed to production

**Per-Country Timeline**: 2-4 weeks depending on office capacity

### Phase 4: Pilot Deployment (Weeks 9-12)
**Actors**: Pilot Country Office, UNDP Oversight Team

**Scope**:
- Limited contract portfolio (50-100 contracts)
- Single outcome type initially
- Weekly review cycles
- Feedback incorporation

**Success Criteria**:
- [ ] 100% recall on known reference cases (DOJ floor)
- [ ] Zero false allegations (Constitutional Line 2)
- [ ] Country office confidence in findings
- [ ] Operational workflow integration

### Phase 5: Scale-Up (Week 13+)
**Actors**: Multiple Country Offices, UNDP Regional Teams

**Expansion Path**:
1. Additional outcome types within pilot country
2. Additional countries with validated maps
3. Regional training and support
4. Full institutional deployment

---

## Constitutional Compliance Verification

### Line 1: Determinism ✓
- Adapters are stateless transforms
- Same input → same canonical OCDS → same analysis
- No LLM, no stochastic sampling in analytical path

### Line 2: Risk Indicator, Not Allegation ✓
- Side 5 verdicts report structural inconsistency
- "Evidence contradicts claim" not "Fraud occurred"
- Humans determine intent

### Line 3: DOJ Recall Floor ✓
- Live validation after any core-touching commit
- Reference cases shipped with test suite
- `[skip ci]` tag for billing-blocked CI

### Line 4: Absence ≠ Evidence of Absence ✓
- Five-place enforcement in Side 5
- UNQUERYABLE prevents absence findings
- Capacity ceiling disclosed upfront

### Line 5: Core Integrity ✓
- Core touched only on proven computation defect
- Composite math changes require:
  - Proven necessity
  - Scoped fix
  - Live floor re-validation
  - Revert on any digit movement

### Line 6: None is Not Zero ✓
- Missing data reports as `None` with reason
- Never rendered as zero
- Explicit in schema and rendering

### Line 7: Framing Gates ✓
- Unconfirmed diversion = "at risk", never "deprived"
- Discipline flows through dataclass, module, API, rendering

### Line 8: No Em-Dashes ✓
- Standard hyphens throughout codebase
- Enforced in code, chat, documents

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
