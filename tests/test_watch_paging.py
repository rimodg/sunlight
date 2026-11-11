"""Rate limit and durable cursor proofs, using synthetic transport only."""
import json
from pathlib import Path

from watch_engine import WatchEngine, retry_delay
from watch_journal import Journal
from tests.test_watch_loop import CF, IATI, release, response, reader


def test_retry_after_never_shortens_exponential_wait_and_handles_http_date():
    at = "2026-01-02T00:00:00Z"
    assert retry_delay(0, "120", at) == 120
    assert retry_delay(3, "1", at) == 480
    assert retry_delay(0, "Fri, 02 Jan 2026 00:03:00 GMT", at) == 180
    assert retry_delay(0, "172800", at) == 172800
    assert retry_delay(2, "invalid", at) == 240


def test_cursor_survives_close_reopen_and_429(tmp_path):
    path = tmp_path / "journal.sqlite3"
    following = CF["url"] + "&cursor=second"
    pol = {"schema": "sunlight.watch-source-policy.v1", "sources": [CF]}
    j = Journal(path)
    WatchEngine(j, pol, clock=lambda: "2026-01-02T00:00:00Z", reader=reader,
                transport=lambda u: response({"releases": [release()], "links": {"next": following}})).tick(examine=False)
    assert not j.events(kind="examination")
    j.close()
    j = Journal(path)
    called = []
    def limited(url):
        called.append(url)
        return response({}, status=429, retry_after="120")
    WatchEngine(j, pol, clock=lambda: "2026-01-02T00:00:01Z", transport=limited).tick(examine=False)
    assert called == [following]
    assert j.events(kind="source_state")[-1]["payload"]["next"] == following
    j.close()
    j = Journal(path)
    def final(url):
        called.append(url)
        return response({"releases": []})
    WatchEngine(j, pol, clock=lambda: "2026-01-02T00:01:00Z", transport=final).tick(examine=False)
    assert called == [following]
    WatchEngine(j, pol, clock=lambda: "2026-01-02T00:02:02Z", transport=final).tick(examine=False)
    assert called == [following, following]
    assert j.events(kind="source_state")[-1]["payload"]["cycle_complete"]
    j.close()


def test_dportal_offset_is_checkpointed_using_current_page(tmp_path):
    source = {**IATI, "url": "https://example.invalid/q?reporting_ref_like=GB-COH-%25&select=aid,reporting_ref&limit=1&offset=0&orderby=aid"}
    calls = []
    def transport(url):
        calls.append(url)
        return response({"rows": [{"aid": "activity-" + str(len(calls)), "reporting_ref": "GB-COH-00123456"}] if len(calls) < 3 else []})
    pol = {"schema": "sunlight.watch-source-policy.v1", "sources": [source]}
    for second in range(3):
        j = Journal(tmp_path / "journal.sqlite3")
        WatchEngine(j, pol, clock=lambda: f"2026-01-02T00:00:0{second}Z", transport=transport).tick(examine=False)
        if second == 2:
            assert j.events(kind="source_state")[-1]["payload"]["cycle_complete"]
        j.close()
    assert ["offset=" + str(i) in u for i, u in enumerate(calls)] == [True, True, True]
