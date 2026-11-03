"""Synthetic transport tests, never requests to public endpoints."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from watch_capture import adapt, policy
from watch_engine import WatchEngine, snapshot
from watch_examination import changes, procurement
from watch_health import health
from watch_identity import canonical
from watch_journal import Journal

CF = {"id": "synthetic-cf", "adapter": "contracts_finder", "url": "https://example.invalid/ocds?limit=100",
      "interval_seconds": 60, "organisation_only_reviewed": True}
IATI = {"id": "synthetic-iati", "adapter": "iati_dportal", "url": "https://example.invalid/q?reporting_ref_like=GB-COH-%25",
        "interval_seconds": 60, "organisation_only_reviewed": True}


def release(amount=100):
    return {"id": "synthetic-release", "ocid": "synthetic-contract", "date": "2026-01-01T00:00:00Z",
            "parties": [{"id": "supplier-a", "roles": ["supplier"],
                         "identifier": {"scheme": "GB-COH", "id": "123456"}}],
            "awards": [{"value": {"amount": amount, "currency": "GBP"}}]}


def response(data, status=200, **kw):
    return {"body": json.dumps(data).encode(), "status": status, **kw}


def reader(record):
    return [{"rule": "SYNTHETIC-001", "dimension": "synthetic", "status": "INDICATOR",
             "citation": "Synthetic test provision", "description": "Test reading"}]


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.j = Journal(Path(self.temp.name) / "journal.sqlite3")
        self.time = "2026-01-02T00:00:00Z"

    def tearDown(self):
        self.j.close(); self.temp.cleanup()

    def engine(self, transport, sources=None):
        return WatchEngine(self.j, {"schema": "sunlight.watch-source-policy.v1", "sources": sources or [CF]},
                           transport=transport, clock=lambda: self.time, reader=reader)

    def test_two_categories_one_party_and_automatic_real_shape_change(self):
        amount = [100]
        def transport(url):
            if "/q?" in url:
                return response({"rows": [{"aid": "synthetic-activity", "reporting_ref": "GB-COH-00123456"}]})
            return response({"releases": [release(amount[0])]})
        engine = self.engine(transport, [CF, IATI])
        first = engine.tick()
        self.assertEqual(len(first["subjects"]), 1)
        self.assertEqual(first["subjects"][0]["categories"], ["aid", "procurement"])
        first_bytes = canonical(snapshot(self.j, self.time, reader=reader))
        self.time = "2026-01-02T00:01:01Z"; amount[0] = 150
        second = engine.tick()
        self.assertEqual(len(second["observations"]), 3)
        self.assertEqual(len(changes(first, second)["observations_added"]), 1)
        self.assertEqual(canonical(snapshot(self.j, "2026-01-02T00:00:00Z", reader=reader)), first_bytes)
        self.assertTrue(self.j.events(kind="examination")[-1]["payload"]["changes"]["readings_superseded"])

    def test_resume_after_restart_pages_without_restarting_at_first(self):
        calls = []
        next_url = CF["url"] + "&cursor=two"
        def transport(url):
            calls.append(url)
            return response({"releases": [release()], "links": {"next": next_url}}) if len(calls) == 1 else response({"releases": []})
        self.engine(transport).tick()
        self.time = "2026-01-02T00:00:01Z"
        self.engine(transport).tick()
        self.assertEqual(calls, [CF["url"], next_url])
        self.assertTrue(self.j.events(kind="source_state")[-1]["payload"]["cycle_complete"])

    def test_429_is_reached_backoff_and_last_good_survives(self):
        engine = self.engine(lambda url: response({"releases": [release()]}))
        engine.tick()
        good = health(self.j, self.time)["sources"][0]["last_good_capture"]
        self.time = "2026-01-02T00:01:01Z"
        engine.transport = lambda url: response({}, 429, retry_after="120")
        engine.tick()
        h = health(self.j, self.time)
        self.assertEqual(h["scheduler"]["outcome"], "failed")
        self.assertEqual(h["sources"][0]["outcome"], "http_429")
        self.assertEqual(h["sources"][0]["last_good_capture"], good)
        self.assertIsNotNone(h["sources"][0]["last_reached"])
        engine.transport = lambda url: self.fail("Backoff must not call transport")
        self.time = "2026-01-02T00:02:00Z"; engine.tick()

    def test_network_failure_receipt_and_overdue_not_no_data(self):
        def failure(url):
            raise OSError("untrusted body must not enter journal")
        engine = self.engine(failure)
        engine.tick()
        self.time = "2026-01-02T00:02:00Z"
        h = health(self.j, self.time)
        self.assertTrue(h["scheduler"]["overdue"])
        self.assertEqual(h["scheduler"]["outcome"], "failed")
        self.assertTrue(h["sources"][0]["overdue"])
        self.assertIsNone(h["sources"][0]["last_reached"])
        self.assertIsNone(h["sources"][0]["silence_seconds"])
        self.assertNotIn("untrusted", canonical(self.j.events()))

    def test_unchanged_capture_does_not_invent_observation_change(self):
        engine = self.engine(lambda url: response({"releases": [release()]}))
        first = engine.tick()
        self.time = "2026-01-02T00:01:01Z"
        second = engine.tick()
        self.assertEqual(changes(first, second)["observations_added"], [])
        self.assertEqual(changes(first, second)["readings_added"], [])

    def test_protection_failure_retains_receipt_but_no_body(self):
        row = release(); row["parties"][0]["contactPoint"] = {"name": "redacted"}
        self.engine(lambda url: response({"releases": [row]})).tick()
        self.assertEqual(self.j.events(kind="capture"), [])
        self.assertEqual(health(self.j, self.time)["sources"][0]["outcome"], "admission_or_adapter_failed")

    def test_unsafe_paging_and_cycles_do_not_admit_capture(self):
        for url in ["https://other.invalid/ocds?limit=100", CF["url"]]:
            self.time = "2026-01-02T00:01:02Z" if url == CF["url"] else self.time
            self.engine(lambda u: response({"releases": [], "links": {"next": url}})).tick()
            self.assertEqual(self.j.events(kind="capture"), [])

    def test_bad_policy_refused(self):
        for source in [{**CF, "organisation_only_reviewed": False}, {**CF, "url": "http://example.invalid"},
                       {**CF, "url": "https://example.invalid/ocds?limit=1000"}, {**IATI, "url": "https://example.invalid/q"}]:
            with self.assertRaises(ValueError):
                policy({"schema": "sunlight.watch-source-policy.v1", "sources": [source]})

    def test_record_moving_page_position_is_not_new_observation(self):
        a = release(); b = {**release(), "ocid": "synthetic-other", "id": "other"}
        first, _ = adapt(CF, json.dumps({"releases": [a, b]}).encode())
        second, _ = adapt(CF, json.dumps({"releases": [b, a]}).encode())
        self.assertEqual(first[0]["id"], second[1]["id"])

    def test_unknown_reach_and_unfinished_scheduler(self):
        h = health(self.j, self.time, {"sources": [CF]})
        self.assertEqual(h["scheduler"]["outcome"], "never_recorded")
        self.assertIsNone(h["sources"][0]["overdue"])
        self.j.append("scheduler_started", self.time, {"interval_seconds": 60, "build": {"synthetic": True}})
        h = health(self.j, "2026-01-02T00:01:01Z")
        self.assertEqual(h["scheduler"]["outcome"], "unfinished")
        self.assertTrue(h["scheduler"]["overdue"])

    def test_existing_procurement_rule_family_is_used(self):
        outputs = procurement(release())
        self.assertGreater(len(outputs), 10)
        self.assertTrue(all(o["citation"] and o["rule"] for o in outputs))

    def test_frozen_packet_replays_byte_for_byte_and_rejects_tamper(self):
        from watch_packet import packet, replay
        engine = self.engine(lambda url: response({"releases": [release()]}))
        result = engine.tick()
        eid = self.j.events(kind="examination")[-1]["id"]
        value = packet(self.j, eid)
        self.assertEqual(canonical(replay(value, reader=reader)), canonical(result))
        bad = copy.deepcopy(value)
        bad["inputs"][0]["payload"]["body"] = '{}'
        with self.assertRaises(ValueError):
            replay(bad, reader=reader)

    def test_no_clock_or_network_on_replay(self):
        from watch_packet import packet, replay
        engine = self.engine(lambda url: response({"releases": [release()]}))
        engine.tick()
        value = packet(self.j, self.j.events(kind="examination")[-1]["id"])
        engine.transport = lambda u: self.fail("Replay called transport")
        engine.clock = lambda: self.fail("Replay called wall clock")
        self.assertEqual(canonical(replay(value, reader=reader)), canonical(replay(value, reader=reader)))


if __name__ == "__main__":
    unittest.main()
