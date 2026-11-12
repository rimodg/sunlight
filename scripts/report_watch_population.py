#!/usr/bin/env python3
"""Count observed identifier coverage without joining on names or inventing gaps."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from watch_identity import normalise
from watch_journal import Journal


def registry_identifiers(party):
    identifiers = ([party["identifier"]] if isinstance(party.get("identifier"), dict) else [])
    identifiers += party.get("additionalIdentifiers", [])
    return {(x.get("scheme"), normalise(x.get("scheme"), x.get("id"))) for x in identifiers
            if normalise(x.get("scheme"), x.get("id")) is not None}


def summarize(events):
    captures = [e for e in events if e["kind"] == "capture"]
    received = sum(e["payload"]["projection"]["received_count"] for e in captures)
    refusals = [r for e in captures for r in e["payload"]["projection"]["refusals"]]
    rows = [r for e in events if e["kind"] == "observations" for r in e["payload"]["records"]]
    releases = {}
    for row in rows:
        releases[row["id"]] = row
    schemes = Counter()
    registry = set()
    awards = 0
    registry_awards = 0
    missing_supplier_refs = 0
    missing_award_ids = 0
    cohort_releases = set()
    for row in releases.values():
        for party in row["parties"]:
            for identifier in party["identifiers"]:
                schemes[identifier.get("scheme") or "scheme_not_supplied"] += 1
        raw = row["record"]
        party_map = defaultdict(list)
        for party in raw.get("parties", []):
            if party.get("id"):
                party_map[party["id"]].append(party)
        for award in raw.get("awards", []):
            awards += 1
            if not award.get("id"):
                missing_award_ids += 1
            supplier_ids = set()
            if not award.get("suppliers"):
                missing_supplier_refs += 1
            for supplier in award.get("suppliers", []):
                supplier_ids.update(registry_identifiers(supplier))
                candidates = party_map.get(supplier.get("id"), [])
                if len(candidates) == 1:
                    supplier_ids.update(registry_identifiers(candidates[0]))
            if supplier_ids:
                registry_awards += 1
                registry.update(supplier_ids)
                cohort_releases.add(row["key"])
    states = [e["payload"] for e in events if e["kind"] == "source_state"]
    starts = [e for e in events if e["kind"] == "population_process_started"]
    pauses = [e for e in events if e["kind"] == "population_operator_pause"]
    receipts = [e["payload"] for e in events if e["kind"] == "source_receipt"]
    return {"captured_pages": len(captures), "received_releases": received,
            "admitted_occurrences": len(rows), "distinct_admitted_versions": len(releases),
            "refused_releases": len(refusals),
            "refusal_reasons": dict(Counter(r["reason"] for r in refusals)),
            "identifier_scheme_occurrences": dict(sorted(schemes.items())),
            "admitted_award_rows": awards, "awards_with_supplier_registry_identifier": registry_awards,
            "registry_share_of_admitted_awards": registry_awards / awards if awards else None,
            "award_rows_missing_id": missing_award_ids,
            "awards_missing_supplier_references": missing_supplier_refs,
            "registry_identifiers": sorted(registry), "registry_release_count": len(cohort_releases),
            "cycle_complete": bool(states and states[-1]["cycle_complete"]),
            "http_status_counts": dict(Counter(str(r["http_status"]) for r in receipts)),
            "processes": len(starts),
            "resumed_at_saved_cursor": bool(len(starts) >= 2 and pauses and
                                             starts[1]["payload"]["resume_url"] == pauses[0]["payload"]["next"]),
            "limits": "Award share is among admitted award rows, not refused releases or all procurement. Scheme occurrences include explicit GB-CFS prefixes and buyer identifiers; supplier registry coverage is counted separately. Registry identifiers are potential joins, not proof of an external match. Mutable API traversal is not a publisher snapshot."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--journal", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    output = Path(args.output).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        p.error("Population evidence must remain outside the repository")
    j = Journal(args.journal, readonly=True)
    try:
        value = summarize(j.events())
        value["journal_head"] = j.verify()
        output.write_text(json.dumps(value, indent=2) + "\n")
        print(json.dumps({k: v for k, v in value.items() if k != "registry_identifiers"}, indent=2))
    finally:
        j.close()


if __name__ == "__main__":
    main()
