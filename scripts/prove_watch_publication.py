#!/usr/bin/env python3
"""Prove a newly published notice after a complete one-page query baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    preliminary = argparse.ArgumentParser(add_help=False)
    preliminary.add_argument("--engine-root", type=Path, default=ROOT)
    ENGINE_ROOT = preliminary.parse_known_args()[0].engine_root.resolve()
else:
    ENGINE_ROOT = ROOT
sys.path.insert(0, str(ENGINE_ROOT / "code"))
from watch_identity import canonical, digest
from watch_journal import Journal, utc
from watch_packet import packet, replay


def candidates(before, after, old_rows, new_rows, source, noticed):
    """Partial pages, first discovery and changed source policies are not proof."""
    if source["adapter"] != "contracts_finder":
        return []
    for capture in [before, after]:
        if (capture["url"] != source["url"] or capture["policy_hash"] != digest(source)
                or capture["projection"]["next"] is not None or capture["projection"]["refusals"]):
            return []
    if before["adapter_version"] != after["adapter_version"]:
        return []
    old_keys = {r["key"] for r in old_rows}
    start, end = utc(before["captured_at"]), utc(after["captured_at"])
    return [r for r in new_rows if r["key"] not in old_keys and r["id"] in noticed
            and r.get("published_at") and start < utc(r["published_at"]) <= end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--journal", required=True)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--engine-root", type=Path, default=ROOT,
                   help="Installed immutable checkout whose rule build produced the examinations")
    args = p.parse_args()
    data = Path(args.data_dir).expanduser().resolve()
    if any(data == root or root in data.parents for root in [ROOT, ENGINE_ROOT]) or data.exists():
        p.error("Use a fresh external evidence directory")
    j = Journal(args.journal, readonly=True)
    try:
        j.db.execute("BEGIN")
        head = j.verify()
        observations = j.events(kind="observations")
        examinations = j.events(kind="examination")
        previous = {}
        for event in observations:
            source = event["payload"]["source_policy"]
            old = previous.get(source["id"])
            previous[source["id"]] = event
            if old is None or old["payload"]["source_policy"] != source:
                continue
            before_id, after_id = old["payload"]["capture"], event["payload"]["capture"]
            before, after = j.capture(before_id), j.capture(after_id)
            old_exams = [e for e in examinations if old["seq"] < e["seq"] < event["seq"]]
            if not old_exams:
                continue
            before_exam = old_exams[-1]
            for after_exam in (e for e in examinations if e["seq"] > event["seq"]):
                found = candidates(before, after, old["payload"]["records"], event["payload"]["records"],
                                   source, after_exam["payload"]["changes"]["observations_added"])
                if not found:
                    continue
                row = sorted(found, key=lambda r: (r["published_at"], r["key"]))[0]
                baseline_rows = before_exam["payload"]["result"]["observations"]
                if any(r["source"] == source["id"] and r["key"] == row["key"] for r in baseline_rows):
                    continue
                data.mkdir(parents=True)
                packets = {}
                for label, exam in [("before", before_exam), ("after", after_exam)]:
                    value = packet(j, exam["id"])
                    if canonical(replay(value)) != canonical(exam["payload"]["result"]):
                        raise ValueError("Publication packet replay mismatch")
                    raw = (canonical(value) + "\n").encode()
                    (data / (label + "-packet.json")).write_bytes(raw)
                    packets[label] = {"examination": exam["id"], "packet_sha256": hashlib.sha256(raw).hexdigest()}
                proof = {
                    "kind": "newly_published_notice", "source_policy": source, "key": row["key"],
                    "before": {"capture": before_id, "captured_at": before["captured_at"],
                               "presence": "absent_from_completed_query", "received_count": before["projection"]["received_count"],
                               "source_sha256": before["sha256"], "projection_sha256": before["projection_sha256"]},
                    "after": {"capture": after_id, "captured_at": after["captured_at"],
                              "received_count": after["projection"]["received_count"], "observation": row,
                              "source_sha256": after["sha256"], "projection_sha256": after["projection_sha256"]},
                    "packets": packets, "packet_replay": "both_passed", "journal_head": head,
                    "replay_engine_root": str(ENGINE_ROOT), "recorded_build": after_exam["payload"]["build"],
                    "qualification": "The publisher-supplied timestamp is after the complete one-page baseline and before capture. The scheduled loop recorded the added observation. This proves a newly published notice in this query, not an edit to an existing notice, absence from all procurement, or independently authenticated publisher time. Personal fields and original response bodies remain excluded."}
                (data / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
                print(json.dumps({"key": row["key"], "published_at": row["published_at"],
                                  "before": before["captured_at"], "after": after["captured_at"],
                                  "packet_replay": "both_passed", "examination": after_exam["id"]}, indent=2))
                return
        raise ValueError("No qualifying published notice found; gate remains open")
    finally:
        j.close()


if __name__ == "__main__":
    main()
