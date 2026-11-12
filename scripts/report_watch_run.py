#!/usr/bin/env python3
"""Report recorded elapsed time and cited changes, without inventing live uptime."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from watch_identity import canonical
from watch_journal import Journal


def seconds(later, earlier):
    return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()


def selected(rows):
    """Select only a unique latest published value, never page position."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["key"]].append(row)
    result = {}
    for key, versions in groups.items():
        latest = max(r.get("published_at") or "" for r in versions)
        values = {canonical(r["record"]): r for r in versions
                  if (r.get("published_at") or "") == latest}
        if len(values) == 1:
            result[key] = next(iter(values.values()))
    return result


def summarize(events, examinations):
    starts = [e for e in events if e["kind"] == "scheduler_started"]
    completed = [e for e in events if e["kind"] == "scheduler_completed"]
    receipts = [e for e in events if e["kind"] == "source_receipt"]
    pending, previous = defaultdict(list), {}
    changes, sources = [], {}
    for event in events:
        payload = event["payload"]
        if event["kind"] == "observations":
            for row in payload["records"]:
                pending[row["source"]].append({**row, "capture": payload["capture"],
                                               "captured_at": event["at"]})
        elif event["kind"] == "source_state" and payload.get("cycle_complete"):
            source = payload["source"]
            current = selected(pending.pop(source, []))
            old = previous.get(source, {})
            for key in old.keys() & current.keys():
                before, after = old[key], current[key]
                if canonical(before["record"]) == canonical(after["record"]):
                    continue
                # An old version disappearing from mutable pagination is not a
                # demonstrated new publisher update. Require publication advance.
                if not before.get("published_at") or not after.get("published_at"):
                    continue
                if seconds(after["published_at"], before["published_at"]) <= 0:
                    continue
                noticed = next((e["id"] for e in examinations
                                if e["at"] >= after["captured_at"]
                                and after["id"] in e["changes"]["observations_added"]), None)
                if noticed:
                    changes.append({"source": source, "key": key, "before": before,
                                    "after": after, "examination": noticed})
            previous[source] = current
    end = completed[-1]["at"] if completed else None
    elapsed = seconds(end, completed[0]["at"]) if completed else None
    for source in sorted({e["payload"]["source"] for e in receipts}):
        rows = [e for e in receipts if e["payload"]["source"] == source]
        reached = [e["payload"]["reached_at"] for e in rows if e["payload"].get("reached_at")]
        sources[source] = {
            "captures": sum(bool(e["payload"].get("capture")) for e in rows),
            "admitted_occurrences": sum(e["payload"].get("admitted_count") or 0 for e in rows),
            "refusals": dict(Counter((r["field"] + ": " + r["reason"])
                                     for e in rows for r in e["payload"].get("refusals", []))),
            "outcomes": dict(Counter(e["payload"]["outcome"] for e in rows)),
            "last_reached": reached[-1] if reached else None,
            "silence_at_last_completion_seconds": seconds(end, reached[-1]) if end and reached else None,
            "maximum_observed_reach_gap_seconds": max((seconds(b, a) for a, b in zip(reached, reached[1:])), default=None)}
    return {"first_completed_at": completed[0]["at"] if completed else None,
            "last_completed_at": end, "recorded_elapsed_seconds": elapsed,
            "full_day_elapsed": elapsed is not None and elapsed >= 86400,
            "scheduler_completed": len(completed),
            "scheduler_failed": sum(e["kind"] == "scheduler_failed" for e in events),
            "maximum_scheduler_start_gap_seconds": max((seconds(b["at"], a["at"])
                for a, b in zip(starts, starts[1:])), default=None),
            "recorded_builds": [json.loads(x) for x in sorted({canonical(e["payload"]["build"]) for e in starts})],
            "sources": sources, "published_change_proofs": changes,
            "limits": "Elapsed time is not uninterrupted uptime. Counts are repeated admitted occurrences. Silence is measured at the last completed run, not now. An independent native verify receipt is required for current process liveness. Change proofs require completed source cycles, a stable record key, advancing publication time and a recorded examination; new discoveries and page movement are excluded."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("Keep operational reports outside the repository")
    journal = Journal(args.journal, readonly=True)
    try:
        journal.db.execute("BEGIN")
        head = journal.verify()
        kinds = ["scheduler_started", "scheduler_completed", "scheduler_failed", "source_receipt", "observations", "source_state"]
        events = sorted((e for kind in kinds for e in journal.events(kind=kind)), key=lambda e: e["seq"])
        examinations = [{"id": r["id"], "at": r["at"], "changes": json.loads(r["changes"])} for r in journal.db.execute(
            "SELECT id,at,json_extract(payload,'$.changes') AS changes FROM watch_events WHERE kind='examination' ORDER BY seq")]
        result = {**summarize(events, examinations), "journal_head": head}
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({**result, "published_change_proofs": len(result["published_change_proofs"])}, indent=2))
    finally:
        journal.close()


if __name__ == "__main__":
    main()
