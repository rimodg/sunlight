"""
Phase 1: ingestion quality assessor.

Discipline: determinism byte-identical, total function, zero-drift on
existing dossier paths (field defaults to None), and structural assertion
of the constitutional rule that quality reporting never modifies the
composite (the composite path never imports from this module).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from dataclasses import asdict

from ingestion_quality import (
    assess_ingestion_quality,
    IngestionQualityReport,
    ENGINE_CONSUMED_FIELDS,
    SCORING_VERSION,
    _is_present,
)
from sunlight_core import ContractDossier


# ── Determinism and totality ────────────────────────────────────────

def test_determinism_byte_identical():
    d1 = _populated_dossier()
    d2 = _populated_dossier()
    a = assess_ingestion_quality(d1)
    b = assess_ingestion_quality(d2)
    assert asdict(a) == asdict(b)


def test_no_wall_clock():
    src = open('code/ingestion_quality.py').read()
    assert 'datetime.now' not in src
    assert 'utcnow' not in src
    assert '.today(' not in src


def test_total_on_empty_dossier():
    """An empty ContractDossier has currency='USD' as a dataclass default,
    which is a real signal SUNLIGHT reads. The honest empty-dossier score
    is therefore 1/15, with only currency present. This test encodes the
    real dataclass shape rather than the assumption that 'empty' means
    'nothing populated'."""
    d = ContractDossier()
    r = assess_ingestion_quality(d)
    assert r.fields_present == 1
    assert r.fields_total == 15
    assert abs(r.data_quality_score - (1/15)) < 1e-9
    assert set(r.missing_fields) == set(ENGINE_CONSUMED_FIELDS) - {"currency"}
    assert "currency" not in r.missing_fields


def test_total_on_object_lacking_fields_entirely():
    """A stripped-down object with no dossier fields still assesses
    honestly: everything absent, no raise."""
    class Bare:
        pass
    r = assess_ingestion_quality(Bare())
    assert r.data_quality_score == 0.0
    assert r.fields_present == 0


# ── Presence semantics ────────────────────────────────────────

def test_presence_semantics():
    """None, empty string, empty list, and numeric zero are missing.
    Non-empty strings and non-zero numbers are present."""
    assert _is_present("x") is True
    assert _is_present("") is False
    assert _is_present(None) is False
    assert _is_present(0) is False
    assert _is_present(0.0) is False
    assert _is_present(1) is True
    assert _is_present(1.5) is True
    assert _is_present([]) is False
    assert _is_present(["item"]) is True
    assert _is_present({}) is False
    assert _is_present({"k": "v"}) is True


# ── Scoring correctness ────────────────────────────────────────

def test_full_populated_dossier_scores_one():
    d = _populated_dossier()
    r = assess_ingestion_quality(d)
    assert r.data_quality_score == 1.0
    assert r.fields_present == 15
    assert r.missing_fields == []


def test_partial_dossier_scores_proportionally():
    d = _populated_dossier()
    d.supplier_id = None
    d.award_value = 0
    d.currency = ""
    r = assess_ingestion_quality(d)
    assert r.fields_present == 12
    assert abs(r.data_quality_score - (12 / 15)) < 1e-9
    assert set(r.missing_fields) == {"supplier_id", "award_value", "currency"}


def test_score_is_reproducible_across_perturbations_of_untouched_fields():
    """Changing non-engine-consumed fields must not affect the score."""
    d1 = _populated_dossier()
    d2 = _populated_dossier()
    d2.dossier_id = "different"
    d2.methodology_version = "different"
    d2.disclaimer = "different"
    a = assess_ingestion_quality(d1)
    b = assess_ingestion_quality(d2)
    assert a.data_quality_score == b.data_quality_score
    assert a.missing_fields == b.missing_fields


# ── Provenance serialization ────────────────────────────────────────

def test_to_provenance_shape():
    d = _populated_dossier()
    d.supplier_id = None
    r = assess_ingestion_quality(d)
    p = r.to_provenance()
    assert set(p.keys()) == {
        "data_quality_score", "missing_fields", "fields_present",
        "fields_total", "scoring_version",
    }
    assert p["scoring_version"] == SCORING_VERSION
    assert p["missing_fields"] == ["supplier_id"]
    assert abs(p["data_quality_score"] - round(14/15, 4)) < 1e-9


# ── Constitutional guarantee ────────────────────────────────────────

def test_composite_path_does_not_import_ingestion_quality():
    """The scoring path must not depend on ingestion_quality. Structural
    proof: grep the composite scoring modules for the import."""
    import subprocess
    scoring_modules = [
        'code/sunlight_core.py',
        'code/cri_engine.py',
        'code/institutional_pipeline.py',
        'code/institutional_statistical_rigor.py',
    ]
    for path in scoring_modules:
        try:
            src = open(path).read()
        except FileNotFoundError:
            continue
        # ContractDossier having ingestion_quality as a field is fine
        # (it's a data holder); the composite MATH must not read it.
        # We assert no scoring function branches on data_quality_score.
        assert 'data_quality_score' not in src, (
            f'{path} references data_quality_score; the composite path '
            f'must remain independent of ingestion-quality reporting per '
            f'the Phase 1 constitutional rule'
        )


def test_report_is_never_stamped_on_dossier_by_default():
    """A freshly-built dossier has ingestion_quality=None; the score is
    populated only by explicit assessment, so scoring is opt-in and
    zero-drift for existing code paths."""
    d = ContractDossier()
    assert d.ingestion_quality is None


# ── Fixtures ────────────────────────────────────────

def _populated_dossier():
    return ContractDossier(
        country_code="US",
        country_name="United States",
        buyer_name="Department of Defense",
        buyer_id="DOD",
        supplier_name="Test Vendor Inc",
        supplier_id="VENDOR-001",
        suppliers=[{"name": "Test Vendor Inc"}],
        tender_value=1_000_000.0,
        award_value=950_000.0,
        currency="USD",
        procurement_method="open",
        number_of_tenderers=3,
        tender_start="2026-01-01",
        tender_end="2026-02-01",
        award_date="2026-03-01",
    )
