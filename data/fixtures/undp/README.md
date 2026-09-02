# UNDP Integration Fixtures

## Purpose

These fixtures support adapter development and testing during institutional onboarding. They are **illustrative samples only** - actual schemas will be provided by UNDP integration teams.

## Status

All fixtures in this directory are marked as `illustrative` status. They must not be used for production analysis until:
1. Actual schemas are provided by UNDP teams
2. Adapters are implemented against real schemas
3. Country offices validate evidence maps

## Available Fixtures

### quantum_erp_sample.json
- **Purpose**: Illustrative UNDP Quantum ERP contract data structure
- **Use Case**: Adapter development for procurement data ingestion
- **Key Fields**: contract_id, project_details, procurement_process, disbursements, outcomes_claimed
- **Reference**: TODO.md Cluster A4

### compass_aggregate_sample.json
- **Purpose**: Illustrative UNDP Compass aggregate programme data structure
- **Use Case**: Adapter development for results-based management data
- **Key Fields**: reporting_period, programme_data, outputs_delivered, sdg_alignment
- **Reference**: TODO.md Cluster A4

## Integration Sequence

During UNDP institutional onboarding:

1. **Schema Handoff**: UNDP provides actual Quantum/Compass schemas
2. **Adapter Implementation**: Replace placeholder adapters in `code/input_adapters.py`
3. **Fixture Update**: Replace these illustrative samples with real data examples
4. **Testing**: Validate adapters against real data
5. **Evidence Map Validation**: Country offices validate jurisdiction-specific evidence maps
6. **Production Deployment**: Enable adapters for operational use

## Evidence Maps

These fixtures work in conjunction with evidence maps in `/data/evidence_maps/`. Each country office must validate:
- Which evidence classes are queryable in their jurisdiction
- Expected evidence timelines and tolerances
- Source accessibility under local conditions

## Contact

For schema documentation and integration support:
- UNDP Digital Transformation Team
- UNDP Results-Based Management Team
- Country Office focal points

## License

Proprietary - SUNLIGHT Infrastructure
