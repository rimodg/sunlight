"""
SUNLIGHT v4 API Input Format Adapter Layer
===========================================

Pluggable ingestion that converts heterogeneous procurement data formats
into canonical OCDS release dict shape for SunlightPipeline.ingest to
consume. Adapters are stateless format translators — they never touch
the analysis engine, never read jurisdiction profiles, and never mutate
the input payload.

This module is distinct from code/ocds_adapter.py, which is a legacy
module serving a separate code path (live_monitor.py, ingest_ocds_live.py)
that transforms OCDS releases into the older SunlightContract schema.
The two modules coexist without interference.

Architecture:
- InputAdapter protocol defines the contract all adapters must implement
- OCDSAdapter is the reference implementation (identity transform with validation)
- QuantumAdapter and CompassAdapter are placeholder stubs with NotImplementedError
- InputAdapterRegistry routes payloads to adapters (explicit or automatic)
- build_default_registry() constructs the production registry instance

Usage in API layer:
    registry = build_default_registry()
    adapter = registry.route(payload)  # Or registry.get("ocds_release")
    canonical_ocds = adapter.to_canonical_ocds(payload)
    dossier = pipeline.ingest(canonical_ocds, ...)
"""

from typing import Protocol, Dict, Any, List
from abc import ABC


class InputAdapter(Protocol):
    """
    Protocol that every input format adapter must implement.

    An adapter converts a source-format payload (a dict in whatever
    shape the source system publishes) into canonical OCDS release
    dict shape that SunlightPipeline.ingest accepts directly. The
    adapter is stateless: the same input always produces the same
    output, and no adapter instance holds per-request state.

    Adapters never touch the analysis engine, never read jurisdiction
    profiles, and never mutate the input payload. They are pure
    format translation and nothing more. All analysis happens
    downstream of the adapter, inside the pipeline.
    """

    format_name: str

    def can_handle(self, payload: Dict[str, Any]) -> bool:
        """
        Return True if this adapter recognizes the payload as its
        source format. Adapters should inspect shape markers (top-level
        keys, version fields, schema identifiers) and return False
        when the shape does not match — never raise.
        """
        ...

    def to_canonical_ocds(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform the source-format payload into a canonical OCDS
        release dict that SunlightPipeline.ingest can consume
        directly. Must return a dict with at least an 'ocid' key
        and the standard OCDS top-level sections (tender, awards,
        parties, etc.) populated from the source payload.

        Raise ValueError with a descriptive message if the payload
        is malformed or missing required fields. Never return
        partially-constructed output — either the full canonical
        shape or an exception.
        """
        ...


class OCDSAdapter:
    """
    Reference adapter for canonical OCDS release payloads. Input
    is already in the target shape, so the adapter is effectively
    an identity transform with input validation.

    Accepts both single OCDS release dicts and OCDS release package
    dicts (which wrap releases under a 'releases' key). Single
    releases pass through unchanged. Release packages return the
    first release in the packaged list.
    """

    format_name = "ocds_release"

    def can_handle(self, payload: Dict[str, Any]) -> bool:
        """Check if payload is an OCDS release or release package."""
        if not isinstance(payload, dict):
            return False
        # Single release has 'ocid' at top level
        if "ocid" in payload:
            return True
        # Release package has 'releases' list
        if "releases" in payload and isinstance(payload["releases"], list):
            return True
        return False

    def to_canonical_ocds(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return the payload unchanged if it's a single release, or extract
        the first release if it's a release package.
        """
        if not isinstance(payload, dict):
            raise ValueError(
                f"OCDSAdapter expected dict payload, got {type(payload).__name__}"
            )

        # Single release: pass through
        if "ocid" in payload:
            return payload

        # Release package: extract first release
        if "releases" in payload:
            releases = payload["releases"]
            if not isinstance(releases, list) or not releases:
                raise ValueError(
                    "OCDSAdapter: 'releases' must be a non-empty list"
                )
            first = releases[0]
            if not isinstance(first, dict) or "ocid" not in first:
                raise ValueError(
                    "OCDSAdapter: first release in package missing 'ocid'"
                )
            return first

        # Unrecognized shape
        raise ValueError(
            "OCDSAdapter: payload is neither an OCDS release nor a release package "
            "(missing 'ocid' and 'releases' keys)"
        )


class QuantumAdapter:
    """
    Placeholder adapter for UNDP Quantum ERP payloads. The Quantum
    procurement data schema is not publicly documented and will be
    provided by UNDP integration teams during institutional
    onboarding. Until then, this adapter raises NotImplementedError
    with a descriptive message pointing to the TODO.md tracking
    entry.

    The class exists in the registry so institutional integration
    teams reading the codebase can see that Quantum is a planned
    extension point, not an oversight.
    """

    format_name = "undp_quantum"

    def can_handle(self, payload: Dict[str, Any]) -> bool:
        """
        Cannot recognize Quantum payloads without the schema.
        Returning False unconditionally means this adapter never
        matches in automatic routing and must be invoked explicitly
        by format_name once the schema is integrated.
        """
        return False

    def to_canonical_ocds(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Raises NotImplementedError with context."""
        raise NotImplementedError(
            "QuantumAdapter is a placeholder. The UNDP Quantum ERP "
            "procurement schema must be integrated before this adapter "
            "can translate Quantum payloads into canonical OCDS shape. "
            "See TODO.md Cluster A4 and the Phase B Jurisprudence Engine "
            "work for the institutional onboarding sequence."
        )


class CompassAdapter:
    """
    Placeholder adapter for UNDP Compass (Global Anti-Corruption Data
    Dashboard) aggregate procurement format payloads. The Compass schema
    is not publicly documented and will be provided by UNDP integration
    teams during institutional onboarding. Until then, this adapter
    raises NotImplementedError with a descriptive message.

    The class exists in the registry so institutional integration
    teams reading the codebase can see that Compass is a planned
    extension point, not an oversight.
    """

    format_name = "undp_compass"

    def can_handle(self, payload: Dict[str, Any]) -> bool:
        """
        Cannot recognize Compass payloads without the schema.
        Returning False unconditionally means this adapter never
        matches in automatic routing and must be invoked explicitly
        by format_name once the schema is integrated.
        """
        return False

    def to_canonical_ocds(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Raises NotImplementedError with context."""
        raise NotImplementedError(
            "CompassAdapter is a placeholder. The UNDP Compass (Global "
            "Anti-Corruption Data Dashboard) procurement schema must be "
            "integrated before this adapter can translate Compass payloads "
            "into canonical OCDS shape. See TODO.md Cluster A4 and the "
            "Phase B Jurisprudence Engine work for the institutional "
            "onboarding sequence."
        )


class InputAdapterRegistry:
    """
    Registry of available input adapters. The API layer instantiates
    one registry at import time and uses it to route incoming payloads
    to the correct adapter.

    Two routing modes:
    - Explicit: the caller names the format via format_name lookup
    - Automatic: the registry iterates registered adapters and picks
      the first one whose can_handle() returns True

    The OCDS adapter is always registered. Quantum and Compass
    adapters are registered as placeholders so their format_names
    appear in the registry listing, but they will not auto-match
    any payload (their can_handle always returns False) and will
    raise NotImplementedError if invoked explicitly.
    """

    def __init__(self):
        self._adapters: List[InputAdapter] = []
        self._by_name: Dict[str, InputAdapter] = {}

    def register(self, adapter: InputAdapter) -> None:
        """
        Register an adapter. Raises ValueError if the format_name
        is already registered.
        """
        if adapter.format_name in self._by_name:
            raise ValueError(
                f"Adapter format_name '{adapter.format_name}' already registered"
            )
        self._adapters.append(adapter)
        self._by_name[adapter.format_name] = adapter

    def get(self, format_name: str) -> InputAdapter:
        """
        Get an adapter by explicit format name. Raises KeyError if
        the format is not registered.
        """
        if format_name not in self._by_name:
            raise KeyError(
                f"No adapter registered for format '{format_name}'. "
                f"Available: {list(self._by_name.keys())}"
            )
        return self._by_name[format_name]

    def list_formats(self) -> List[str]:
        """Return list of all registered format names."""
        return list(self._by_name.keys())

    def route(self, payload: Dict[str, Any]) -> InputAdapter:
        """
        Automatic routing: find the first registered adapter whose
        can_handle() returns True. Raises ValueError if no adapter
        recognizes the payload shape.
        """
        for adapter in self._adapters:
            try:
                if adapter.can_handle(payload):
                    return adapter
            except Exception:
                # Swallow can_handle() exceptions and try next adapter
                continue

        raise ValueError(
            f"No registered adapter recognizes the payload shape. "
            f"Registered formats: {self.list_formats()}"
        )


def build_default_registry() -> InputAdapterRegistry:
    """
    Construct the default adapter registry with OCDS, Quantum, and
    Compass adapters registered. This is the registry the API layer
    uses in production.
    """
    reg = InputAdapterRegistry()
    reg.register(OCDSAdapter())
    reg.register(QuantumAdapter())
    reg.register(CompassAdapter())
    return reg
