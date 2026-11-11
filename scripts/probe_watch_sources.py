#!/usr/bin/env python3
"""One explicitly reviewed page per source. Retain projections, never raw bodies."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from watch_capture import fetch, policy
from watch_engine import WatchEngine, now
from watch_identity import canonical
from watch_journal import Journal
from watch_packet import packet, replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()
    data = Path(args.data_dir).expanduser().resolve()
    if data == ROOT or ROOT in data.parents:
        parser.error("Probe artifacts must be outside the repository")
    data.mkdir(parents=True, exist_ok=True)
    if (data / "journal.sqlite3").exists():
        parser.error("Use a fresh probe directory; previous evidence is preserved")
    pol = policy(json.loads(Path(args.policy).read_text()))
    measurements = {}
    def transport(url):
        response = fetch(url)
        measurements[url] = {"http_status": response["status"], "response_bytes": len(response["body"])}
        return response
    journal = Journal(data / "journal.sqlite3")
    try:
        result = WatchEngine(journal, pol, transport=transport).tick()
        sources = []
        for receipt in journal.events(kind="source_receipt"):
            r = receipt["payload"]
            item = {"source": r["source"], "outcome": r["outcome"], "http_status": r["http_status"],
                    "admitted": r.get("admitted_count"), "refusals": r.get("refusals", [])}
            if r["capture"]:
                capture = journal.capture(r["capture"])
                projection = capture["projection"]
                item.update(url=capture["url"], capture=r["capture"], source_sha256=capture["sha256"],
                            projection_sha256=capture["projection_sha256"], adapter_version=capture["adapter_version"],
                            received=projection["received_count"], refused=len(projection["refusals"]),
                            response_bytes=measurements[capture["url"]]["response_bytes"],
                            projection_bytes=len(canonical(projection).encode()),
                            capture_payload_bytes=len(canonical(capture).encode()),
                            next_page_pending=projection["next"] is not None)
                item["refusal_counts"] = dict(Counter(x["reason"] for x in projection["refusals"]))
            sources.append(item)
        eid = journal.events(kind="examination")[-1]["id"]
        value = packet(journal, eid)
        if canonical(replay(value)) != canonical(result):
            raise ValueError("probe_replay_mismatch")
        (data / "packet.json").write_text(canonical(value) + "\n")
        summary = {"at": now(), "scope": "One page per reviewed source; not population or unattended acceptance",
                   "build": value["examination"]["payload"]["build"], "sources": sources,
                   "projection_replay": "passed", "original_bodies_retained": False,
                   "journal_head": journal.verify()}
        (data / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        if any(x["admitted"] is None or x["admitted"] == 0 for x in sources):
            return 1
        return 0
    finally:
        journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
