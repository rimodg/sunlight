"""
Tests for SUNLIGHT Side 5 — Corroboration Graph Construction.

Covers spec tests 8-11 (independence collapse) plus the graph contract.

    Independence collapse — the centre of the module:
        8.  Two artifacts from the same party collapse to one corroboration
        9.  Linked parties (prime + subcontractor) collapse to one
        10. Genuinely independent sources count separately
        11. Contract parties excluded from the independent count

    Union-find properties:
        - Transitive: prime → sub → sub-sub is ONE group, not two
        - Symmetric: a one-sided declaration still collapses both
        - Deterministic: submission order cannot change the grouping

    Graph structure:
        - Node and edge vocabularies are typed and complete
        - UNQUERYABLE nodes carry NO edge to the claim
        - STALE evidence carries no SATISFIES edge
        - Absence edges run expectation → absence
        - Nothing is dropped silently: unattributed artifacts are counted

The tests that matter most here are the ones asserting what does NOT happen:
an unqueryable source must not connect to the claim, and stale evidence must
not corroborate. Both are ways a false claim could otherwise buy support.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evidence_graph import (
    BASE_EDGE_MARKER,
    EvidenceEdgeType,
    EvidenceGraphBuilder,
    EvidenceNodeType,
    IndependenceResolver,
    count_independent_corroborations,
    derive_queryable_classes,
)
from evidence_schema import (
    CorroborationDossier,
    EvidenceArtifact,
    EvidenceClass,
    EvidenceStatus,
    ExpectedEvidence,
    OutcomeClaim,
    OutcomeType,
    SourceIndependence,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def make_claim():
    return OutcomeClaim(
        claim_id="CLAIM-001",
        contract_id="CONTRACT-001",
        outcome_type=OutcomeType.FACILITY_CONSTRUCTION,
        claim_description="200-bed hospital operational",
        claimed_completion_date=date(2025, 3, 1),
        claimed_magnitude=200.0,
        claimed_magnitude_unit="beds",
        site_latitude=9.0765,
        site_longitude=7.3986,
        country_code="ng",
        award_date=date(2024, 1, 1),
    )


def artifact(aid, evidence_class, status=EvidenceStatus.OBSERVED, party=None, desc=None):
    return EvidenceArtifact(
        artifact_id=aid,
        evidence_class=evidence_class,
        claim_id="CLAIM-001",
        description=desc or f"artifact {aid}",
        status=status,
        source_party_id=party,
    )


def source(pid, name=None, ptype="government_agency", linked=None, contract_party=False):
    return SourceIndependence(
        party_id=pid,
        party_name=name or f"Party {pid}",
        party_type=ptype,
        linked_parties=linked or [],
        is_contract_party=contract_party,
    )


def expectation(eid, evidence_class, required=True, queryable=True):
    return ExpectedEvidence(
        expectation_id=eid,
        evidence_class=evidence_class,
        description=f"expected {eid}",
        required=required,
        queryable_in_jurisdiction=queryable,
    )


def build(dossier):
    b = EvidenceGraphBuilder()
    b.build_graph(dossier)
    return b.last_report


# ═══════════════════════════════════════════════════════════
# SECTION 1: INDEPENDENCE COLLAPSE  (spec tests 8-11)
# ═══════════════════════════════════════════════════════════


class TestIndependenceCollapse:

    def test_same_party_collapses_to_one(self):
        """Spec test 8.

        Two artifacts from one implementing partner, in two different evidence
        classes. Without collapse this reads as two independent corroborations;
        it is one party vouching twice.
        """
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.INSTITUTIONAL, party="P1"),
                artifact("A2", EvidenceClass.ADVERSARIAL_OPEN, party="P1"),
            ],
            source_registry=[source("P1", "Implementing Partner", "implementing_partner")],
        )
        independent, distinct_classes, _ = count_independent_corroborations(d)
        assert independent == 1
        # The class diagnostic still shows two — which is exactly why the
        # gate uses the collapsed number and not this one.
        assert distinct_classes == 2

    def test_linked_prime_and_subcontractor_collapse_to_one(self):
        """Spec test 9 — a prime and its subcontractor are one source."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.INSTITUTIONAL, party="PRIME"),
                artifact("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="SUB"),
            ],
            source_registry=[
                source("PRIME", "Prime Contractor", "commercial_provider", linked=["SUB"]),
                source("SUB", "Subcontractor", "commercial_provider"),
            ],
        )
        independent, _, _ = count_independent_corroborations(d)
        assert independent == 1

    def test_genuinely_independent_sources_count_separately(self):
        """Spec test 10 — three unrelated parties are three corroborations."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="UTILITY"),
                artifact("A2", EvidenceClass.GEOSPATIAL, party="IMAGERY"),
                artifact("A3", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS"),
            ],
            source_registry=[
                source("UTILITY", "National Electricity Authority"),
                source("IMAGERY", "Satellite Provider", "commercial_provider"),
                source("HEALTH_MIS", "Health Information System"),
            ],
        )
        independent, distinct_classes, _ = count_independent_corroborations(d)
        assert independent == 3
        assert distinct_classes == 3

    def test_contract_parties_excluded(self):
        """Spec test 11 — self-attestation is not corroboration.

        The implementing partner's own report does not count. Only the two
        outside parties do.
        """
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                artifact("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="UTILITY"),
                artifact("A3", EvidenceClass.GEOSPATIAL, party="IMAGERY"),
            ],
            source_registry=[
                source("IP", "Implementing Partner", "implementing_partner", contract_party=True),
                source("UTILITY", "National Electricity Authority"),
                source("IMAGERY", "Satellite Provider", "commercial_provider"),
            ],
        )
        independent, _, _ = count_independent_corroborations(d)
        assert independent == 2

    def test_contract_party_status_propagates_through_linkage(self):
        """A subcontractor of the implementing partner is not an outside witness.

        This is the loophole that would otherwise reopen test 11: route the
        self-attestation through a nominally separate entity and it counts again.
        """
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[artifact("A1", EvidenceClass.INSTITUTIONAL, party="SUB")],
            source_registry=[
                source("IP", "Implementing Partner", "implementing_partner",
                       linked=["SUB"], contract_party=True),
                source("SUB", "Their Subcontractor", "commercial_provider"),
            ],
        )
        independent, _, _ = count_independent_corroborations(d)
        assert independent == 0

    def test_only_observed_artifacts_corroborate(self):
        """Absent, contradictory, unqueryable and stale evidence do not vouch."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.INSTITUTIONAL, EvidenceStatus.ABSENT, "P1"),
                artifact("A2", EvidenceClass.GEOSPATIAL, EvidenceStatus.CONTRADICTORY, "P2"),
                artifact("A3", EvidenceClass.BENEFICIARY_SIDE, EvidenceStatus.UNQUERYABLE, "P3"),
                artifact("A4", EvidenceClass.ADVERSARIAL_OPEN, EvidenceStatus.STALE, "P4"),
            ],
            source_registry=[source(f"P{i}") for i in range(1, 5)],
        )
        independent, _, _ = count_independent_corroborations(d)
        assert independent == 0

    def test_unattributed_artifacts_are_surfaced_not_dropped(self):
        """An artifact with no named source vouches for nothing — but the fact
        that one was submitted must be visible, not silently discarded."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.INSTITUTIONAL, party=None),
                artifact("A2", EvidenceClass.GEOSPATIAL, party="IMAGERY"),
            ],
            source_registry=[source("IMAGERY")],
        )
        independent, _, unattributed = count_independent_corroborations(d)
        assert independent == 1
        assert unattributed == 1

    def test_unregistered_party_still_counts(self):
        """A named party with no independence metadata is a real party. We know
        who it is; we simply have no linkage data for it."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[artifact("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="UNKNOWN_REGISTRY")],
            source_registry=[],
        )
        independent, _, _ = count_independent_corroborations(d)
        assert independent == 1


# ═══════════════════════════════════════════════════════════
# SECTION 2: UNION-FIND PROPERTIES
# ═══════════════════════════════════════════════════════════


class TestIndependenceResolver:

    def test_unlinked_parties_are_independent(self):
        r = IndependenceResolver([source("A"), source("B")])
        assert r.are_independent("A", "B") is True
        assert r.group_count() == 2

    def test_linked_parties_are_not_independent(self):
        r = IndependenceResolver([source("A", linked=["B"]), source("B")])
        assert r.are_independent("A", "B") is False
        assert r.group_count() == 1

    def test_linkage_is_transitive(self):
        """A→B, B→C means A and C are one source.

        Without transitivity a two-hop chain reads as two independent
        corroborations — precisely the structure available to a counterparty
        that wants to manufacture one.
        """
        r = IndependenceResolver([
            source("A", linked=["B"]),
            source("B", linked=["C"]),
            source("C"),
        ])
        assert r.are_independent("A", "C") is False
        assert r.group_count() == 1

    def test_linkage_is_symmetric(self):
        """A one-sided declaration still collapses both.

        Independence is a property of the relationship, not of who disclosed it.
        """
        r = IndependenceResolver([source("A", linked=["B"]), source("B")])
        assert r.find("A") == r.find("B")

    def test_long_chain_collapses(self):
        chain = [source(f"P{i}", linked=[f"P{i+1}"]) for i in range(6)]
        chain.append(source("P6"))
        r = IndependenceResolver(chain)
        assert r.group_count() == 1
        assert r.are_independent("P0", "P6") is False

    def test_grouping_is_order_independent(self):
        """Determinism: same registry, any submission order, same grouping."""
        a = [source("A", linked=["B"]), source("B"), source("C")]
        b = [source("C"), source("B"), source("A", linked=["B"])]
        assert IndependenceResolver(a).groups() == IndependenceResolver(b).groups()

    def test_groups_are_sorted_and_stable(self):
        r = IndependenceResolver([source("Z", linked=["A"]), source("A"), source("M")])
        groups = r.groups()
        assert groups == {"A": ["A", "Z"], "M": ["M"]}

    def test_link_to_unregistered_party_still_unions(self):
        """A party named only in someone else's linked_parties still exists."""
        r = IndependenceResolver([source("A", linked=["GHOST"])])
        assert r.are_independent("A", "GHOST") is False

    def test_unknown_party_is_its_own_group(self):
        r = IndependenceResolver([source("A")])
        assert r.find("NEVER_SEEN") == "NEVER_SEEN"
        assert r.are_independent("A", "NEVER_SEEN") is True

    def test_contract_party_detection(self):
        r = IndependenceResolver([source("IP", contract_party=True), source("OTHER")])
        assert r.is_contract_party("IP") is True
        assert r.is_contract_party("OTHER") is False

    def test_contract_party_taints_its_whole_group(self):
        r = IndependenceResolver([
            source("IP", contract_party=True, linked=["SUB"]),
            source("SUB"),
        ])
        assert r.is_contract_party("SUB") is True

    def test_empty_registry(self):
        r = IndependenceResolver([])
        assert r.group_count() == 0
        assert r.groups() == {}

    def test_none_registry(self):
        assert IndependenceResolver(None).group_count() == 0


# ═══════════════════════════════════════════════════════════
# SECTION 3: QUERYABLE CLASS DERIVATION
# ═══════════════════════════════════════════════════════════


class TestDeriveQueryableClasses:

    def test_queryable_expectations_count(self):
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[
                expectation("E1", EvidenceClass.THIRD_PARTY_ADMIN, queryable=True),
                expectation("E2", EvidenceClass.GEOSPATIAL, queryable=True),
            ],
        )
        assert derive_queryable_classes(d) == {
            EvidenceClass.THIRD_PARTY_ADMIN,
            EvidenceClass.GEOSPATIAL,
        }

    def test_unqueryable_expectations_excluded(self):
        """The poor-country guard, at the capacity level. A registry that does
        not exist locally cannot be counted as reachable evidence space."""
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[
                expectation("E1", EvidenceClass.THIRD_PARTY_ADMIN, queryable=True),
                expectation("E2", EvidenceClass.BENEFICIARY_SIDE, queryable=False),
            ],
        )
        assert derive_queryable_classes(d) == {EvidenceClass.THIRD_PARTY_ADMIN}

    def test_answered_artifact_makes_class_queryable(self):
        """If a source answered, it was evidently reachable."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[artifact("A1", EvidenceClass.GEOSPATIAL, EvidenceStatus.ABSENT, "P1")],
        )
        assert derive_queryable_classes(d) == {EvidenceClass.GEOSPATIAL}

    def test_unqueryable_artifact_overrides_optimistic_expectation(self):
        """If the map said reachable but the query came back UNQUERYABLE, the
        map was wrong. Capacity follows reality, not the profile."""
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[expectation("E1", EvidenceClass.BENEFICIARY_SIDE, queryable=True)],
            artifacts=[artifact("A1", EvidenceClass.BENEFICIARY_SIDE,
                                EvidenceStatus.UNQUERYABLE, "P1")],
        )
        assert derive_queryable_classes(d) == set()

    def test_mixed_results_in_one_class_keep_it_queryable(self):
        """One unreachable source does not make the whole class unreachable if
        another source in that class answered."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                         EvidenceStatus.UNQUERYABLE, "P1"),
                artifact("A2", EvidenceClass.THIRD_PARTY_ADMIN,
                         EvidenceStatus.OBSERVED, "P2"),
            ],
        )
        assert derive_queryable_classes(d) == {EvidenceClass.THIRD_PARTY_ADMIN}

    def test_empty_dossier_has_no_queryable_classes(self):
        assert derive_queryable_classes(CorroborationDossier(claim=make_claim())) == set()


# ═══════════════════════════════════════════════════════════
# SECTION 4: GRAPH STRUCTURE
# ═══════════════════════════════════════════════════════════


class TestGraphStructure:

    def _full_dossier(self):
        return CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[
                expectation("E1", EvidenceClass.THIRD_PARTY_ADMIN),
                expectation("E2", EvidenceClass.GEOSPATIAL),
                expectation("E3", EvidenceClass.BENEFICIARY_SIDE, queryable=False),
            ],
            artifacts=[
                artifact("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                         EvidenceStatus.OBSERVED, "UTILITY"),
                artifact("A2", EvidenceClass.GEOSPATIAL,
                         EvidenceStatus.CONTRADICTORY, "IMAGERY"),
                artifact("A3", EvidenceClass.INSTITUTIONAL,
                         EvidenceStatus.ABSENT, "MINISTRY"),
                artifact("A4", EvidenceClass.BENEFICIARY_SIDE,
                         EvidenceStatus.UNQUERYABLE, "HEALTH_MIS"),
                artifact("A5", EvidenceClass.ADVERSARIAL_OPEN,
                         EvidenceStatus.STALE, "PRESS"),
            ],
            source_registry=[
                source("UTILITY"), source("IMAGERY", ptype="commercial_provider"),
                source("MINISTRY"), source("HEALTH_MIS"),
                source("PRESS", ptype="civil_society"),
            ],
        )

    def test_graph_written_to_dossier(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        assert d.graph is not None
        assert d.graph.node_count == len(d.graph.nodes)
        assert d.graph.edge_count == len(d.graph.edges)

    def test_claim_node_present_and_typed(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        claim_nodes = [n for n in d.graph.nodes if n["type"] == EvidenceNodeType.CLAIM.value]
        assert len(claim_nodes) == 1

    def test_every_node_carries_a_known_type(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        known = {t.value for t in EvidenceNodeType}
        assert all(n["type"] in known for n in d.graph.nodes)

    def test_every_edge_carries_a_known_type(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        known = {t.value for t in EvidenceEdgeType}
        assert all(e["type"] in known for e in d.graph.edges)

    def test_structural_edges_carry_the_base_marker(self):
        """Mirrors delivery_graph and the NON_RULE_MARKERS convention, so
        rule-derived edges stay distinguishable when step 3 adds them."""
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        assert all(e["rule"] == BASE_EDGE_MARKER for e in d.graph.edges)

    def test_claim_requires_every_expectation(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        requires = [e for e in d.graph.edges if e["type"] == EvidenceEdgeType.REQUIRES.value]
        assert len(requires) == 3
        assert all(e["source"] == "claim" for e in requires)

    def test_observed_evidence_satisfies_its_expectation(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        sat = [e for e in d.graph.edges if e["type"] == EvidenceEdgeType.SATISFIES.value]
        assert any(e["source"] == "artifact_A1" and e["target"] == "expected_E1" for e in sat)

    def test_contradictory_evidence_points_at_the_claim(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        con = [e for e in d.graph.edges if e["type"] == EvidenceEdgeType.CONTRADICTS.value]
        assert len(con) == 1
        assert con[0]["source"] == "artifact_A2"
        assert con[0]["target"] == "claim"

    def test_absence_edge_runs_from_the_disappointed_expectation(self):
        """An absence is the disappointment of an expectation, so the edge runs
        expectation → absence rather than the reverse."""
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[expectation("E1", EvidenceClass.INSTITUTIONAL)],
            artifacts=[artifact("A1", EvidenceClass.INSTITUTIONAL,
                                EvidenceStatus.ABSENT, "MINISTRY")],
            source_registry=[source("MINISTRY")],
        )
        EvidenceGraphBuilder().build_graph(d)
        absent = [e for e in d.graph.edges if e["type"] == EvidenceEdgeType.ABSENT.value]
        assert len(absent) == 1
        assert absent[0]["source"] == "expected_E1"
        assert absent[0]["target"] == "artifact_A1"

    def test_produced_by_edges_attribute_every_sourced_artifact(self):
        d = self._full_dossier()
        EvidenceGraphBuilder().build_graph(d)
        produced = [e for e in d.graph.edges if e["type"] == EvidenceEdgeType.PRODUCED_BY.value]
        assert len(produced) == 5

    def test_linked_to_edge_emitted_once_per_pair(self):
        """A mutual declaration is one relationship, not two."""
        d = CorroborationDossier(
            claim=make_claim(),
            source_registry=[
                source("A", linked=["B"]),
                source("B", linked=["A"]),
            ],
        )
        EvidenceGraphBuilder().build_graph(d)
        links = [e for e in d.graph.edges if e["type"] == EvidenceEdgeType.LINKED_TO.value]
        assert len(links) == 1


class TestGraphRefusals:
    """What the graph deliberately does NOT connect.

    Both assertions here block a route by which a claim could acquire
    unearned support.
    """

    def test_unqueryable_artifact_has_no_edge_to_the_claim(self):
        """An unreachable source says nothing for or against the claim. An edge
        here would let a downstream traversal mistake reach for evidence."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[artifact("A1", EvidenceClass.BENEFICIARY_SIDE,
                                EvidenceStatus.UNQUERYABLE, "HEALTH_MIS")],
            source_registry=[source("HEALTH_MIS")],
        )
        EvidenceGraphBuilder().build_graph(d)
        touching = [
            e for e in d.graph.edges
            if "artifact_A1" in (e["source"], e["target"])
            and "claim" in (e["source"], e["target"])
        ]
        assert touching == []

    def test_unqueryable_artifact_is_typed_unqueryable_not_missing(self):
        """UNQUERYABLE must never be rendered as MISSING_EVIDENCE. That single
        substitution would turn thin infrastructure into a finding."""
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[artifact("A1", EvidenceClass.BENEFICIARY_SIDE,
                                EvidenceStatus.UNQUERYABLE, "P1")],
            source_registry=[source("P1")],
        )
        EvidenceGraphBuilder().build_graph(d)
        node = next(n for n in d.graph.nodes if n["id"] == "artifact_A1")
        assert node["type"] == EvidenceNodeType.UNQUERYABLE.value
        assert node["type"] != EvidenceNodeType.MISSING_EVIDENCE.value

    def test_unqueryable_expectation_is_typed_unqueryable(self):
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[expectation("E1", EvidenceClass.BENEFICIARY_SIDE, queryable=False)],
        )
        EvidenceGraphBuilder().build_graph(d)
        node = next(n for n in d.graph.nodes if n["id"] == "expected_E1")
        assert node["type"] == EvidenceNodeType.UNQUERYABLE.value

    def test_stale_evidence_does_not_satisfy(self):
        """Stale evidence shows the claim held outside the window under
        examination. It is present, and it is not corroboration."""
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[expectation("E1", EvidenceClass.ADVERSARIAL_OPEN)],
            artifacts=[artifact("A1", EvidenceClass.ADVERSARIAL_OPEN,
                                EvidenceStatus.STALE, "PRESS")],
            source_registry=[source("PRESS", ptype="civil_society")],
        )
        EvidenceGraphBuilder().build_graph(d)
        sat = [e for e in d.graph.edges if e["type"] == EvidenceEdgeType.SATISFIES.value]
        assert sat == []


# ═══════════════════════════════════════════════════════════
# SECTION 5: BUILD REPORT AND WRITEBACK
# ═══════════════════════════════════════════════════════════


class TestBuildReport:

    def test_counts_by_status(self):
        d = CorroborationDossier(
            claim=make_claim(),
            artifacts=[
                artifact("A1", EvidenceClass.INSTITUTIONAL, EvidenceStatus.OBSERVED, "P1"),
                artifact("A2", EvidenceClass.GEOSPATIAL, EvidenceStatus.CONTRADICTORY, "P2"),
                artifact("A3", EvidenceClass.THIRD_PARTY_ADMIN, EvidenceStatus.ABSENT, "P3"),
                artifact("A4", EvidenceClass.BENEFICIARY_SIDE, EvidenceStatus.UNQUERYABLE, "P4"),
                artifact("A5", EvidenceClass.ADVERSARIAL_OPEN, EvidenceStatus.STALE, "P5"),
            ],
            source_registry=[source(f"P{i}") for i in range(1, 6)],
        )
        r = build(d)
        assert r.artifacts_total == 5
        assert r.artifacts_corroborating == 1
        assert r.artifacts_contradicting == 1
        assert r.artifacts_absent == 1
        assert r.artifacts_unqueryable == 1
        assert r.artifacts_stale == 1

    def test_unqueried_expectations_are_reported(self):
        """An expectation with no artifact was never asked. That is not an
        absence — absence requires the provenance of a query — so it is
        counted separately rather than folded into a finding."""
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[
                expectation("E1", EvidenceClass.THIRD_PARTY_ADMIN),
                expectation("E2", EvidenceClass.GEOSPATIAL),
            ],
            artifacts=[artifact("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                                EvidenceStatus.OBSERVED, "P1")],
            source_registry=[source("P1")],
        )
        r = build(d)
        assert r.expectations_total == 2
        assert r.expectations_addressed == 1
        assert r.expectations_unqueried == 1

    def test_unqueryable_expectations_counted(self):
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[
                expectation("E1", EvidenceClass.BENEFICIARY_SIDE, queryable=False),
                expectation("E2", EvidenceClass.FIELD_VERIFICATION, queryable=False),
            ],
        )
        assert build(d).expectations_unqueryable == 2

    def test_collapse_ratio_exposes_inflation(self):
        """Four submitted sources resolving to one is visible as 0.25."""
        d = CorroborationDossier(
            claim=make_claim(),
            source_registry=[
                source("A", linked=["B"]), source("B", linked=["C"]),
                source("C", linked=["D"]), source("D"),
            ],
        )
        r = build(d)
        assert r.parties_registered == 4
        assert r.parties_after_collapse == 1
        assert r.collapse_ratio == 0.25

    def test_collapse_ratio_is_one_when_all_independent(self):
        d = CorroborationDossier(
            claim=make_claim(),
            source_registry=[source("A"), source("B"), source("C")],
        )
        assert build(d).collapse_ratio == 1.0

    def test_collapse_ratio_no_division_error_on_empty_registry(self):
        assert build(CorroborationDossier(claim=make_claim())).collapse_ratio == 1.0

    def test_contract_parties_counted(self):
        d = CorroborationDossier(
            claim=make_claim(),
            source_registry=[source("IP", contract_party=True), source("OTHER")],
        )
        assert build(d).parties_excluded_as_contract_party == 1

    def test_independence_groups_recorded(self):
        d = CorroborationDossier(
            claim=make_claim(),
            source_registry=[source("A", linked=["B"]), source("B"), source("C")],
        )
        assert build(d).independence_groups == {"A": ["A", "B"], "C": ["C"]}


class TestWriteback:

    def test_derived_counts_written_to_dossier(self):
        d = CorroborationDossier(
            claim=make_claim(),
            expected_evidence=[
                expectation("E1", EvidenceClass.THIRD_PARTY_ADMIN),
                expectation("E2", EvidenceClass.GEOSPATIAL),
            ],
            artifacts=[
                artifact("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                         EvidenceStatus.OBSERVED, "UTILITY"),
                artifact("A2", EvidenceClass.GEOSPATIAL,
                         EvidenceStatus.OBSERVED, "IMAGERY"),
            ],
            source_registry=[source("UTILITY"), source("IMAGERY")],
        )
        EvidenceGraphBuilder().build_graph(d)
        assert d.independent_classes_corroborating == 2
        assert d.classes_queryable == 2
        assert d.corroboration_capacity == pytest.approx(2 / 6)

    def test_builder_writes_no_verdict(self):
        """Verdicts come from the gate at Stage 16, after the rules have run.
        A graph builder that set a verdict would be deciding without evidence."""
        d = CorroborationDossier(claim=make_claim())
        EvidenceGraphBuilder().build_graph(d)
        assert d.verdict is None
        assert d.rules_result is None

    def test_build_is_deterministic(self):
        """Same input, same graph. Forever."""
        def fresh():
            return CorroborationDossier(
                claim=make_claim(),
                expected_evidence=[expectation("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
                artifacts=[
                    artifact("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                             EvidenceStatus.OBSERVED, "UTILITY"),
                    artifact("A2", EvidenceClass.GEOSPATIAL,
                             EvidenceStatus.CONTRADICTORY, "IMAGERY"),
                ],
                source_registry=[source("UTILITY", linked=["IMAGERY"]), source("IMAGERY")],
            )

        d1, d2 = fresh(), fresh()
        EvidenceGraphBuilder().build_graph(d1)
        EvidenceGraphBuilder().build_graph(d2)
        assert d1.graph.nodes == d2.graph.nodes
        assert d1.graph.edges == d2.graph.edges

    def test_empty_dossier_builds_a_claim_only_graph(self):
        d = CorroborationDossier(claim=make_claim())
        EvidenceGraphBuilder().build_graph(d)
        assert d.graph.node_count == 1
        assert d.graph.edge_count == 0
        assert d.independent_classes_corroborating == 0
        assert d.corroboration_capacity == 0.0

    def test_side_1_to_4_untouched(self):
        """Purely additive: the builder holds no handle on any other side."""
        d = CorroborationDossier(claim=make_claim())
        EvidenceGraphBuilder().build_graph(d)
        assert d.claim.source_dossier_id is None
        assert d.claim.source_recovery_id is None
