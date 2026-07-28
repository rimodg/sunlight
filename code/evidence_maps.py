"""
SUNLIGHT Side 5 — Country Evidence Map Loading
=================================================

Loads per-jurisdiction expected-evidence maps from JSON, mirroring
cpd_allocation.load_cpd_profile.

Why these are per-country and not global:
    A 200-bed hospital in a country with a digital land registry, a utility
    connection database and a national health information system leaves
    traces that the same hospital elsewhere physically cannot. Applying one
    global expectation set would generate absence findings in exactly the
    countries with the thinnest registries — which is the failure mode Side 5
    exists to prevent.

    So what SUNLIGHT looks for is a property of the jurisdiction, declared in
    advance, and published through GET /evidence/expected/{outcome_type} so
    an institution can see the expectations BEFORE it submits anything.

File convention:
    data/evidence_maps/{iso2}.json — lowercase ISO 3166-1 alpha-2, matching
    data/cpd_profiles/ exactly, because the same country codes flow through
    both and a second convention would guarantee mismatches.

On the shipped maps:
    ng.json and ua.json are ILLUSTRATIVE. They encode a plausible evidence
    landscape, not a validated one, and loaded profiles carry status
    "illustrative" so nothing downstream can mistake them for country-office
    ground truth. is_validated() is the check to gate operational use on.

    This matters more than it might seem. queryable_classes drives
    corroboration capacity, which decides whether an adverse conclusion is
    available at all. An unvalidated map that overstates a country's
    registries would unlock findings its evidence base cannot support.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from evidence_schema import EvidenceClass


# Status values a map may declare. Anything else is treated as unvalidated.
STATUS_ILLUSTRATIVE = "illustrative"
STATUS_VALIDATED = "validated"


@dataclass
class CountryEvidenceProfile:
    """A jurisdiction's evidence landscape.

    Usable directly as the `profile` argument to EvidencePipeline,
    EvidenceRuleEngine and evidence_gate: Side 5 reads its parameters by
    name through getattr, and every field the rules and gate ask for is
    present here with a conservative default.
    """

    country_code: str
    country_office: str = ""
    status: str = STATUS_ILLUSTRATIVE
    source_note: str = ""
    last_updated: str = ""

    # Which evidence classes are reachable here. Empty means unknown, and
    # reachability is then derived from what the sources actually returned.
    queryable_classes: List[str] = field(default_factory=list)

    # outcome_type value → list of expected-evidence definitions.
    expected_evidence_maps: Dict[str, List[dict]] = field(default_factory=dict)

    # Tunables. Defaults match evidence_rules and evidence_evg.
    min_independent_classes: int = 3
    min_queryable_classes: int = 3
    min_corroboration_capacity: float = 0.5
    timeline_tolerance_days: int = 90
    magnitude_tolerance: float = 0.20
    beneficiary_tolerance: float = 0.25
    field_verification_window_months: int = 6
    evidence_freshness_months: int = 18
    geotag_tolerance_meters: float = 250.0
    evidence_legal_citations: Dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.country_office or self.country_code

    def is_validated(self) -> bool:
        """Whether this map has been confirmed by the country office.

        Gate operational use on this. An illustrative map is a starting point
        for a conversation with a country office, not a basis for telling an
        institution what its evidence should look like.
        """
        return self.status == STATUS_VALIDATED

    def outcome_types_covered(self) -> List[str]:
        return sorted(self.expected_evidence_maps)

    def expectations_for(self, outcome_type: str) -> List[dict]:
        """Raw expectation definitions for one outcome type, or empty.

        Empty is an honest answer: an outcome type this jurisdiction has no
        map for produces no expectations, and therefore no absence findings.
        Guessing would produce fabricated absences.
        """
        return list(self.expected_evidence_maps.get(outcome_type, []))

    def capacity_ceiling(self) -> float:
        """The highest corroboration capacity attainable in this jurisdiction."""
        total = len(EvidenceClass)
        if total == 0:
            return 0.0
        return len(self.valid_queryable_classes()) / total

    def valid_queryable_classes(self) -> List[str]:
        """Declared classes that name a real EvidenceClass.

        Unrecognised entries are dropped rather than raising — a typo should
        not take a country offline — but validate() reports them, because
        silently dropping one lowers capacity and could turn an available
        conclusion into UNVERIFIED without anyone noticing.
        """
        valid = {c.value for c in EvidenceClass}
        return [c for c in self.queryable_classes if c in valid]

    def validate(self) -> List[str]:
        """Return warnings. Same contract as JurisdictionProfile.validate()."""
        warnings: List[str] = []
        valid = {c.value for c in EvidenceClass}

        unknown = [c for c in self.queryable_classes if c not in valid]
        if unknown:
            warnings.append(
                f"queryable_classes contains unrecognised value(s) {unknown}. "
                f"They are ignored, which lowers corroboration capacity and "
                f"may turn an available conclusion into UNVERIFIED."
            )

        for outcome_type, entries in self.expected_evidence_maps.items():
            for i, entry in enumerate(entries):
                cls = entry.get("evidence_class")
                if cls not in valid:
                    warnings.append(
                        f"{outcome_type}[{i}] names unrecognised evidence_class "
                        f"'{cls}'; the expectation will be skipped."
                    )
                elif self.queryable_classes and cls not in self.queryable_classes:
                    warnings.append(
                        f"{outcome_type}[{i}] expects '{cls}', which this "
                        f"jurisdiction does not list as queryable. It will be "
                        f"marked unqueryable and cannot produce an absence finding."
                    )

        if not self.is_validated():
            warnings.append(
                f"status='{self.status}' — this map has not been validated by "
                f"the country office. queryable_classes drives corroboration "
                f"capacity, which decides whether an adverse conclusion is "
                f"available at all."
            )

        return warnings


def _default_map_dir() -> str:
    code_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(code_dir)
    return os.path.join(project_root, "data", "evidence_maps")


def parse_evidence_map(data: dict) -> CountryEvidenceProfile:
    """Build a CountryEvidenceProfile from a loaded JSON document."""
    params = data.get("parameters", {}) or {}
    profile = CountryEvidenceProfile(
        country_code=data.get("country_code", ""),
        country_office=data.get("country_office", ""),
        status=data.get("status", STATUS_ILLUSTRATIVE),
        source_note=data.get("source_note", ""),
        last_updated=data.get("last_updated", ""),
        queryable_classes=list(data.get("queryable_classes", []) or []),
        expected_evidence_maps=dict(data.get("expected_evidence_maps", {}) or {}),
    )

    for key, value in params.items():
        if hasattr(profile, key):
            setattr(profile, key, value)

    return profile


def load_evidence_map(
    country_code: str,
    map_dir: Optional[str] = None,
) -> Optional[CountryEvidenceProfile]:
    """Load a country's evidence map.

    Looks for data/evidence_maps/{country_code}.json, mirroring
    cpd_allocation.load_cpd_profile.

    Args:
        country_code: ISO 3166-1 alpha-2 code, case-insensitive.
        map_dir: optional directory override.

    Returns:
        CountryEvidenceProfile, or None when no map exists for this country.

        None is meaningful and is not an error: it means SUNLIGHT has no
        declared expectations here. Stage 14 then resolves no expectations,
        no absence rule can fire, and the analysis reports what the submitted
        evidence shows without inventing a standard the country never agreed to.
    """
    if map_dir is None:
        map_dir = _default_map_dir()

    filepath = os.path.join(map_dir, f"{country_code.lower()}.json")
    if not os.path.exists(filepath):
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return parse_evidence_map(data)


def available_evidence_maps(map_dir: Optional[str] = None) -> List[str]:
    """Country codes with a shipped evidence map, sorted."""
    if map_dir is None:
        map_dir = _default_map_dir()
    if not os.path.isdir(map_dir):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(map_dir)
        if f.endswith(".json")
    )
