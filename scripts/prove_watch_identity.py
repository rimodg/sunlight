#!/usr/bin/env python3
"""Join one captured procurement identifier to a live IATI activity reference."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from watch_engine import WatchEngine
from watch_identity import canonical, normalise
from watch_journal import Journal
from watch_packet import packet, replay


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--procurement-journal", required=True)
    p.add_argument("--registry-id", required=True)
    p.add_argument("--reporting-ref", required=True)
    p.add_argument("--data-dir", required=True)
    args = p.parse_args()
    key = normalise("GB-COH", args.registry_id)
    if not key or not args.reporting_ref.startswith("GB-COH-") or normalise("GB-COH", args.reporting_ref[7:]) != key:
        p.error("Both published registry references must normalize to the same GB-COH identifier")
    data = Path(args.data_dir).expanduser().resolve()
    if data == ROOT or ROOT in data.parents or (data / "journal.sqlite3").exists():
        p.error("Use a fresh external proof directory")
    original = Journal(args.procurement_journal, readonly=True)
    try:
        original.verify()
        event = next((e for e in original.events(kind="observations") if any(
            row["category"] == "procurement" and any(
                i.get("scheme") == "GB-COH" and i.get("normalised_value") == key
                for party in row["parties"] for i in party["identifiers"])
            for row in e["payload"]["records"])), None)
        if event is None:
            raise ValueError("No cited procurement occurrence of the requested registry identifier")
        capture = next(e for e in original.events(kind="capture") if e["id"] == event["payload"]["capture"])
    finally:
        original.close()
    query = urlencode({"from": "act", "select": "aid,reporting_ref", "reporting_ref_like": "GB-COH-%",
                       "reporting_ref": args.reporting_ref, "limit": 100, "offset": 0,
                       "orderby": "aid", "form": "json"})
    source = {"id": "dportal-identity-proof", "adapter": "iati_dportal", "url": "https://d-portal.org/q?" + query,
              "interval_seconds": 3600, "organisation_only_reviewed": True, "page_limit": 100}
    j = Journal(data / "journal.sqlite3")
    try:
        for e in (capture, event):
            if j.append(e["kind"], e["at"], e["payload"]) != e["id"]:
                raise ValueError("Copied evidence identity mismatch")
        result = WatchEngine(j, {"schema": "sunlight.watch-source-policy.v1", "sources": [source]}).tick()
        subject = next((s for s in result["subjects"] if ["GB-COH", key] in [list(x) for x in s["identifiers"]]
                        and s["categories"] == ["aid", "procurement"]), None)
        if subject is None:
            raise ValueError("Live cited-identifier join not demonstrated")
        relevant = [r for r in result["observations"] if r["id"] in subject["observations"]]
        proof = {"subject": subject, "observations": relevant,
                 "basis": "Published organizational identifiers and source locators only; no names were retained or compared",
                 "limits": "A shared cited identifier is not beneficial-ownership verification, a labor finding or evidence of a money flow."}
        value = packet(j, j.events(kind="examination")[-1]["id"])
        if canonical(replay(value)) != canonical(result):
            raise ValueError("Identity packet replay mismatch")
        (data / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
        (data / "packet.json").write_text(canonical(value) + "\n")
        print(json.dumps({"registry_id": key, "subject_id": subject["id"], "categories": subject["categories"],
                          "observation_count": len(relevant), "packet_replay": "passed",
                          "procurement_capture": capture["id"],
                          "aid_capture": j.events(kind="source_receipt")[-1]["payload"]["capture"]}, indent=2))
    finally:
        j.close()


if __name__ == "__main__":
    main()
