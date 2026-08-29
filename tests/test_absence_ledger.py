"""
Increment 1: CPDOutputTarget schema growth + _get_absence_param.
Proves the growth is additive: old constructions and old JSON unchanged,
new fields round-trip, absent means None and never zero.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from cpd_allocation import (
    CPDOutputTarget,
    _parse_cpd_profile,
    load_cpd_profile,
)
from absence_ledger import _get_absence_param


def test_positional_construction_unbroken():
    """Existing tests build CPDOutputTarget positionally; growth must not break them."""
    o = CPDOutputTarget("3.1.1", "Primary clinics", "health", 1000.0, 400.0)
    assert o.output_id == "3.1.1"
    assert o.planned_capacity_description is None
    assert o.planned_beneficiaries is None
    assert o.planned_delivery_date is None
    assert o.source_document_citation is None


def test_parser_roundtrips_new_fields():
    data = {
        "country_office": "Testland",
        "country_code": "TL",
        "outputs": [{
            "output_id": "TL-H-001",
            "output_description": "Clinics",
            "pillar": "health",
            "target_amount": 5000000,
            "actual_spend": 1000000,
            "planned_capacity_description": "15 primary health clinics",
            "planned_beneficiaries": 30000,
            "planned_delivery_date": "2026-06-30",
            "source_document_citation": "CPD Testland 2023-2027, output 3.1.1",
        }],
    }
    prof = _parse_cpd_profile(data)
    o = prof.outputs[0]
    assert o.planned_capacity_description == "15 primary health clinics"
    assert o.planned_beneficiaries == 30000
    assert o.planned_delivery_date == "2026-06-30"
    assert o.source_document_citation == "CPD Testland 2023-2027, output 3.1.1"


def test_old_json_yields_none_not_zero():
    """A CPD without absence fields parses with None everywhere: not stated, not zero."""
    data = {
        "country_office": "Testland",
        "country_code": "TL",
        "outputs": [{
            "output_id": "TL-H-001",
            "output_description": "Clinics",
            "pillar": "health",
        }],
    }
    o = _parse_cpd_profile(data).outputs[0]
    assert o.planned_beneficiaries is None
    assert o.planned_beneficiaries != 0
    assert o.planned_delivery_date is None
    assert o.planned_capacity_description is None
    assert o.source_document_citation is None


def test_ng_profile_still_loads_with_none_fields():
    """Golden: the shipped illustrative profile loads; new fields read None until authored."""
    prof = load_cpd_profile("ng")
    assert prof is not None
    assert len(prof.outputs) > 0
    for o in prof.outputs:
        assert _get_absence_param(o, "planned_beneficiaries") is None


def test_get_absence_param_present_and_absent():
    o = CPDOutputTarget("X", "Y", "health", planned_beneficiaries=1200)
    assert _get_absence_param(o, "planned_beneficiaries") == 1200
    assert _get_absence_param(o, "nonexistent_field") is None
    assert _get_absence_param(o, "nonexistent_field", "fallback") == "fallback"


def test_none_default_is_none_not_falsy_zero():
    """The default for absence params is None, so absence is distinguishable from 0."""
    o = CPDOutputTarget("X", "Y", "health")
    v = _get_absence_param(o, "planned_beneficiaries")
    assert v is None and v != 0
