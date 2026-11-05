"""Pure as-of examination and changes. No HTTP, clock, model or corpus mutation."""
from __future__ import annotations

from watch_identity import canonical, digest, resolve
from watch_journal import utc
from datetime import datetime
import re

VERSION = "sunlight.watch-examination.v2"


def input_basis(rule, record, fields, currency):
    """Availability of the actual inputs, without repairing or retuning a rule."""
    tender = record.get("tender") or {}
    awards = record.get("awards") or []
    award = awards[0] if awards else {}
    tv, av = tender.get("value") or {}, award.get("value") or {}
    def numeric(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    tender_value = numeric(tv.get("amount")) and tv.get("currency") == currency
    comparable_values = (tender_value and numeric(av.get("amount")) and av.get("currency") == currency
                         and tv["amount"] > 0 and av["amount"] > 0)
    bidders = isinstance(tender.get("numberOfTenderers"), int) and not isinstance(tender.get("numberOfTenderers"), bool) and tender["numberOfTenderers"] >= 0
    suppliers = fields.get("suppliers") or []
    explicit_ids = len(suppliers) >= 2 and all(isinstance(s.get("id"), str) and bool(s["id"]) for s in suppliers)
    geography = bool(re.fullmatch(r"[a-z]{2}", fields.get("country_code") or "")) and bool(fields["supplier_countries"]) and all(re.fullmatch(r"[a-z]{2}", s) for s in fields["supplier_countries"])
    requirements = {
        "PROC-001": (bool(fields["procurement_method"]) and tender_value, "Published procurement method and numeric tender value in profile currency"),
        "PROC-002": (bool(fields["procurement_method"]) and bidders, "Published procurement method and non-negative integer bidder count"),
        "PROC-003": (isinstance(record.get("parties"), list), "Published parties array; absence of a named review body is about this document only"),
        "PROC-004": (isinstance(record.get("parties"), list), "Published parties array"),
        "PROC-005": (bool(fields["procurement_method"]) and bidders, "Published procurement method and non-negative integer bidder count"),
        "ENT-001": (len(fields["supplier_addresses"]) >= 2, "At least two published organizational street addresses"),
        "ENT-002": (explicit_ids, "At least two explicit supplier identifiers; names are not identity"),
        "ENT-003": (bool(suppliers) and bidders, "Published suppliers and bidder count"),
        "FIN-001": (comparable_values, "Positive tender and award values in the same profile currency"),
        "FIN-002": (comparable_values and bidders, "Positive comparable tender and award values, plus bidder count"),
        "FIN-003": (comparable_values, "Positive tender and award values in the same profile currency"),
        "TIME-001": (fields["award_month"] is not None and fields["award_day"] is not None, "Parseable published award date"),
        "TIME-002": (fields["award_month"] is not None, "Parseable published award month"),
        "TIME-003": (fields["award_month"] is not None, "Parseable published award month"),
        "GEO-001": (geography, "Contract and supplier jurisdictions in the same two-letter code vocabulary"),
        "GEO-002": (geography, "Contract and supplier jurisdictions in the same two-letter code vocabulary"),
    }
    available, requires = requirements.get(rule, (False, "Input contract not reviewed for this rule"))
    return {"available": bool(available), "requires": requires}


def procurement(record):
    """Run the existing profile's complete TCA rule family without retuning it.

    This is a structural screen, not a price-comparable, delivery or arms run.
    Those engines need additional dossiers; their absence is stated explicitly.
    """
    from sunlight_core import SunlightPipeline
    from tca_rules import TCAGraphRuleEngineAdapter, _extract
    from jurisdiction_profile import UK_CENTRAL_GOVERNMENT
    grapher = TCAGraphRuleEngineAdapter(profile=UK_CENTRAL_GOVERNMENT)
    pipeline = SunlightPipeline(grapher=grapher)
    dossier = pipeline.process(pipeline.ingest(record))
    if dossier.errors or dossier.graph is None:
        raise ValueError("procurement_rule_execution_failed")
    results = []
    log = dossier.graph["metadata"]["rule_fire_log"]
    fields = _extract(dossier)
    for rule in grapher.engine.rules:
        basis = input_basis(rule.rule_id, record, fields, UK_CENTRAL_GOVERNMENT.currency)
        relations = sorted({edge["type"] for edge in dossier.graph["edges"] if edge.get("rule") == rule.rule_id})
        if not basis["available"]:
            status = "UNASSESSABLE"
        elif not log[rule.rule_id]:
            status = "NOT_TRIGGERED"
        elif relations and set(relations) <= {"VERIFIES", "EXPRESSES"}:
            status = "DOCUMENTED_SIGNAL"
        else:
            status = "INDICATOR"
        results.append({"rule": rule.rule_id, "dimension": rule.layer,
                        "status": status, "rule_fired": log[rule.rule_id],
                        "input_basis": basis, "relation_types": relations,
                        "citation": rule.evidence, "description": rule.description.replace("\u2014", ";")})
    return results


def examine(observations, as_of, *, procurement_reader=procurement):
    cutoff = utc(as_of)
    admitted = [r for r in observations if utc(r["captured_at"]) <= cutoff and
                (r.get("published_at") is None or utc(r["published_at"]) <= cutoff)]
    # Keep every historical version, even after a record is superseded.
    unique = {}
    for record in sorted(admitted, key=lambda r: (r["captured_at"], r["id"], canonical(r["evidence"]))):
        unique.setdefault(record["id"], record)
    history = sorted(unique.values(), key=lambda r: (r["captured_at"], r["id"]))
    subjects = resolve(history)
    latest = {}
    for r in admitted:
        key = (r["source"], r["key"])
        # Equal capture times with different versions are ambiguous, not ordered by arrival.
        rank = (r.get("published_at") or "", r["captured_at"])
        old = latest.get(key)
        if old is None or rank > old[0]:
            latest[key] = (rank, {r["id"]: unique[r["id"]]})
        elif rank == old[0]:
            old[1][r["id"]] = unique[r["id"]]
    readings, questions = [], []
    for _, versions in sorted(latest.values(), key=lambda x: canonical(x[1])):
        for r in sorted(versions.values(), key=lambda x: x["id"]):
            if len(versions) > 1:
                questions.append({"observation": r["id"], "reason": "ambiguous_record_versions", "status": "UNASSESSABLE"})
                continue
            if r["category"] == "procurement":
                try:
                    outputs = procurement_reader(r["record"])
                except ImportError:
                    outputs = []
                    questions.append({"observation": r["id"], "reason": "procurement_runtime_unavailable", "status": "UNASSESSABLE"})
            else:
                outputs = []
                questions.append({"observation": r["id"], "reason": "aid_reporting_observation_only", "status": "UNASSESSABLE"})
            for output in outputs:
                readings.append({**output, "observation": r["id"], "evidence": r["evidence"],
                                 "id": digest({"observation": r["id"], "rule": output["rule"], "version": VERSION})})
            if r.get("published_at") is None:
                questions.append({"observation": r["id"], "reason": "publication_time_not_supplied", "status": "UNAVAILABLE"})
    by_id = {r["id"]: r for r in history}
    for s in subjects:
        s["categories"] = sorted({by_id[oid]["category"] for oid in s["observations"]})
    for q in questions:
        record = by_id[q["observation"]]
        q["source"], q["record_key"] = record["source"], record["key"]
        q["id"] = digest({"source": q["source"], "record_key": q["record_key"], "reason": q["reason"]})
        same_record = [r for r in history if (r["source"], r["key"]) == (record["source"], record["key"])]
        if q["reason"] == "ambiguous_record_versions":
            # Age refers to this selected ambiguous capture group, not an
            # unsupported claim about when the publisher first became ambiguous.
            q["since"] = latest[(record["source"], record["key"])][0][1]
        else:
            q["since"] = min(r["captured_at"] for r in same_record)
        q["age_seconds"] = (datetime.fromisoformat(cutoff) - datetime.fromisoformat(q["since"])).total_seconds()
        q["evidence"] = by_id[q["observation"]]["evidence"]
    return {"schema": VERSION, "as_of": cutoff, "subjects": subjects,
            "observations": history, "readings": sorted(readings, key=lambda r: r["id"]),
            "open_questions": sorted(questions, key=canonical),
            "scope": "Organizational structural screening only. No price-comparable, delivery, recovery or arms inference.",
            "framing": "Indicator, never allegation. Missing is not zero."}


def changes(previous, current):
    """Report gained/lost/versioned evidence and reading changes, not guilt."""
    old = {r["id"] for r in (previous or {}).get("observations", [])}
    new = {r["id"] for r in current["observations"]}
    previous_readings = {digest(r) for r in (previous or {}).get("readings", [])}
    readings = {digest(r) for r in current["readings"]}
    def question_key(q):
        return canonical({"id": q.get("id", q["observation"]), "reason": q["reason"], "status": q["status"]})
    previous_questions = {question_key(q) for q in (previous or {}).get("open_questions", [])}
    questions = {question_key(q) for q in current["open_questions"]}
    return {"observations_added": sorted(new - old),
            "readings_added": sorted(readings - previous_readings),
            "readings_superseded": sorted(previous_readings - readings),
            "questions_opened": sorted(questions - previous_questions),
            "questions_closed": sorted(previous_questions - questions)}
