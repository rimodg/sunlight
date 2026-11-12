from copy import deepcopy

from scripts.prove_watch_publication import candidates
from watch_identity import digest


def inputs():
    source = {"id": "cf", "adapter": "contracts_finder", "url": "https://example.invalid/query"}
    before = {"url": source["url"], "policy_hash": digest(source), "adapter_version": "v1",
              "captured_at": "2026-11-12T10:00:00+00:00", "projection": {"next": None, "refusals": []}}
    after = {**deepcopy(before), "captured_at": "2026-11-12T11:00:00+00:00"}
    row = {"key": "new-notice", "id": "new-observation", "published_at": "2026-11-12T10:30:00+00:00"}
    return before, after, [], [row], source, {"new-observation"}


def test_new_notice_requires_timestamp_after_baseline_and_recorded_notice():
    args = inputs()
    assert candidates(*args) == args[3]
    assert candidates(*args[:-1], set()) == []
    for published in [None, "2026-11-12T09:59:59+00:00", "2026-11-12T11:00:01+00:00"]:
        changed = deepcopy(args)
        changed[3][0]["published_at"] = published
        assert candidates(*changed) == []


def test_partial_or_refused_baseline_and_changed_query_cannot_prove_absence():
    for target, field, value in [(0, "url", "https://example.invalid/query?cursor=last"),
                                  (1, "policy_hash", "different"), (1, "adapter_version", "v2")]:
        args = inputs()
        args[target][field] = value
        assert candidates(*args) == []
    for target in [0, 1]:
        for field, value in [("next", "https://example.invalid/next"), ("refusals", [{"field": "/id"}])]:
            args = inputs()
            args[target]["projection"][field] = value
            assert candidates(*args) == []


def test_existing_record_is_not_a_new_publication():
    args = inputs()
    args[2].append({"key": "new-notice"})
    assert candidates(*args) == []
