"""
Unit and integration tests for the input format adapter layer.

Tests the pluggable ingestion architecture that converts heterogeneous
procurement data formats into canonical OCDS release dict shape. Covers:

- OCDSAdapter reference implementation (identity transform with validation)
- QuantumAdapter and CompassAdapter placeholder stubs
- InputAdapterRegistry routing (explicit and automatic)
- End-to-end integration with POST /analyze endpoint

The adapter layer must preserve backward compatibility for existing OCDS
payloads while enabling future extension to UNDP institutional formats.
"""

import os
import sys
import pytest
from typing import Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from input_adapters import (
    OCDSAdapter,
    QuantumAdapter,
    CompassAdapter,
    InputAdapterRegistry,
    build_default_registry,
)


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_ocds_release() -> Dict[str, Any]:
    """Minimal valid OCDS release (single release, not a package)."""
    return {
        "ocid": "ocds-test-001",
        "tender": {"id": "TND-001", "value": {"amount": 100000, "currency": "USD"}},
        "parties": [],
        "awards": [],
    }


@pytest.fixture
def sample_ocds_package() -> Dict[str, Any]:
    """OCDS release package wrapping multiple releases."""
    return {
        "uri": "https://example.com/releases/001",
        "publishedDate": "2024-01-01T00:00:00Z",
        "releases": [
            {
                "ocid": "ocds-package-001",
                "tender": {"id": "TND-PKG-001", "value": {"amount": 50000, "currency": "EUR"}},
                "parties": [],
                "awards": [],
            },
            {
                "ocid": "ocds-package-002",
                "tender": {"id": "TND-PKG-002", "value": {"amount": 75000, "currency": "EUR"}},
                "parties": [],
                "awards": [],
            }
        ]
    }


@pytest.fixture
def unrecognized_payload() -> Dict[str, Any]:
    """Payload that no registered adapter should recognize."""
    return {
        "id": "UNKNOWN-001",
        "data": {"foo": "bar"},
        "format": "proprietary_erp_v3"
    }


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS — OCDSAdapter
# ═══════════════════════════════════════════════════════════════════════════


def test_ocds_adapter_can_handle_single_release(sample_ocds_release):
    """OCDSAdapter.can_handle returns True for single OCDS release."""
    adapter = OCDSAdapter()
    assert adapter.can_handle(sample_ocds_release) is True


def test_ocds_adapter_can_handle_release_package(sample_ocds_package):
    """OCDSAdapter.can_handle returns True for OCDS release package."""
    adapter = OCDSAdapter()
    assert adapter.can_handle(sample_ocds_package) is True


def test_ocds_adapter_to_canonical_single_release(sample_ocds_release):
    """OCDSAdapter.to_canonical_ocds is identity transform for single release."""
    adapter = OCDSAdapter()
    canonical = adapter.to_canonical_ocds(sample_ocds_release)

    # Identity transform: input == output
    assert canonical == sample_ocds_release
    assert canonical["ocid"] == "ocds-test-001"


def test_ocds_adapter_to_canonical_release_package(sample_ocds_package):
    """OCDSAdapter.to_canonical_ocds extracts first release from package."""
    adapter = OCDSAdapter()
    canonical = adapter.to_canonical_ocds(sample_ocds_package)

    # Should extract first release from package
    assert canonical["ocid"] == "ocds-package-001"
    assert canonical["tender"]["id"] == "TND-PKG-001"
    assert "releases" not in canonical  # Package wrapper stripped


def test_ocds_adapter_rejects_malformed_package():
    """OCDSAdapter raises ValueError on malformed release package."""
    adapter = OCDSAdapter()

    # Empty releases list
    with pytest.raises(ValueError, match="non-empty list"):
        adapter.to_canonical_ocds({"releases": []})

    # Releases not a list
    with pytest.raises(ValueError, match="non-empty list"):
        adapter.to_canonical_ocds({"releases": "not-a-list"})

    # First release missing ocid
    with pytest.raises(ValueError, match="missing 'ocid'"):
        adapter.to_canonical_ocds({"releases": [{"tender": {}}]})


def test_ocds_adapter_rejects_unrecognized_shape():
    """OCDSAdapter raises ValueError on unrecognized payload shape."""
    adapter = OCDSAdapter()

    with pytest.raises(ValueError, match="neither an OCDS release nor a release package"):
        adapter.to_canonical_ocds({"id": "unknown", "data": {}})


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS — Placeholder Adapters
# ═══════════════════════════════════════════════════════════════════════════


def test_quantum_adapter_can_handle_returns_false(sample_ocds_release, unrecognized_payload):
    """QuantumAdapter.can_handle always returns False (no schema integrated)."""
    adapter = QuantumAdapter()

    assert adapter.can_handle(sample_ocds_release) is False
    assert adapter.can_handle(unrecognized_payload) is False
    assert adapter.can_handle({}) is False


def test_quantum_adapter_to_canonical_raises_not_implemented():
    """QuantumAdapter.to_canonical_ocds raises NotImplementedError with context."""
    adapter = QuantumAdapter()

    with pytest.raises(NotImplementedError, match="QuantumAdapter is a placeholder"):
        adapter.to_canonical_ocds({"data": "anything"})


def test_compass_adapter_can_handle_returns_false(sample_ocds_release, unrecognized_payload):
    """CompassAdapter.can_handle always returns False (no schema integrated)."""
    adapter = CompassAdapter()

    assert adapter.can_handle(sample_ocds_release) is False
    assert adapter.can_handle(unrecognized_payload) is False
    assert adapter.can_handle({}) is False


def test_compass_adapter_to_canonical_raises_not_implemented():
    """CompassAdapter.to_canonical_ocds raises NotImplementedError with context."""
    adapter = CompassAdapter()

    with pytest.raises(NotImplementedError, match="CompassAdapter is a placeholder"):
        adapter.to_canonical_ocds({"data": "anything"})


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS — InputAdapterRegistry
# ═══════════════════════════════════════════════════════════════════════════


def test_registry_explicit_get_by_name():
    """Registry.get returns registered adapter by exact format name."""
    registry = build_default_registry()

    ocds_adapter = registry.get("ocds_release")
    assert ocds_adapter.format_name == "ocds_release"
    assert isinstance(ocds_adapter, OCDSAdapter)

    quantum_adapter = registry.get("undp_quantum")
    assert quantum_adapter.format_name == "undp_quantum"
    assert isinstance(quantum_adapter, QuantumAdapter)


def test_registry_get_raises_on_unknown_format():
    """Registry.get raises KeyError on unregistered format name."""
    registry = build_default_registry()

    with pytest.raises(KeyError, match="No adapter registered for format 'unknown_format'"):
        registry.get("unknown_format")


def test_registry_list_formats():
    """Registry.list_formats returns all registered format names."""
    registry = build_default_registry()
    formats = registry.list_formats()

    assert "ocds_release" in formats
    assert "undp_quantum" in formats
    assert "undp_compass" in formats
    assert len(formats) == 3


def test_registry_automatic_routing_single_release(sample_ocds_release):
    """Registry.route auto-detects OCDS single release and returns OCDSAdapter."""
    registry = build_default_registry()
    adapter = registry.route(sample_ocds_release)

    assert adapter.format_name == "ocds_release"
    assert isinstance(adapter, OCDSAdapter)


def test_registry_automatic_routing_release_package(sample_ocds_package):
    """Registry.route auto-detects OCDS release package and returns OCDSAdapter."""
    registry = build_default_registry()
    adapter = registry.route(sample_ocds_package)

    assert adapter.format_name == "ocds_release"
    assert isinstance(adapter, OCDSAdapter)


def test_registry_route_raises_on_unrecognized_payload(unrecognized_payload):
    """Registry.route raises ValueError when no adapter recognizes the payload."""
    registry = build_default_registry()

    with pytest.raises(ValueError, match="No registered adapter recognizes the payload shape"):
        registry.route(unrecognized_payload)


def test_registry_rejects_duplicate_registration():
    """Registry.register raises ValueError on duplicate format_name."""
    registry = InputAdapterRegistry()
    registry.register(OCDSAdapter())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(OCDSAdapter())


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TEST — API Layer
# ═══════════════════════════════════════════════════════════════════════════


def test_api_analyze_endpoint_with_ocds_payload():
    """
    Integration test: POST /analyze accepts OCDS payload and routes through
    adapter layer cleanly, preserving backward compatibility.

    This test verifies that the wiring in code/api.py correctly:
    1. Routes the payload through the adapter registry
    2. Transforms to canonical OCDS (identity for OCDS input)
    3. Passes to pipeline.ingest without error
    4. Returns valid analysis response
    """
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.app)

    # Minimal OCDS release payload
    payload = {
        "contract": {
            "ocid": "ocds-integration-test-001",
            "tender": {
                "id": "TND-INT-001",
                "value": {"amount": 150000, "currency": "USD"},
                "procurementMethod": "open",
            },
            "parties": [
                {
                    "id": "ORG-001",
                    "name": "Test Buyer",
                    "roles": ["buyer"]
                }
            ],
            "awards": [],
        },
        "profile": "us_federal",
        "include_graph": False,
        # input_format omitted → automatic routing
    }

    response = client.post("/analyze", json=payload)

    # Should succeed
    assert response.status_code == 200
    result = response.json()

    # Verify structure
    assert result["ocid"] == "ocds-integration-test-001"
    assert result["profile_used"] == "us_federal"
    assert "structure" in result
    assert "processing_time_ms" in result
    assert isinstance(result["processing_time_ms"], (int, float))


def test_api_analyze_endpoint_with_explicit_format():
    """
    Integration test: POST /analyze with explicit input_format field routes
    to the named adapter.
    """
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.app)

    payload = {
        "contract": {
            "ocid": "ocds-explicit-format-test",
            "tender": {"value": {"amount": 100000, "currency": "USD"}},
            "parties": [],
            "awards": [],
        },
        "profile": "us_federal",
        "input_format": "ocds_release",  # Explicit adapter selection
    }

    response = client.post("/analyze", json=payload)

    assert response.status_code == 200
    result = response.json()
    assert result["ocid"] == "ocds-explicit-format-test"


def test_api_analyze_endpoint_rejects_unknown_format():
    """
    Integration test: POST /analyze with unknown input_format raises 400.
    """
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.app)

    payload = {
        "contract": {
            "ocid": "ocds-unknown-format-test",
            "tender": {"value": {"amount": 100000, "currency": "USD"}},
            "parties": [],
            "awards": [],
        },
        "profile": "us_federal",
        "input_format": "unknown_erp_format",
    }

    response = client.post("/analyze", json=payload)

    assert response.status_code == 400
    assert "Input format adapter error" in response.json()["detail"]


def test_api_list_input_formats_endpoint():
    """
    Integration test: GET /input-formats returns list of registered adapters.
    """
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.app)

    response = client.get("/input-formats")

    assert response.status_code == 200
    result = response.json()

    assert "available_formats" in result
    formats = result["available_formats"]
    assert "ocds_release" in formats
    assert "undp_quantum" in formats
    assert "undp_compass" in formats
    assert len(formats) == 3
