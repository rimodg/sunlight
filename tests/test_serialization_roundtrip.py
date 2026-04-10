"""
SUNLIGHT Response Model Serialization Roundtrip Tests
======================================================

Roundtrip serialization hardening for every Pydantic response model exposed
by the SUNLIGHT REST API. Tests the byte-level JSON serialization guarantees
that institutional integration code (UNDP, World Bank, etc.) will depend on,
catching failure modes that do not show up in HTTP-layer shape tests:

- Enum casing drift (verdict="CONCERN" vs "concern")
- Datetime timezone loss (aware datetime → naive string → broken)
- None-vs-missing field coercion (null vs absent key in JSON)
- Nested model dict-vs-object bugs (model instance vs raw dict)
- Unicode mojibake (£ or — characters corrupted)

Each test constructs a realistic instance of the model with non-trivial
field values that exercise edge cases, serializes it to JSON via
.model_dump_json(), deserializes it via Model.model_validate_json(...),
and asserts the round-tripped instance equals the original at the field
level. Also verifies the JSON is parseable as a plain dict to prove no
binary garbage leaked into the output.

This complements the existing HTTP integration tests (test_api.py,
test_docker_live.py) which verify response shape but not serialization
correctness. If UNDP's pipeline depends on deserializing our JSON responses
into their own Pydantic models or JSON parsers, these tests prove the
serialization is robust.
"""

import json
import sys
import os
import pytest

# Add code directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from api import (
    ContractInput,
    AnalyzeRequest,
    BatchAnalyzeRequest,
    Contradiction,
    StructuralFindings,
    AnalyzeResponse,
    BatchAnalyzeResponse,
    HealthResponse,
    VersionResponse,
    ProfileListResponse,
    CalibrationStateResponse,
)


# ============================================================================
# Core Response Model Roundtrip Tests (11 tests)
# ============================================================================


def test_roundtrip_ContractInput():
    """ContractInput request model with full OCDS structure."""
    original = ContractInput(
        ocid="ocds-roundtrip-001",
        buyer={"id": "US-DOD", "name": "Department of Defense"},
        tender={
            "title": "Professional Services Contract",
            "value": {"amount": 250000, "currency": "USD"},
            "procurementMethod": "open",
            "numberOfTenderers": 5,
        },
        awards=[{"value": {"amount": 240000, "currency": "USD"}}],
        parties=[
            {"id": "US-DOD", "name": "Department of Defense", "roles": ["buyer"]},
            {"id": "CONTRACTOR-001", "name": "Acme Corp", "roles": ["supplier"]},
        ],
        planning={"budget": {"amount": 300000}},
        contracts=[{"id": "CONTRACT-001", "awardID": "AWARD-001"}],
        language="en",
    )

    json_str = original.model_dump_json()
    restored = ContractInput.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    # Verify JSON is parseable as plain dict
    as_dict = json.loads(json_str)
    assert isinstance(as_dict, dict)
    assert as_dict["ocid"] == "ocds-roundtrip-001"
    assert as_dict["buyer"]["id"] == "US-DOD"
    assert as_dict["tender"]["value"]["amount"] == 250000


def test_roundtrip_AnalyzeRequest():
    """AnalyzeRequest with contract and profile."""
    original = AnalyzeRequest(
        contract=ContractInput(
            ocid="ocds-analyze-req-001",
            buyer={"id": "UK-MOD", "name": "Ministry of Defence"},
            tender={
                "value": {"amount": 500000, "currency": "GBP"},
                "procurementMethod": "selective",
            },
        ),
        profile="uk_central_government",
        include_graph=True,
    )

    json_str = original.model_dump_json()
    restored = AnalyzeRequest.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["profile"] == "uk_central_government"
    assert as_dict["include_graph"] is True


def test_roundtrip_BatchAnalyzeRequest():
    """BatchAnalyzeRequest with multiple contracts and capacity budget."""
    original = BatchAnalyzeRequest(
        contracts=[
            ContractInput(
                ocid=f"ocds-batch-{i}",
                buyer={"id": "US-GSA", "name": "General Services Administration"},
                tender={"value": {"amount": 100000 + i * 50000, "currency": "USD"}},
            )
            for i in range(3)
        ],
        profile="us_federal",
        capacity_budget=50,
    )

    json_str = original.model_dump_json()
    restored = BatchAnalyzeRequest.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert len(as_dict["contracts"]) == 3
    assert as_dict["capacity_budget"] == 50


def test_roundtrip_Contradiction():
    """Contradiction with multiple legal citations and special characters in evidence."""
    original = Contradiction(
        rule_id="PROC-001",
        severity="medium",
        description="Competitive threshold exceeded",
        evidence="value=$250,000 > threshold=$100,000 — flagged per FAR Part 6",
        legal_citations=["FAR Part 6.101", "41 U.S.C. § 3301", "48 CFR 6.302"],
    )

    json_str = original.model_dump_json()
    restored = Contradiction.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["rule_id"] == "PROC-001"
    assert "$" in as_dict["evidence"]
    assert ">" in as_dict["evidence"]
    assert len(as_dict["legal_citations"]) == 3


def test_roundtrip_StructuralFindings():
    """StructuralFindings with lowercase verdict, non-round confidence, contradictions."""
    original = StructuralFindings(
        confidence=0.87,
        verdict="concern",
        contradictions=[
            Contradiction(
                rule_id="TCA-PROC-001",
                severity="high",
                description="Single bidder on high-value contract",
                evidence="numberOfTenderers=1, value=$1,200,000",
                legal_citations=["FAR 6.302-1"],
            ),
            Contradiction(
                rule_id="TCA-PROC-002",
                severity="medium",
                description="Award discount below market floor",
                evidence="discount=20%, market_floor=5%",
                legal_citations=["FAR Part 15"],
            ),
        ],
        feedback_traps=["self_referential_justification"],
    )

    json_str = original.model_dump_json()
    restored = StructuralFindings.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["verdict"] == "concern"
    assert as_dict["confidence"] == 0.87
    assert len(as_dict["contradictions"]) == 2
    assert len(as_dict["feedback_traps"]) == 1


def test_roundtrip_AnalyzeResponse():
    """AnalyzeResponse with gate_verdict=None, non-round processing time, recommended=True."""
    original = AnalyzeResponse(
        ocid="ocds-analyze-resp-001",
        stage="verified_output",
        profile_used="us_federal",
        structure=StructuralFindings(
            confidence=0.92,
            verdict="compromised",
            contradictions=[
                Contradiction(
                    rule_id="TCA-MARKUP-001",
                    severity="critical",
                    description="Markup exceeds prosecution threshold",
                    evidence="markup=450%, threshold=200%",
                    legal_citations=["18 U.S.C. § 287"],
                )
            ],
            feedback_traps=[],
        ),
        gate_verdict=None,
        errors=[],
        processing_time_ms=6.22,
        recommended_for_investigation=True,
    )

    json_str = original.model_dump_json()
    restored = AnalyzeResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["ocid"] == "ocds-analyze-resp-001"
    assert as_dict["gate_verdict"] is None  # Verify None → null → None
    assert as_dict["structure"]["verdict"] == "compromised"
    assert as_dict["recommended_for_investigation"] is True
    assert as_dict["processing_time_ms"] == 6.22


def test_roundtrip_BatchAnalyzeResponse():
    """BatchAnalyzeResponse with multiple results and threshold metadata."""
    original = BatchAnalyzeResponse(
        results=[
            AnalyzeResponse(
                ocid=f"ocds-batch-result-{i}",
                stage="verified_output",
                profile_used="us_federal",
                structure=StructuralFindings(
                    confidence=0.75 + i * 0.05,
                    verdict="concern" if i % 2 == 0 else "sound",
                    contradictions=[],
                    feedback_traps=[],
                ),
                gate_verdict=None,
                errors=[],
                processing_time_ms=4.5 + i * 0.3,
                recommended_for_investigation=(i % 2 == 0),
            )
            for i in range(3)
        ],
        total_processed=3,
        total_errors=0,
        verdict_distribution={"sound": 1, "concern": 2},
        threshold_metadata={
            "statistical_threshold": 2.0,
            "capacity_budget": 50,
            "capacity_threshold": 2.8,
            "binding_threshold": 2.8,
            "recommended_count": 2,
        },
    )

    json_str = original.model_dump_json()
    restored = BatchAnalyzeResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert len(as_dict["results"]) == 3
    assert as_dict["total_processed"] == 3
    assert as_dict["threshold_metadata"]["capacity_budget"] == 50
    assert as_dict["threshold_metadata"]["binding_threshold"] == 2.8


def test_roundtrip_HealthResponse():
    """HealthResponse with ISO timestamp as string."""
    original = HealthResponse(
        status="ok",
        version="0.1.0",
        profiles_available=2,
        timestamp="2026-04-10T13:30:00Z",
    )

    json_str = original.model_dump_json()
    restored = HealthResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["status"] == "ok"
    assert as_dict["timestamp"] == "2026-04-10T13:30:00Z"  # String, not datetime


def test_roundtrip_VersionResponse():
    """VersionResponse with realistic version strings and profile list."""
    original = VersionResponse(
        sunlight_version="0.1.0",
        mjpis_version="draft-v0.1",
        profiles=["us_federal", "uk_central_government"],
        api_version="v1",
    )

    json_str = original.model_dump_json()
    restored = VersionResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["sunlight_version"] == "0.1.0"
    assert len(as_dict["profiles"]) == 2
    assert "us_federal" in as_dict["profiles"]
    assert "uk_central_government" in as_dict["profiles"]


def test_roundtrip_ProfileListResponse():
    """ProfileListResponse with multiple profile dicts."""
    original = ProfileListResponse(
        profiles=[
            {
                "name": "us_federal",
                "country_code": "US",
                "currency": "USD",
                "fiscal_year_end": "09-30",
                "description": "United States federal government procurement",
            },
            {
                "name": "uk_central_government",
                "country_code": "GB",
                "currency": "GBP",
                "fiscal_year_end": "03-31",
                "description": "United Kingdom central government procurement",
            },
        ]
    )

    json_str = original.model_dump_json()
    restored = ProfileListResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert len(as_dict["profiles"]) == 2
    assert as_dict["profiles"][0]["name"] == "us_federal"
    assert as_dict["profiles"][1]["currency"] == "GBP"


def test_roundtrip_CalibrationStateResponse():
    """CalibrationStateResponse with populated verdict/rule counts and statistics."""
    original = CalibrationStateResponse(
        profile_name="us_federal",
        total_contracts_analyzed=150,
        verdict_counts={"sound": 100, "concern": 35, "compromised": 15},
        rule_fire_counts={"TCA-PROC-001": 45, "TCA-MARKUP-001": 20},
        mean_risk_score=1.87,
        variance_risk_score=0.42,
        risk_score_min=0.05,
        risk_score_max=4.95,
        first_observation_utc="2026-04-01T12:00:00Z",
        last_observation_utc="2026-04-10T14:30:00Z",
        schema_version="1.0",
    )

    json_str = original.model_dump_json()
    restored = CalibrationStateResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["profile_name"] == "us_federal"
    assert as_dict["total_contracts_analyzed"] == 150
    assert as_dict["verdict_counts"]["sound"] == 100
    assert as_dict["rule_fire_counts"]["TCA-PROC-001"] == 45
    assert as_dict["mean_risk_score"] == 1.87
    assert as_dict["first_observation_utc"] == "2026-04-01T12:00:00Z"


# ============================================================================
# Edge Case Roundtrip Tests (4 tests)
# ============================================================================


def test_AnalyzeResponse_roundtrip_with_empty_contradictions():
    """Verify empty contradictions list survives as [] not null or missing."""
    original = AnalyzeResponse(
        ocid="ocds-empty-contradictions-001",
        stage="verified_output",
        profile_used="us_federal",
        structure=StructuralFindings(
            confidence=0.95,
            verdict="sound",
            contradictions=[],
            feedback_traps=[],
        ),
        gate_verdict=None,
        errors=[],
        processing_time_ms=3.14,
        recommended_for_investigation=False,
    )

    json_str = original.model_dump_json()
    restored = AnalyzeResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["structure"]["contradictions"] == []  # Empty list, not null
    assert isinstance(as_dict["structure"]["contradictions"], list)


def test_BatchAnalyzeResponse_roundtrip_with_capacity_threshold_none():
    """Verify capacity_threshold=None survives as JSON null and deserializes to Python None."""
    original = BatchAnalyzeResponse(
        results=[
            AnalyzeResponse(
                ocid="ocds-no-capacity-001",
                stage="verified_output",
                profile_used="us_federal",
                structure=StructuralFindings(
                    confidence=0.80,
                    verdict="concern",
                    contradictions=[],
                    feedback_traps=[],
                ),
                gate_verdict=None,
                errors=[],
                processing_time_ms=5.0,
                recommended_for_investigation=True,
            )
        ],
        total_processed=1,
        total_errors=0,
        verdict_distribution={"concern": 1},
        threshold_metadata={
            "statistical_threshold": 2.0,
            "capacity_budget": None,  # No capacity specified
            "capacity_threshold": None,  # Should be null in JSON
            "binding_threshold": 2.0,
            "recommended_count": 1,
        },
    )

    json_str = original.model_dump_json()
    restored = BatchAnalyzeResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["threshold_metadata"]["capacity_budget"] is None  # JSON null
    assert as_dict["threshold_metadata"]["capacity_threshold"] is None  # JSON null


def test_CalibrationStateResponse_roundtrip_zero_state():
    """Verify freshly-initialized state with all None fields round-trips correctly."""
    original = CalibrationStateResponse(
        profile_name="uk_central_government",
        total_contracts_analyzed=0,
        verdict_counts={},
        rule_fire_counts={},
        mean_risk_score=None,
        variance_risk_score=None,
        risk_score_min=None,
        risk_score_max=None,
        first_observation_utc=None,
        last_observation_utc=None,
        schema_version="1.0",
    )

    json_str = original.model_dump_json()
    restored = CalibrationStateResponse.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert as_dict["total_contracts_analyzed"] == 0
    assert as_dict["verdict_counts"] == {}
    assert as_dict["rule_fire_counts"] == {}
    assert as_dict["mean_risk_score"] is None  # JSON null, not "None" string
    assert as_dict["variance_risk_score"] is None
    assert as_dict["risk_score_min"] is None
    assert as_dict["risk_score_max"] is None
    assert as_dict["first_observation_utc"] is None
    assert as_dict["last_observation_utc"] is None


def test_Contradiction_roundtrip_with_unicode_evidence():
    """Verify unicode characters in evidence survive encoding/decoding without mojibake."""
    original = Contradiction(
        rule_id="TCA-UK-001",
        severity="high",
        description="Threshold exceeded — procurement rules violated",
        evidence="£214,000 threshold exceeded per UK regulation — flagged",
        legal_citations=["Public Contracts Regulations 2015"],
    )

    json_str = original.model_dump_json()
    restored = Contradiction.model_validate_json(json_str)
    assert restored == original, f"roundtrip mismatch: {restored} != {original}"

    as_dict = json.loads(json_str)
    assert "£" in as_dict["evidence"]  # Pound sign survived
    assert "—" in as_dict["evidence"]  # Em dash survived
    assert "—" in as_dict["description"]
    # Verify no mojibake (£ should not become Â£ or similar)
    assert as_dict["evidence"] == "£214,000 threshold exceeded per UK regulation — flagged"
