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
        assert base_dir.parent.name == "undp"
        assert base_dir.parent.parent.name == "fixtures"


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
        assert "UNDP" in quantum_data["_metadata"]["description"]

    def test_contract_id_present(self, quantum_data):
        """Verify contract identifier is present."""
        assert "contract_id" in quantum_data
        assert quantum_data["contract_id"].startswith("NG-")

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
        assert "Compass" in compass_data["_metadata"]["description"]

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
        from code.evidence_schema import EvidenceClass
        
        valid_classes = {c.value for c in EvidenceClass}
        
        for country in ["ng", "ua"]:
            data = get_evidence_map_fixture(country)
            for qc in data["queryable_classes"]:
                assert qc in valid_classes, f"Invalid queryable class '{qc}' in {country}"
