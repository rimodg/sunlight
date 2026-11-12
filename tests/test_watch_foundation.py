"""Offline tests. All parties, records, dates and URLs below are synthetic."""
import itertools
import hashlib
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

    def test_capture_keeps_projection_and_original_digest_with_idempotent_retry(self):
        from watch_capture import project_page
        from test_watch_loop import CF
        body = b'{"releases": [ ]}\n'
        projection = project_page(CF, body)
        sha = hashlib.sha256(body).hexdigest()
        cid = self.j.freeze("synthetic", "https://example.invalid/data", "2026-01-01T00:00:00Z", projection, "0" * 64, source_sha256=sha)
        self.assertNotIn("body", self.j.capture(cid))
        self.assertEqual(self.j.capture(cid)["projection"], projection)
        self.assertEqual(self.j.capture(cid)["sha256"], sha)
        self.assertEqual(self.j.freeze("synthetic", "https://example.invalid/data", "2026-01-01T00:00:00Z", projection, "0" * 64, source_sha256=sha), cid)
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
                self.j.freeze("synthetic", "https://example.invalid", "2026-01-01T00:00:00Z", data, "0" * 64, source_sha256="0" * 64)
        self.assertEqual(self.j.events(), [])

    def test_integrity_detects_tampering(self):
        self.j.append("receipt", "2026-01-01T00:00:00Z", {})
        self.j.db.execute("DROP TRIGGER watch_no_update")
        self.j.db.execute("UPDATE watch_events SET payload='{} ' ")
        self.j.db.execute("UPDATE watch_events SET at='2026-01-02'")
        with self.assertRaises(ValueError):
            self.j.verify()

    def test_bundle_is_atomic_when_admission_fails(self):
        with self.assertRaises(ValueError):
            self.j.append_many([("receipt", "2026-01-01T00:00:00Z", {}),
                                ("receipt", "2026-01-01T00:00:00Z", {"email": "redacted"})])
        self.assertEqual(self.j.events(), [])


class FrozenAcceptanceTests(unittest.TestCase):
    def test_supplied_bytes_and_manifest_remain_frozen(self):
        root=Path(__file__).resolve().parents[1]/'acceptance/2026-10-27'
        expected={
            'candidates.json':'bdb4a985a7fe493550f60f335ce0ce824378a7691bc56819a41db217784e1f42',
            'intersection.json':'c625b6489b23257eee10507e4d3a64c48a414ac076f10a4483ab7d9a1fdbb4b7',
            'cf_state.json':'06154c5380520a40d0348d3d4b667a9b6ceca5ff4fed890e36ac5c72e95e50b4',
            'hashes.txt':'bd070d01c8825345f6801795e47e65ec3167df6164040d63c61b0721fbd4e172'}
        manifest=json.loads((root/'manifest.json').read_text())
        entries={f['name']:f for f in manifest['files']}
        self.assertEqual(set(entries),set(expected))
        for name,sha in expected.items():
            with self.subTest(file=name):
                data=(root/name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),sha)
                self.assertEqual(entries[name]['sha256'],sha)
                self.assertEqual(entries[name]['size_bytes'],len(data))


if __name__ == "__main__":
    unittest.main()
