from copy import deepcopy

from scripts.report_watch_run import summarize


def cycle(row, at, capture):
    return [
        {"kind": "observations", "at": at, "payload": {"records": [row], "capture": capture}},
        {"kind": "source_state", "at": at, "payload": {"source": "source", "cycle_complete": True}},
    ]


def row():
    return {"source": "source", "key": "contract", "id": "v1", "locator": "/releases/0",
            "published_at": "2026-11-12T09:00:00+00:00", "record": {"value": 100}}


def test_page_movement_and_initial_discovery_are_not_published_changes():
    first = row()
    moved = {**first, "id": "moved", "locator": "/releases/9"}
    events = cycle(first, "2026-11-12T10:00:00+00:00", "c1")
    events += cycle(moved, "2026-11-12T11:00:00+00:00", "c2")
    notices = [{"id": "exam", "at": "2026-11-12T11:01:00+00:00",
                "changes": {"observations_added": ["v1", "moved"]}}]
    assert summarize(events, notices)["published_change_proofs"] == []
    assert summarize(events, notices)["full_day_elapsed"] is False


def test_changed_record_requires_publication_advance_and_loop_notice():
    before = row()
    after = {**before, "id": "v2", "published_at": "2026-11-12T10:30:00+00:00", "record": {"value": 90}}
    events = cycle(before, "2026-11-12T10:00:00+00:00", "c1")
    events += cycle(after, "2026-11-12T11:00:00+00:00", "c2")
    assert summarize(events, [])["published_change_proofs"] == []
    notices = [{"id": "exam", "at": "2026-11-12T11:01:00+00:00",
                "changes": {"observations_added": ["v2"]}}]
    proof = summarize(events, notices)["published_change_proofs"][0]
    assert proof["before"]["capture"] == "c1"
    assert proof["after"]["capture"] == "c2"
    assert proof["examination"] == "exam"
    rollback = deepcopy(events)
    rollback[2]["payload"]["records"][0]["published_at"] = before["published_at"]
    assert summarize(rollback, notices)["published_change_proofs"] == []


def test_day_requires_completed_runs_a_full_day_apart_and_preserves_refusal_reasons():
    events = [{"kind": "scheduler_completed", "at": t, "payload": {}} for t in
              ["2026-11-12T10:00:00+00:00", "2026-11-13T09:59:59+00:00"]]
    events.append({"kind": "source_receipt", "at": "2026-11-13T09:59:50+00:00", "payload": {
        "source": "source", "capture": "c1", "admitted_count": 2, "outcome": "captured_with_refusals",
        "reached_at": "2026-11-13T09:59:50+00:00", "refusals": [{"field": "/id", "reason": "personal_shaped"}]}})
    value = summarize(events, [])
    assert value["full_day_elapsed"] is False
    assert value["sources"]["source"]["refusals"] == {"/id: personal_shaped": 1}
    assert value["sources"]["source"]["silence_at_last_completion_seconds"] == 9
    events[1]["at"] = "2026-11-13T10:00:00+00:00"
    assert summarize(events, [])["full_day_elapsed"] is True
