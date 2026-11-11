#!/usr/bin/env python3
"""Capture one reviewed source cycle, checkpointing each page before continuing.

Uses the service's exact capture, gate, journal and cursor path. This command
does not append repeated full-population examinations during a historical import.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from watch_capture import policy
from watch_engine import WatchEngine, now
from watch_identity import digest
from watch_journal import Journal, utc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", required=True)
    p.add_argument("--data-dir", required=True)
    p.add_argument("--pause-seconds", type=int, default=10)
    p.add_argument("--stop-after-pages", type=int)
    args = p.parse_args()
    if args.pause_seconds < 1 or (args.stop_after_pages is not None and args.stop_after_pages < 1):
        p.error("Positive pacing and stop count required")
    pol = policy(json.loads(Path(args.policy).read_text()))
    if len(pol["sources"]) != 1:
        p.error("One reviewed source per population journal")
    data = Path(args.data_dir).expanduser().resolve()
    if data == ROOT or ROOT in data.parents:
        p.error("Population journal must be outside the repository")
    source = pol["sources"][0]
    j = Journal(data / "journal.sqlite3")
    def state():
        entries = [e["payload"] for e in j.events(kind="source_state")
                   if e["payload"]["source"] == source["id"] and e["payload"]["policy_hash"] == digest(source)]
        return entries[-1] if entries else {}
    try:
        engine = WatchEngine(j, pol)
        checkpoint = state()
        j.append("population_process_started", now(), {"source": source["id"], "build": engine.build,
                 "resume_url": checkpoint.get("next") or source["url"], "resumed": bool(checkpoint)})
        pages = 0
        while not state().get("cycle_complete"):
            checkpoint = state()
            if checkpoint.get("due"):
                wait = (datetime.fromisoformat(utc(checkpoint["due"])) - datetime.fromisoformat(utc(now()))).total_seconds()
                if wait > 0:
                    time.sleep(min(wait, 30))
                    continue
            engine.tick(examine=False)
            receipt = j.events(kind="source_receipt")[-1]["payload"]
            if receipt.get("capture"):
                pages += 1
            summary = {"at": now(), "pages_this_process": pages, "outcome": receipt["outcome"],
                       "admitted": receipt.get("admitted_count"), "refused": len(receipt.get("refusals", [])),
                       "cycle_complete": state().get("cycle_complete", False)}
            print(json.dumps(summary), flush=True)
            if (receipt["outcome"] == "admission_or_adapter_failed"
                    or receipt.get("http_status") in {400, 401, 403, 404}
                    or state().get("failures", 0) >= 5):
                print(json.dumps({"blocked": True, "outcome": receipt["outcome"],
                                  "checkpoint_preserved": True}), flush=True)
                return 2
            if args.stop_after_pages and pages >= args.stop_after_pages and not state().get("cycle_complete"):
                j.append("population_operator_pause", now(), {"source": source["id"], "pages_this_process": pages,
                                                            "next": state()["next"]})
                return 0
            if not state().get("cycle_complete"):
                time.sleep(args.pause_seconds)
        print(json.dumps({"complete": True, "journal_head": j.verify()}), flush=True)
        return 0
    finally:
        j.close()


if __name__ == "__main__":
    raise SystemExit(main())
