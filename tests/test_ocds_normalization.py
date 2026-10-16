"""Regression evidence for source fields lost by the fallback normalizer."""
from api import create_analysis_pipeline
from jurisdiction_profile import US_FEDERAL
from ingestion_quality import assess_ingestion_quality, input_mapping_gaps
from tca_rules import _extract, build_rules


def source():
    return {
        "ocid": "normalization-regression",
        "buyer": {"name": "Example authority", "id": "buyer-1"},
        "tender": {"procurementMethod": "open", "numberOfTenderers": 3,
                   "value": {"amount": 100000, "currency": "USD"},
                   "tenderPeriod": {"startDate": "2025-01-01", "endDate": "2025-02-01"}},
        "awards": [{"suppliers": [{"id": "supplier-1", "name": "Example supplier"}]}],
    }


def test_supplied_identity_and_period_fields_reach_normalized_dossier():
    raw = source()
    pipeline = create_analysis_pipeline(US_FEDERAL)
    dossier = pipeline.process(pipeline.ingest(raw))
    assert not dossier.errors
    assert dossier.buyer_id == "buyer-1"
    assert dossier.supplier_id == "supplier-1"
    assert dossier.supplier_name == "Example supplier"
    assert dossier.tender_start == "2025-01-01"
    assert dossier.tender_end == "2025-02-01"
    assert not input_mapping_gaps(dossier)
    missing = assess_ingestion_quality(dossier).missing_fields
    assert not set(missing).intersection({"buyer_id", "suppliers", "supplier_id", "tender_start", "tender_end"})
    assert _extract(dossier)["supplier_ids"] == ["supplier-1"]


def test_supplier_parties_retain_their_richer_supplied_record():
    raw = source()
    raw['parties'] = [{"id": "supplier-1", "name": "Example supplier", "roles": ["supplier"],
                       "address": {"streetAddress": "Example street"}}]
    pipeline = create_analysis_pipeline(US_FEDERAL)
    dossier = pipeline.process(pipeline.ingest(raw))
    assert dossier.suppliers == raw['parties']
    assert _extract(dossier)['supplier_addresses'] == ['example street']


def test_absent_identity_and_period_fields_remain_unknown():
    pipeline = create_analysis_pipeline(US_FEDERAL)
    dossier = pipeline.process(pipeline.ingest({'ocid': 'sparse-normalization'}))
    assert dossier.buyer_id == ''
    assert dossier.supplier_id == ''
    assert dossier.suppliers == []
    assert dossier.tender_start is None
    assert dossier.tender_end is None
    assert input_mapping_gaps(dossier) == []


def test_direct_award_rule_cites_its_procurement_basis_only():
    rule = next(rule for rule in build_rules(US_FEDERAL) if rule.rule_id == 'PROC-001')
    assert rule.evidence == US_FEDERAL.legal_citations['procurement_law']
    assert 'UNCAC Art. 16' not in rule.evidence
