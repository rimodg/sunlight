"""
Test fixtures for UNDP integration testing.

These fixtures support adapter development and evidence map validation
testing during institutional onboarding.
"""

import json
from pathlib import Path
from typing import Dict, Any


def get_fixture_path(fixture_name: str) -> Path:
    """Get path to a fixture file."""
    # Fixtures are in /workspace/data/fixtures/undp/, not under tests/
    base_dir = Path(__file__).parent.parent.parent / "data" / "fixtures" / "undp"
    return base_dir / fixture_name


def load_quantum_sample() -> Dict[str, Any]:
    """Load the illustrative Quantum ERP sample."""
    fixture_path = get_fixture_path("quantum_erp_sample.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_compass_sample() -> Dict[str, Any]:
    """Load the illustrative Compass aggregate sample."""
    fixture_path = get_fixture_path("compass_aggregate_sample.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_evidence_map_fixture(country_code: str) -> Dict[str, Any]:
    """Load an evidence map for testing."""
    # Evidence maps are in /workspace/data/evidence_maps/
    fixture_path = Path(__file__).parent.parent.parent / "data" / "evidence_maps" / f"{country_code}.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)
