"""
SUNLIGHT Side 5 — Corroboration Graph Construction
=====================================================

Builds a typed directed graph of what SHOULD exist against what DOES exist,
then collapses non-independent sources before anything is counted.

Same evidence + same registry = same graph. Forever.

Architecture:
    Mirrors DeliveryGraphBuilder from delivery_graph.py:
    1. Construct the base graph (claim → expectations)
    2. Add observed, missing, contradictory and unqueryable evidence nodes
    3. Add source nodes and independence links
    4. Collapse linked sources, count independent corroboration
    5. Write EvidenceGraphResult to dossier.graph

    Nodes and edges are plain dicts with the same shape delivery uses
    ({"id", "label", "metadata"}), so serialisation and tooling stay uniform,
    with one addition: nodes carry a "type" field. Side 5 needs to tell an
    expectation from an observation from a documented absence, and delivery's
    untyped nodes cannot express that.

    The edge vocabulary is Side 5's own and deliberately does not reuse the
    seven TCA types. There is no TCA edge that means LINKED_TO, and source
    linkage is the load-bearing mechanic here — forcing it into MIRRORS or
    INHERITS would lose exactly the meaning the graph exists to carry.
    Structural edges keep the "rule": "BASE" marker so non-rule edges remain
    distinguishable, as in delivery and tca_analyzer.

Why independence collapse is the centre of this module:
    Corroboration count is trivially inflatable. Submit six reports from six
    departments of one ministry and a false claim appears corroborated across
    six sources. Submit a prime contractor's report and its subcontractor's
    report and it appears corroborated twice.

    So the graph unions every party joined by a LINKED_TO edge — transitively,
    and treating the declaration as symmetric — and counts independence
    GROUPS, not documents. Parties to the contract are excluded outright: an
    implementing partner cannot independently corroborate its own delivery.

    The question the count answers is: how many genuinely separate parties
    would have to be complicit for this claim to be false?

Stage note:
    This module builds structure and counts corroboration. Rule evaluation
    (the 16 rules) arrives in evidence_rules.py and is wired in at Stage 15,
    the same way DeliveryGraphBuilder invokes DeliveryRuleEngine. There is no
    placeholder rule engine here — an empty one would report "0 rules fired",
    which reads identically to "nothing was wrong".

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from evidence_schema import (
    CorroborationDossier,
    EvidenceArtifact,
    EvidenceClass,
    EvidenceGraphResult,
    EvidenceStatus,
    ExpectedEvidence,
)


# ═══════════════════════════════════════════════════════════
# SECTION 1: NODE AND EDGE VOCABULARY
# ═══════════════════════════════════════════════════════════


class EvidenceNodeType(Enum):
    """What a node in the corroboration graph represents."""
    CLAIM = "CLAIM"                                   # what was asserted
    EXPECTED_EVIDENCE = "EXPECTED_EVIDENCE"           # what should exist if true
    OBSERVED_EVIDENCE = "OBSERVED_EVIDENCE"           # what was actually found
    MISSING_EVIDENCE = "MISSING_EVIDENCE"             # expected, queried, not found
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"  # found and inconsistent
    SOURCE = "SOURCE"                                 # the party that produced evidence
    UNQUERYABLE = "UNQUERYABLE"                       # class unavailable here — NOT a contradiction


class EvidenceEdgeType(Enum):
    """What a relationship in the corroboration graph asserts."""
    REQUIRES = "REQUIRES"          # claim requires this expected evidence
    SATISFIES = "SATISFIES"        # observed evidence satisfies an expectation
    CONTRADICTS = "CONTRADICTS"    # observed evidence contradicts the claim
    ABSENT = "ABSENT"              # expectation has a documented non-observation
    PRODUCED_BY = "PRODUCED_BY"    # evidence was produced by a source
    LINKED_TO = "LINKED_TO"        # source is NOT independent of another source


# Marker for structural (non-rule) edges, matching delivery_graph.py and the
# NON_RULE_MARKERS convention in tca_analyzer.py.
BASE_EDGE_MARKER = "BASE"


# ═══════════════════════════════════════════════════════════
# SECTION 2: BUILD REPORT
# ═══════════════════════════════════════════════════════════


@dataclass
class EvidenceGraphBuildReport:
    """Audit trail of how a corroboration graph was constructed.

    Several counters here exist so that nothing is dropped silently. An
    artifact that cannot be attributed to a party, or an expectation that was
    never queried at all, must be visible rather than quietly absent from the
    corroboration count.
    """
    nodes_total: int = 0
    edges_total: int = 0

    expectations_total: int = 0
    expectations_addressed: int = 0
    expectations_unqueried: int = 0        # no artifact at all — never asked
    expectations_unqueryable: int = 0      # source does not exist in this jurisdiction

    artifacts_total: int = 0
    artifacts_corroborating: int = 0
    artifacts_contradicting: int = 0
    artifacts_absent: int = 0
    artifacts_unqueryable: int = 0
    artifacts_stale: int = 0

    # Corroborating artifacts with no source_party_id. They cannot count
    # toward independent corroboration — an unattributable document vouches
    # for nothing — so they are surfaced here rather than dropped in silence.
    artifacts_unattributed: int = 0

    parties_registered: int = 0
    parties_after_collapse: int = 0
    parties_excluded_as_contract_party: int = 0

    independence_groups: Dict[str, List[str]] = field(default_factory=dict)
    classes_queryable: int = 0
    independent_corroborations: int = 0
    distinct_classes_corroborating: int = 0

    graph_version: str = "EGS-2026-07-001"

    @property
    def collapse_ratio(self) -> float:
        """How much corroboration was inflated before collapse.

        1.0 means every party was genuinely independent. 0.25 means four
        submitted sources resolved to one.
        """
        if self.parties_registered <= 0:
            return 1.0
        return self.parties_after_collapse / self.parties_registered


# ═══════════════════════════════════════════════════════════
# SECTION 3: INDEPENDENCE COLLAPSE
# ═══════════════════════════════════════════════════════════


class IndependenceResolver:
    """Union-find over party linkage. Collapses non-independent sources.

    Linkage is treated as SYMMETRIC and TRANSITIVE:

        symmetric  — if a ministry declares a link to its agency but the
                     agency declares nothing, they are still one source.
                     Independence is a property of the relationship, not of
                     who happened to disclose it.

        transitive — prime → subcontractor → sub-subcontractor collapses to
                     one group. Without transitivity, a two-hop chain would
                     read as two independent corroborations, which is exactly
                     the structure a contractor would use to manufacture one.

    Deterministic: group representatives are chosen by sorted party id, so
    the same registry always produces the same grouping regardless of the
    order parties were submitted in.
    """

    def __init__(self, registry: Optional[List] = None):
        self._parent: Dict[str, str] = {}
        self._known: Dict[str, object] = {}

        for source in (registry or []):
            self._known[source.party_id] = source
            self._add(source.party_id)

        # Second pass: union after every party exists, so link order cannot
        # change the outcome.
        for source in (registry or []):
            for linked in sorted(source.linked_parties or []):
                self._add(linked)
                self.union(source.party_id, linked)

            # A monitor is not independent of whoever chose it. Selection is
            # the same relationship linked_parties models, arrived at by a
            # different route, so it collapses the same way — which means a
            # monitor picked by the implementing partner inherits that
            # party's contract-party status and stops counting as outside
            # corroboration. Without this, capture is detectable (EVD-SRC-003)
            # but the captured monitor still inflates the corroboration count
            # it was chosen to inflate.
            selector = getattr(source, "selected_by", None)
            if selector:
                self._add(selector)
                self.union(source.party_id, selector)

    def _add(self, party_id: str) -> None:
        if party_id not in self._parent:
            self._parent[party_id] = party_id

    def find(self, party_id: str) -> str:
        """Representative of this party's independence group."""
        self._add(party_id)
        root = party_id
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression — safe because representative choice is by sort
        # order in union(), not by traversal order here.
        while self._parent[party_id] != root:
            self._parent[party_id], party_id = root, self._parent[party_id]
        return root

    def union(self, a: str, b: str) -> None:
        """Merge two parties into one independence group."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # Lexicographically smallest id wins, so grouping is deterministic
        # and independent of insertion order.
        low, high = (ra, rb) if ra < rb else (rb, ra)
        self._parent[high] = low

    def are_independent(self, a: str, b: str) -> bool:
        """False when two parties belong to the same independence group."""
        return self.find(a) != self.find(b)

    def is_contract_party(self, party_id: str) -> bool:
        """True when this party — or anything it is linked to — is party to the contract.

        Linkage propagates contract-party status. A subcontractor of the
        implementing partner is not an independent witness to the partner's
        own delivery, whatever its own record says.
        """
        group = self.find(party_id)
        for pid, source in self._known.items():
            if self.find(pid) == group and getattr(source, "is_contract_party", False):
                return True
        return False

    def groups(self) -> Dict[str, List[str]]:
        """Every independence group, as representative → sorted member ids."""
        out: Dict[str, List[str]] = {}
        for party_id in sorted(self._parent):
            out.setdefault(self.find(party_id), []).append(party_id)
        return {k: sorted(v) for k, v in sorted(out.items())}

    def group_count(self) -> int:
        return len(self.groups())


# ═══════════════════════════════════════════════════════════
# SECTION 4: DERIVED COUNTS
# ═══════════════════════════════════════════════════════════


def derive_queryable_classes(dossier: CorroborationDossier) -> Set[EvidenceClass]:
    """Which evidence classes were reachable in this jurisdiction at all.

    A class counts as queryable when either the expected-evidence map says a
    source for it exists locally, or an artifact for it came back as anything
    other than UNQUERYABLE — you cannot query an unreachable source and get
    an answer.

    This is the numerator of corroboration_capacity, and therefore the number
    that decides whether SUNLIGHT is entitled to draw an adverse conclusion
    here at all. Undercounting it is the safe direction; overcounting it would
    unlock a CONTRADICTED verdict the evidence base cannot support.
    """
    queryable: Set[EvidenceClass] = set()

    for exp in dossier.expected_evidence:
        if exp.queryable_in_jurisdiction:
            queryable.add(exp.evidence_class)

    for art in dossier.artifacts:
        if art.status != EvidenceStatus.UNQUERYABLE:
            queryable.add(art.evidence_class)

    # An explicit UNQUERYABLE finding overrides an optimistic expectation map:
    # if the source was actually unreachable, the map was wrong.
    for art in dossier.artifacts:
        if art.status == EvidenceStatus.UNQUERYABLE:
            has_other = any(
                a.evidence_class == art.evidence_class
                and a.status != EvidenceStatus.UNQUERYABLE
                for a in dossier.artifacts
            )
            if not has_other:
                queryable.discard(art.evidence_class)

    return queryable


def count_independent_corroborations(
    dossier: CorroborationDossier,
    resolver: Optional[IndependenceResolver] = None,
) -> Tuple[int, int, int]:
    """Count genuinely independent corroboration of the claim.

    Returns (independent_corroborations, distinct_classes, unattributed).

    SEMANTICS — read this before using the number.

        independent_corroborations counts INDEPENDENCE GROUPS, not documents
        and not classes. Two reports from one implementing partner are one
        corroboration. A prime and its subcontractor are one corroboration.
        Six departments of one ministry are one corroboration.

        The question it answers is how many separate parties would have to be
        complicit for the claim to be false — which is the only reading of
        "independent" that survives contact with a determined counterparty.

        distinct_classes is reported alongside it as a diagnostic, because
        three corroborations spanning satellite imagery, a utility registry
        and a patient-record system are stronger than three spanning three
        institutional reports. Nothing gates on it today; it exists so the
        difference is visible rather than lost.

    Excluded from the count, each for a stated reason:
        - artifacts that do not corroborate (only OBSERVED corroborates;
          STALE evidence shows the claim held outside the window of interest)
        - artifacts produced by a party to the contract, or by anything
          linked to one — self-attestation is not corroboration
        - artifacts with no source_party_id at all, which are returned as the
          third element so they are visible rather than silently dropped
    """
    resolver = resolver or IndependenceResolver(dossier.source_registry)

    groups: Set[str] = set()
    classes: Set[EvidenceClass] = set()
    unattributed = 0

    for art in dossier.artifacts:
        if not art.corroborates:
            continue

        party_id = art.source_party_id
        if not party_id:
            unattributed += 1
            continue

        if resolver.is_contract_party(party_id):
            continue

        groups.add(resolver.find(party_id))
        classes.add(art.evidence_class)

    return len(groups), len(classes), unattributed


# ═══════════════════════════════════════════════════════════
# SECTION 5: GRAPH BUILDER
# ═══════════════════════════════════════════════════════════


class EvidenceGraphBuilder:
    """Deterministic corroboration topology construction.

    Mirrors DeliveryGraphBuilder: build the graph from dossier data, write an
    EvidenceGraphResult back, and keep a build report for audit.
    """

    def __init__(self, profile=None):
        self.profile = profile
        self.last_report: Optional[EvidenceGraphBuildReport] = None

    # ── node id helpers ──────────────────────────────────

    @staticmethod
    def _claim_node_id() -> str:
        return "claim"

    @staticmethod
    def _expectation_node_id(exp: ExpectedEvidence) -> str:
        return f"expected_{exp.expectation_id}"

    @staticmethod
    def _artifact_node_id(art: EvidenceArtifact) -> str:
        return f"artifact_{art.artifact_id}"

    @staticmethod
    def _source_node_id(party_id: str) -> str:
        return f"source_{party_id}"

    # ── build ────────────────────────────────────────────

    def build_graph(self, dossier: CorroborationDossier) -> CorroborationDossier:
        """Build the corroboration graph and write derived counts to the dossier.

        Writes: dossier.graph, dossier.classes_queryable,
                dossier.independent_classes_corroborating

        Does NOT write a verdict. Verdicts come from the gate at Stage 16,
        after the rules have run.
        """
        nodes: List[Dict] = []
        edges: List[Dict] = []
        seen_ids: Set[str] = set()
        report = EvidenceGraphBuildReport()

        def add_node(node_id: str, label: str, node_type: EvidenceNodeType, **metadata):
            if node_id in seen_ids:
                return
            node: Dict = {"id": node_id, "label": label, "type": node_type.value}
            if metadata:
                node["metadata"] = metadata
            nodes.append(node)
            seen_ids.add(node_id)

        def add_edge(src: str, tgt: str, edge_type: EvidenceEdgeType,
                     weight: float, description: str):
            edges.append({
                "source": src,
                "target": tgt,
                "type": edge_type.value,
                "weight": weight,
                "rule": BASE_EDGE_MARKER,
                "description": description,
            })

        # ── The claim ──
        claim = dossier.claim
        claim_id = self._claim_node_id()
        add_node(
            claim_id,
            f"Claim: {claim.claim_description}",
            EvidenceNodeType.CLAIM,
            outcome_type=claim.outcome_type.value,
            contract_id=claim.contract_id,
        )

        # ── Expectations: what should exist if the claim is true ──
        report.expectations_total = len(dossier.expected_evidence)

        for exp in dossier.expected_evidence:
            exp_node = self._expectation_node_id(exp)

            if exp.queryable_in_jurisdiction:
                add_node(
                    exp_node,
                    f"Expected: {exp.description}",
                    EvidenceNodeType.EXPECTED_EVIDENCE,
                    evidence_class=exp.evidence_class.value,
                    required=exp.required,
                    expected_by_month=exp.expected_by_month,
                )
            else:
                # The source does not exist in this jurisdiction. This node is
                # NOT a finding — it records a limit on SUNLIGHT's reach, and
                # nothing downstream may treat it as evidence against anyone.
                report.expectations_unqueryable += 1
                add_node(
                    exp_node,
                    f"Unqueryable here: {exp.description}",
                    EvidenceNodeType.UNQUERYABLE,
                    evidence_class=exp.evidence_class.value,
                    reason="source does not exist in this jurisdiction",
                )

            add_edge(
                claim_id, exp_node, EvidenceEdgeType.REQUIRES,
                1.0 if exp.required else 0.5,
                f"Claim requires {exp.description}",
            )

        # Map expectations by class so artifacts can be matched to them.
        expectations_by_class: Dict[EvidenceClass, List[ExpectedEvidence]] = {}
        for exp in dossier.expected_evidence:
            expectations_by_class.setdefault(exp.evidence_class, []).append(exp)

        addressed_classes: Set[EvidenceClass] = set()

        # ── Artifacts: what was actually found, or documented as not found ──
        report.artifacts_total = len(dossier.artifacts)

        for art in dossier.artifacts:
            art_node = self._artifact_node_id(art)
            addressed_classes.add(art.evidence_class)
            matched = expectations_by_class.get(art.evidence_class, [])

            if art.status == EvidenceStatus.OBSERVED:
                report.artifacts_corroborating += 1
                add_node(art_node, f"Observed: {art.description}",
                         EvidenceNodeType.OBSERVED_EVIDENCE,
                         evidence_class=art.evidence_class.value,
                         observed_value=art.observed_value)
                for exp in matched:
                    add_edge(art_node, self._expectation_node_id(exp),
                             EvidenceEdgeType.SATISFIES, 1.0,
                             f"{art.description} satisfies {exp.description}")
                if not matched:
                    add_edge(art_node, claim_id, EvidenceEdgeType.SATISFIES, 0.8,
                             f"{art.description} corroborates the claim")

            elif art.status == EvidenceStatus.CONTRADICTORY:
                report.artifacts_contradicting += 1
                add_node(art_node, f"Contradictory: {art.description}",
                         EvidenceNodeType.CONTRADICTORY_EVIDENCE,
                         evidence_class=art.evidence_class.value,
                         observed_value=art.observed_value)
                add_edge(art_node, claim_id, EvidenceEdgeType.CONTRADICTS, 1.0,
                         f"{art.description} is inconsistent with the claim")

            elif art.status == EvidenceStatus.ABSENT:
                report.artifacts_absent += 1
                add_node(art_node, f"Absent: {art.description}",
                         EvidenceNodeType.MISSING_EVIDENCE,
                         evidence_class=art.evidence_class.value)
                # The ABSENT edge runs expectation → absence: the expectation
                # is what was disappointed. Where no expectation was declared
                # the absence still stands on its own documented query.
                for exp in matched:
                    add_edge(self._expectation_node_id(exp), art_node,
                             EvidenceEdgeType.ABSENT, 1.0,
                             f"{exp.description} queried and not found")
                if not matched:
                    add_edge(claim_id, art_node, EvidenceEdgeType.ABSENT, 0.8,
                             f"{art.description} queried and not found")

            elif art.status == EvidenceStatus.UNQUERYABLE:
                report.artifacts_unqueryable += 1
                add_node(art_node, f"Unqueryable: {art.description}",
                         EvidenceNodeType.UNQUERYABLE,
                         evidence_class=art.evidence_class.value,
                         reason="source unavailable in this jurisdiction")
                # Deliberately NO edge to the claim. An unqueryable source
                # says nothing for or against it, and an edge here would let
                # a downstream traversal mistake reach for evidence.

            elif art.status == EvidenceStatus.STALE:
                report.artifacts_stale += 1
                add_node(art_node, f"Stale: {art.description}",
                         EvidenceNodeType.OBSERVED_EVIDENCE,
                         evidence_class=art.evidence_class.value,
                         stale=True)
                # No SATISFIES edge: stale evidence shows the claim held at
                # some point outside the window under examination, which is
                # not corroboration of the claim as made.

            # ── Source attribution ──
            if art.source_party_id:
                src_node = self._source_node_id(art.source_party_id)
                registered = dossier.source(art.source_party_id)
                add_node(
                    src_node,
                    f"Source: {registered.party_name if registered else art.source_party_id}",
                    EvidenceNodeType.SOURCE,
                    party_type=registered.party_type if registered else "unregistered",
                    is_contract_party=bool(registered.is_contract_party) if registered else False,
                )
                add_edge(art_node, src_node, EvidenceEdgeType.PRODUCED_BY, 1.0,
                         f"{art.description} produced by {art.source_party_id}")
            elif art.corroborates:
                report.artifacts_unattributed += 1

        report.expectations_addressed = sum(
            1 for exp in dossier.expected_evidence
            if exp.evidence_class in addressed_classes
        )
        report.expectations_unqueried = (
            report.expectations_total - report.expectations_addressed
        )

        # ── Sources and their linkage ──
        resolver = IndependenceResolver(dossier.source_registry)
        report.parties_registered = len(dossier.source_registry)

        for source in dossier.source_registry:
            src_node = self._source_node_id(source.party_id)
            add_node(src_node, f"Source: {source.party_name}",
                     EvidenceNodeType.SOURCE,
                     party_type=source.party_type,
                     is_contract_party=source.is_contract_party)
            if source.is_contract_party:
                report.parties_excluded_as_contract_party += 1

        # One LINKED_TO edge per unordered pair, so a mutual declaration does
        # not read as two separate links.
        emitted_links: Set[Tuple[str, str]] = set()
        for source in dossier.source_registry:
            for linked in sorted(source.linked_parties or []):
                pair = tuple(sorted((source.party_id, linked)))
                if pair in emitted_links:
                    continue
                emitted_links.add(pair)
                add_node(self._source_node_id(linked), f"Source: {linked}",
                         EvidenceNodeType.SOURCE, party_type="unregistered",
                         is_contract_party=False)
                add_edge(self._source_node_id(pair[0]), self._source_node_id(pair[1]),
                         EvidenceEdgeType.LINKED_TO, 1.0,
                         f"{pair[0]} is not independent of {pair[1]}")

        report.parties_after_collapse = resolver.group_count()
        report.independence_groups = resolver.groups()

        # ── Derived counts ──
        queryable = derive_queryable_classes(dossier)
        report.classes_queryable = len(queryable)

        independent, distinct_classes, unattributed = count_independent_corroborations(
            dossier, resolver
        )
        report.independent_corroborations = independent
        report.distinct_classes_corroborating = distinct_classes
        report.artifacts_unattributed = unattributed

        # ── Write back ──
        report.nodes_total = len(nodes)
        report.edges_total = len(edges)
        self.last_report = report

        dossier.graph = EvidenceGraphResult(
            node_count=len(nodes),
            edge_count=len(edges),
            nodes=nodes,
            edges=edges,
        )
        dossier.classes_queryable = len(queryable)
        dossier.independent_classes_corroborating = independent

        return dossier
