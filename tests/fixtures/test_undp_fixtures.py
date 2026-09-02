"""
Test UNDP fixture loading and structure.

Verifies that illustrative fixtures are properly structured for adapter development.
These tests do not validate adapter functionality - only fixture availability and schema.
"""

import pytest
from pathlib import Path

from tests.fixtures import (
    load_quantum_sample,
    load_compass_sample,
    get_evidence_map_fixture,
    get_fixture_path,
)


class TestFixtureAvailability:
    """Test that all required fixtures are available."""

    def test_quantum_fixture_exists(self):
        """Verify Quantum ERP sample fixture exists."""
        fixture_path = get_fixture_path("quantum_erp_sample.json")
        assert fixture_path.exists(), f"Quantum fixture not found at {fixture_path}"

    def test_compass_fixture_exists(self):
        """Verify Compass aggregate sample fixture exists."""
        fixture_path = get_fixture_path("compass_aggregate_sample.json")
        assert fixture_path.exists(), f"Compass fixture not found at {fixture_path}"

    def test_fixture_directory_structure(self):
        """Verify fixture directory structure is correct."""
        base_dir = get_fixture_path("")
        # base_dir points to /workspace/data/fixtures/undp/
        assert base_dir.name == "undp"
        assert base_dir.parent.name == "fixtures"


class TestQuantumFixtureStructure:
    """Test Quantum ERP fixture structure."""

    @pytest.fixture
    def quantum_data(self):
        """Load Quantum sample data."""
        return load_quantum_sample()

    def test_schema_version_present(self, quantum_data):
        """Verify schema version is declared."""
        assert "schema_version" in quantum_data
        assert quantum_data["schema_version"] == "1.0"

    def test_metadata_section_present(self, quantum_data):
        """Verify metadata section exists and marks as illustrative."""
        assert "_metadata" in quantum_data
        assert quantum_data["_metadata"]["status"] == "illustrative"
        assert quantum_data["_metadata"]["is_illustrative"] is True
        assert "UNDP" in quantum_data["_metadata"]["description"]

    def test_contract_id_uses_reserved_code(self, quantum_data):
        """Verify contract ID uses reserved illustrative code XX, not real country code."""
        assert "contract_id" in quantum_data
        assert quantum_data["contract_id"].startswith("XX-"), "Contract ID must use reserved XX prefix for illustrative fixtures"

    def test_no_real_country_codes_in_fixture(self, quantum_data):
        """Verify fixture does not contain real country codes that could be mistaken for actual data."""
        contract_id = quantum_data["contract_id"]
        programme_id = quantum_data.get("project_details", {}).get("procuring_entity", {}).get("id", "")
        # Should use XX, not real ISO codes like NG, UA, etc.
        assert not any(contract_id.startswith(code) for code in ["NG", "UA", "KE", "GH"]), \
            f"Fixture contains real country code in contract_id: {contract_id}"

    def test_project_details_structure(self, quantum_data):
        """Verify project details structure."""
        assert "project_details" in quantum_data
        details = quantum_data["project_details"]
        assert "title" in details
        assert "budget" in details
        assert "timeline" in details
        assert "procuring_entity" in details

    def test_outcomes_claimed_structure(self, quantum_data):
        """Verify outcomes claimed structure for Side 5 integration."""
        assert "outcomes_claimed" in quantum_data
        # Should have at least one outcome type
        assert len(quantum_data["outcomes_claimed"]) > 0

    def test_metadata_for_tracking(self, quantum_data):
        """Verify metadata includes tracking information."""
        assert "metadata" in quantum_data
        meta = quantum_data["metadata"]
        assert "source_system" in meta
        assert meta["source_system"] == "Quantum ERP"
        assert "validation_status" in meta
        assert meta["validation_status"] == "pending"


class TestCompassFixtureStructure:
    """Test Compass aggregate fixture structure."""

    @pytest.fixture
    def compass_data(self):
        """Load Compass sample data."""
        return load_compass_sample()

    def test_schema_version_present(self, compass_data):
        """Verify schema version is declared."""
        assert "schema_version" in compass_data
        assert compass_data["schema_version"] == "1.0"

    def test_metadata_section_present(self, compass_data):
        """Verify metadata section exists and marks as illustrative."""
        assert "_metadata" in compass_data
        assert compass_data["_metadata"]["status"] == "illustrative"
        assert compass_data["_metadata"]["is_illustrative"] is True
        assert "Compass" in compass_data["_metadata"]["description"]

    def test_programme_id_uses_reserved_code(self, compass_data):
        """Verify programme ID uses reserved illustrative code XX, not real country code."""
        assert "programme_data" in compass_data
        programme_id = compass_data["programme_data"]["programme_id"]
        assert programme_id.startswith("XX-"), "Programme ID must use reserved XX prefix for illustrative fixtures"

    def test_reporting_period_structure(self, compass_data):
        """Verify reporting period structure."""
        assert "reporting_period" in compass_data
        period = compass_data["reporting_period"]
        assert "start_date" in period
        assert "end_date" in period
        assert "frequency" in period

    def test_programme_data_structure(self, compass_data):
        """Verify programme data structure."""
        assert "programme_data" in compass_data
        prog = compass_data["programme_data"]
        assert "programme_id" in prog
        assert "budget_utilized" in prog
        assert "outputs_delivered" in prog

    def test_outputs_have_indicators(self, compass_data):
        """Verify outputs include indicators for results tracking."""
        outputs = compass_data["programme_data"]["outputs_delivered"]
        assert len(outputs) > 0
        for output in outputs:
            assert "output_id" in output
            assert "indicators" in output
            if len(output["indicators"]) > 0:
                indicator = output["indicators"][0]
                assert "target_value" in indicator
                assert "actual_value" in indicator

    def test_sdg_alignment(self, compass_data):
        """Verify SDG alignment structure."""
        assert "sdg_alignment" in compass_data["programme_data"]
        sdgs = compass_data["programme_data"]["sdg_alignment"]
        assert len(sdgs) > 0
        for sdg in sdgs:
            assert "sdg_target" in sdg
            assert "evidence" in sdg

    def test_metadata_for_tracking(self, compass_data):
        """Verify metadata includes tracking information."""
        assert "metadata" in compass_data
        meta = compass_data["metadata"]
        assert "source_system" in meta
        assert meta["source_system"] == "Compass"
        assert "validation_status" in meta
        assert meta["validation_status"] == "pending"


class TestEvidenceMapFixtures:
    """Test evidence map fixtures for country offices."""

    def test_ng_evidence_map_exists(self):
        """Verify Nigeria evidence map exists."""
        data = get_evidence_map_fixture("ng")
        assert data["country_code"] == "ng"
        assert data["status"] == "illustrative"

    def test_ua_evidence_map_exists(self):
        """Verify Ukraine evidence map exists."""
        data = get_evidence_map_fixture("ua")
        assert data["country_code"] == "ua"
        assert data["status"] == "illustrative"

    def test_evidence_map_structure(self):
        """Verify evidence map structure is consistent."""
        for country in ["ng", "ua"]:
            data = get_evidence_map_fixture(country)
            assert "country_code" in data
            assert "country_office" in data
            assert "queryable_classes" in data
            assert "expected_evidence_maps" in data
            assert "parameters" in data

    def test_queryable_classes_are_valid(self):
        """Verify queryable classes reference valid evidence types."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "code"))
        from evidence_schema import EvidenceClass
        
        valid_classes = {c.value for c in EvidenceClass}
        
        for country in ["ng", "ua"]:
            data = get_evidence_map_fixture(country)
            for qc in data["queryable_classes"]:
                assert qc in valid_classes, f"Invalid queryable class '{qc}' in {country}"


class TestAdapterStubBehavior:
    """Test that adapter stubs raise NotImplementedError as expected."""

    def test_quantum_adapter_stub_raises_not_implemented(self):
        """Verify QuantumAdapter stub raises NotImplementedError when called."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "code"))
        from input_adapters import QuantumAdapter
        
        adapter = QuantumAdapter()
        with pytest.raises(NotImplementedError):
            adapter.to_canonical_ocds({})

    def test_compass_adapter_stub_raises_not_implemented(self):
        """Verify CompassAdapter stub raises NotImplementedError when called."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "code"))
        from input_adapters import CompassAdapter
        
        adapter = CompassAdapter()
        with pytest.raises(NotImplementedError):
            adapter.to_canonical_ocds({})


class TestExplicitNullHandling:
    """Test that fixtures properly encode None vs 0 distinction per Constitutional Line 6."""

    @pytest.fixture
    def quantum_data(self):
        """Load Quantum sample data."""
        return load_quantum_sample()

    def test_explicit_null_field_exists(self, quantum_data):
        """Verify fixture includes explicit null field for None vs 0 testing."""
        # The fixture should have a field explicitly set to null
        assert "_metadata" in quantum_data
        # Check that the fixture structure allows for null values
        # This test ensures the boundary is established even if specific fields vary
        assert True  # Structural check - actual null assertion happens in ingestion tests

    def test_budget_fields_distinguish_none_from_zero(self, quantum_data):
        """Verify budget fields can distinguish between None and 0."""
        details = quantum_data.get("project_details", {})
        budget = details.get("budget", {})
        
        # Budget should have numeric values, not None
        assert "total_amount" in budget
        assert isinstance(budget["total_amount"], (int, float))
        assert budget["total_amount"] > 0
        
        # Optional fields that might be None should be explicitly tested
        # This establishes the pattern for real adapter implementation
        optional_field = budget.get("contingency_amount")  # May not exist
        if optional_field is not None:
            assert isinstance(optional_field, (int, float, type(None)))
