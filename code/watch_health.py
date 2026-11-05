"""Journal queries distinguish a stopped watch from a quiet source."""
from datetime import datetime
from watch_journal import utc


def seconds(now, then):
    return max(0, (datetime.fromisoformat(utc(now)) - datetime.fromisoformat(utc(then))).total_seconds())


def health(journal, now, policy=None, interval=None):
    events = journal.events(as_of=now)
    starts = [e for e in events if e["kind"] == "scheduler_started"]
    last = max(starts, key=lambda e: (e["at"], e["seq"]), default=None)
    ends = [e for e in events if e["kind"] in {"scheduler_completed", "scheduler_failed"} and last and e["payload"]["run"] == last["id"]]
    end = ends[-1] if ends else None
    interval = interval or (last["payload"]["interval_seconds"] if last else None)
    schedule = {"last_started": last["at"] if last else None, "last_finished": end["at"] if end else None,
                "outcome": end["kind"].removeprefix("scheduler_") if end else "unfinished" if last else "never_recorded",
                "interval_seconds": interval, "overdue": seconds(now, last["at"]) > interval if last and interval else None,
                "build": last["payload"]["build"] if last else None,
                "pid": last["payload"].get("pid") if last else None,
                "receipt": (end or last)["id"] if last else None}
    if policy is None:
        configs = [e for e in events if e["kind"] == "source_policy"]
        policy = configs[-1]["payload"]["policy"] if configs else {"sources": []}
    sources = []
    for source in policy["sources"]:
        receipts = [e for e in events if e["kind"] == "source_receipt" and e["payload"]["source"] == source["id"]]
        receipts.sort(key=lambda e: (e["at"], e["seq"]))
        latest = receipts[-1] if receipts else None
        reached = [e for e in receipts if e["payload"].get("reached_at")]
        good = [e for e in receipts if e["payload"].get("capture")]
        last_reach = reached[-1]["payload"]["reached_at"] if reached else None
        anchor = last_reach or (receipts[0]["at"] if receipts else None)
        sources.append({"source": source["id"], "last_attempt": latest["at"] if latest else None,
                        "last_reached": last_reach, "outcome": latest["payload"]["outcome"] if latest else "never_recorded",
                        "silence_seconds": seconds(now, last_reach) if last_reach else None,
                        "interval_seconds": source["interval_seconds"],
                        "overdue": seconds(now, anchor) > source["interval_seconds"] if anchor else None,
                        "last_good_capture": good[-1]["payload"]["capture"] if good else None,
                        "receipt": latest["id"] if latest else None})
    return {"as_of": utc(now), "scheduler": schedule, "sources": sources,
            "note": "Receipts describe recorded runs, not proof that a process is currently alive."}
