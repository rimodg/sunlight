"""Offline tests. All parties, records, dates and URLs below are synthetic."""
import itertools
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from watch_identity import normalise, resolve
from watch_journal import Journal


def observation(oid, identifiers, name="Synthetic company"):
    return {"id": oid, "parties": [{"name": name, "identifiers": [
        {"scheme": s, "value": v, "locator": "/parties/0/identifier"} for s, v in identifiers]}]}


class IdentityTests(unittest.TestCase):
    def test_numeric_padding(self):
        self.assertEqual(normalise("GB-COH", "123456"), "00123456")
        self.assertEqual(normalise("GB-COH", "00123456"), "00123456")

    def test_each_prefix(self):
        for prefix in ["OC", "RC", "FC", "SC", "NI"]:
            with self.subTest(prefix=prefix):
                self.assertEqual(normalise("GB-COH", prefix + "123456"), prefix + "123456")

    def test_no_repair_or_unknown_authority(self):
        for value in [" 123456", "oc123456", "123456789", 123456, "１２３", "OC1234"]:
            self.assertIsNone(normalise("GB-COH", value))
        self.assertIsNone(normalise("unknown", "123456"))

    def test_order_independent_transitive_identity(self):
        rows = [observation("a", [("GB-COH", "123456")]),
                observation("b", [("GB-COH", "00123456"), ("GB-COH", "OC123456")]),
                observation("c", [("GB-COH", "OC123456")])]
        expected = resolve(rows)
        self.assertEqual(len(expected), 1)
        self.assertEqual(expected[0]["observations"], ["a", "b", "c"])
        for ordering in itertools.permutations(rows):
            self.assertEqual(resolve(ordering), expected)
        mappings = next(c for c in expected[0]["citations"] if c["observation"] == "a")["identifiers"]
        self.assertEqual(mappings[0]["published_value"], "123456")
        self.assertEqual(mappings[0]["normalised_value"], "00123456")

    def test_same_name_never_merges(self):
        rows = [observation("a", []), observation("b", [])]
        self.assertEqual(len(resolve(rows)), 2)
        self.assertTrue(all(s["state"] == "unresolved" for s in resolve(rows)))

    def test_identifier_without_locator_does_not_join(self):
        row = observation("a", [("GB-COH", "123456")])
        row["parties"][0]["identifiers"][0]["locator"] = None
        self.assertEqual(resolve([row])[0]["state"], "unresolved")


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "journal.sqlite3"
        self.j = Journal(self.path)

    def tearDown(self):
        self.j.close(); self.temp.cleanup()

    def test_capture_keeps_exact_bytes_and_idempotent_retry(self):
        body = b'{"releases": [ ]}\n'
        cid = self.j.freeze("synthetic", "https://example.invalid/data", "2026-01-01T00:00:00Z", body, "0" * 64)
        self.assertEqual(self.j.capture(cid)["body"].encode(), body)
        self.assertEqual(self.j.freeze("synthetic", "https://example.invalid/data", "2026-01-01T00:00:00Z", body, "0" * 64), cid)
        self.assertEqual(len(self.j.events()), 1)
        self.j.verify()

    def test_append_only_and_readonly(self):
        self.j.append("receipt", "2026-01-01T00:00:00Z", {"state": "unavailable"})
        for sql in ["DELETE FROM watch_events", "UPDATE watch_events SET at='later'"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.j.db.execute(sql)
        other = Journal(self.path, readonly=True)
        try:
            self.assertEqual(len(other.events()), 1)
            with self.assertRaises(sqlite3.OperationalError):
                other.append("receipt", "2026-01-02T00:00:00Z", {})
        finally:
            other.close()

    def test_cutoff_and_timezone(self):
        self.j.append("receipt", "2026-01-01T01:00:00+01:00", {})
        self.j.append("receipt", "2026-01-02T00:00:00Z", {})
        self.assertEqual(len(self.j.events(as_of="2026-01-01T00:00:00Z")), 1)
        with self.assertRaises(ValueError):
            self.j.append("receipt", "2026-01-01", {})

    def test_personal_data_is_rejected_before_capture(self):
        for data in [{"email": "redacted"}, {"contactPoint": {}}, {"name": "person@example.invalid"}]:
            with self.assertRaises(ValueError):
                self.j.freeze("synthetic", "https://example.invalid", "2026-01-01T00:00:00Z", json.dumps(data).encode(), "0" * 64)
        self.assertEqual(self.j.events(), [])

    def test_integrity_detects_tampering(self):
        self.j.append("receipt", "2026-01-01T00:00:00Z", {})
        self.j.db.execute("DROP TRIGGER watch_no_update")
        self.j.db.execute("UPDATE watch_events SET payload='{} ' ")
        self.j.db.execute("UPDATE watch_events SET at='2026-01-02'")
        with self.assertRaises(ValueError):
            self.j.verify()


if __name__ == "__main__":
    unittest.main()
