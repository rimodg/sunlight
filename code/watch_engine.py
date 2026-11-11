"""Continuous watch: capture, resolve, append, examine, compare, repeat."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from watch_capture import records_from_projection, fetch, frozen_records, policy, checked_url
from watch_examination import examine, changes
from watch_health import health
from watch_identity import canonical, digest
from watch_journal import Journal, utc


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def build_identity(root=None):
    root = Path(root or Path(__file__).resolve().parents[1])
    files = sorted((root / "code").glob("*.py")) + [root / "requirements.lock"]
    files += sorted((root / "code").glob("*.json"))
    # This is executable rule data, not an operator capture or acceptance feed.
    # Missing or changed calibration input must not hide behind unchanged code.
    files += [root / "research/corpus/prosecuted_cases_global_v0.1.json"]
    files += sorted((root / "data/cpd_profiles").glob("*.json"))
    files += sorted((root / "data/evidence_maps").glob("*.json"))
    files += [root / p for p in ["scripts/watch_service.py", "scripts/run_watch_service.py",
                                "scripts/watch-service", "scripts/install-watch", "scripts/uninstall-watch",
                                "config/watch-runtime.json", "deploy/launchd/org.sunlight.watch.plist"] if (root / p).exists()]
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    import platform
    return {"git_commit": commit, "source_sha256": digest(hashes), "python": platform.python_version(),
            "lock_sha256": hashes["requirements.lock"]}


def snapshot(journal, as_of, *, reader=None):
    journal.verify()
    records = []
    for event in journal.events(as_of=as_of, kind="observations"):
        p = event["payload"]
        capture = journal.capture(p["capture"])
        reproduced, next_url = records_from_projection(p["source_policy"], capture["projection"])
        if reproduced != p["records"] or next_url != p["next"]:
            raise ValueError("adapter_replay_mismatch")
        for row in p["records"]:
            records.append({**row, "captured_at": event["at"],
                            "evidence": {"capture": p["capture"], "sha256": capture["sha256"],
                                         "projection_sha256": capture["projection_sha256"],
                                         "url": capture["url"], "locator": row["locator"]}})
    kwargs = {"procurement_reader": reader} if reader is not None else {}
    return examine(records, as_of, **kwargs)


class WatchEngine:
    def __init__(self, journal, source_policy, *, interval=60, transport=fetch, clock=now, reader=None):
        self.journal = journal
        self.policy = policy(source_policy)
        if not isinstance(interval, int) or interval < 1:
            raise ValueError("invalid_scheduler_interval")
        self.interval, self.transport, self.clock, self.reader = interval, transport, clock, reader
        self.build = build_identity()  # Frozen at startup, not a later request's HEAD.
        self.journal.verify()

    def tick(self):
        # A crashed process releases the OS lock. Manual ticks cannot race the
        # service into duplicate captures or contradictory cursor updates.
        import fcntl
        with open(self.journal.path.with_suffix(".lock"), "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                return self._tick()
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _tick(self):
        at = utc(self.clock())
        run = self.journal.append("scheduler_started", at, {"interval_seconds": self.interval, "build": self.build,
                                                           "pid": os.getpid()})
        self.journal.append("source_policy", at, {"policy": self.policy})
        failed = False
        try:
            if build_identity()["source_sha256"] != self.build["source_sha256"]:
                raise ValueError("running_source_drift")
            for source in self.policy["sources"]:
                states = [e for e in self.journal.events(kind="source_state")
                          if e["payload"]["source"] == source["id"] and e["payload"]["policy_hash"] == digest(source)]
                state = states[-1]["payload"] if states else {}
                if state.get("due") and utc(state["due"]) > at:
                    continue
                url = state.get("next") or source["url"]
                reached, status, capture_id = None, None, None
                admitted_count, refusals = None, []
                outcome, retry = "unavailable", min(86400, 60 * 2 ** min(10, state.get("failures", 0)))
                try:
                    checked_url(url, source["url"])
                    response = self.transport(url)
                    reached = utc(self.clock())
                    status = response["status"]
                    if response.get("read_failed"):
                        raise ValueError("response_body_read_failed")
                    if status != 200:
                        hint = response.get("retry_after")
                        retry = max(60, min(86400, int(hint))) if hint and str(hint).isdigit() else min(86400, 60 * 2 ** min(10, state.get("failures", 0)))
                        outcome = "http_" + str(status)
                        raise ValueError("http_failure")
                    seen = state.get("seen", [])
                    capture_id, records, next_url = frozen_records(self.journal, source, url, reached, response["body"], digest(source), seen)
                    admitted_count = len(records)
                    refusals = self.journal.capture(capture_id)["projection"]["refusals"]
                    due = reached if next_url else (datetime.fromisoformat(reached) + timedelta(seconds=source["interval_seconds"])).isoformat()
                    self.journal.append("source_state", reached, {"source": source["id"], "policy_hash": digest(source),
                                        "next": next_url, "due": due, "seen": (seen + [url]) if next_url else [],
                                        "failures": 0, "cycle_complete": next_url is None})
                    outcome = "captured_with_refusals" if refusals else "captured"
                except Exception:
                    failed = True
                    # No source text, exception body or untrusted payload in failure receipts.
                    if status == 200:
                        outcome = "admission_or_adapter_failed"
                    due = (datetime.fromisoformat(at) + timedelta(seconds=retry)).isoformat()
                    self.journal.append("source_state", at, {**state, "source": source["id"], "policy_hash": digest(source),
                                        "due": due, "failures": state.get("failures", 0) + 1, "cycle_complete": False})
                self.journal.append("source_receipt", utc(self.clock()), {"source": source["id"], "outcome": outcome,
                                    "reached_at": reached, "http_status": status, "capture": capture_id,
                                    "admitted_count": admitted_count, "refusals": refusals})
            cutoff = utc(self.clock())
            current = snapshot(self.journal, cutoff, reader=self.reader)
            previous = self.journal.events(kind="examination")
            delta = changes(previous[-1]["payload"]["result"] if previous else None, current)
            self.journal.append("examination", cutoff, {"result": current, "changes": delta,
                                "policy_hash": digest(self.policy), "build": self.build})
        except Exception:
            self.journal.append("scheduler_failed", utc(self.clock()), {"run": run, "reason": "watch_execution_failed"})
            raise
        self.journal.append("scheduler_failed" if failed else "scheduler_completed", utc(self.clock()),
                            {"run": run, "reason": "source_failure" if failed else "completed"})
        return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--replay", metavar="AS_OF")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--packet", metavar="EXAMINATION_ID")
    parser.add_argument("--verify-packet", metavar="PATH")
    args = parser.parse_args()
    data = Path(args.data_dir).expanduser().resolve()
    root = Path(__file__).resolve().parents[1]
    if data == root or root in data.parents:
        parser.error("Operational data must be outside the repository")
    pol = policy(json.loads(Path(args.policy).read_text()))
    if args.verify_packet:
        from watch_packet import replay
        print(canonical(replay(json.loads(Path(args.verify_packet).read_text()))))
        return
    journal = Journal(data / "journal.sqlite3", readonly=bool(args.replay or args.health or args.packet))
    try:
        if args.replay:
            print(canonical(snapshot(journal, args.replay)))
            return
        if args.health:
            print(canonical(health(journal, now(), pol, args.interval)))
            return
        if args.packet:
            from watch_packet import packet
            print(canonical(packet(journal, args.packet)))
            return
        engine = WatchEngine(journal, pol, interval=args.interval)
        while True:
            try:
                engine.tick()
                failed = health(journal, now())["scheduler"]["outcome"] == "failed"
                print(canonical({"event": "watch_tick_failed" if failed else "watch_tick_recorded", "at": now()}), flush=True)
                if args.once and failed:
                    raise SystemExit(1)
            except Exception:
                print(canonical({"event": "watch_tick_failed", "at": now()}), flush=True)
                if args.once:
                    raise SystemExit(1)
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        journal.close()


if __name__ == "__main__":
    main()
