"""Pure as-of examination and changes. No HTTP, clock, model or corpus mutation."""
from __future__ import annotations

from watch_identity import canonical, digest, resolve
from watch_journal import utc
from datetime import datetime

VERSION = "sunlight.watch-examination.v1"


def procurement(record):
    """Run the existing profile's complete TCA rule family without retuning it.

    This is a structural screen, not a price-comparable, delivery or arms run.
    Those engines need additional dossiers; their absence is stated explicitly.
    """
    from sunlight_core import SunlightPipeline
    from tca_rules import TCAGraphRuleEngineAdapter
    from jurisdiction_profile import UK_CENTRAL_GOVERNMENT
    grapher = TCAGraphRuleEngineAdapter(profile=UK_CENTRAL_GOVERNMENT)
    pipeline = SunlightPipeline(grapher=grapher)
    dossier = pipeline.process(pipeline.ingest(record))
    if dossier.errors or dossier.graph is None:
        raise ValueError("procurement_rule_execution_failed")
    results = []
    log = dossier.graph["metadata"]["rule_fire_log"]
    for rule in grapher.engine.rules:
        results.append({"rule": rule.rule_id, "dimension": rule.layer,
                        "status": "INDICATOR" if log[rule.rule_id] else "NOT_TRIGGERED",
                        "citation": rule.evidence, "description": rule.description})
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
    for r in history:
        key = (r["source"], r["key"])
        # Equal capture times with different versions are ambiguous, not ordered by arrival.
        rank = (r.get("published_at") or "", r["captured_at"])
        old = latest.get(key)
        if old is None or rank > old[0]:
            latest[key] = (rank, [r])
        elif rank == old[0]:
            old[1].append(r)
    readings, questions = [], []
    for _, versions in sorted(latest.values(), key=lambda x: canonical(x[1])):
        for r in versions:
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
        q["since"] = by_id[q["observation"]]["captured_at"]
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
        return canonical({k: q[k] for k in ("observation", "reason", "status")})
    previous_questions = {question_key(q) for q in (previous or {}).get("open_questions", [])}
    questions = {question_key(q) for q in current["open_questions"]}
    return {"observations_added": sorted(new - old),
            "readings_added": sorted(readings - previous_readings),
            "readings_superseded": sorted(previous_readings - readings),
            "questions_opened": sorted(questions - previous_questions),
            "questions_closed": sorted(previous_questions - questions)}
