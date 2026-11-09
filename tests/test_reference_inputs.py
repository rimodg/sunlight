"""Synthetic file admission tests. No reference corpus is recreated here."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from reference_inputs import verify_reference_inputs


class ReferenceInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "synthetic.db"
        self.cases = self.root / "synthetic-cases.json"
        self.db.write_bytes(b"synthetic reference bytes, not a database")
        self.cases.write_bytes(b'{"synthetic":true}\n')
        self.manifest = {"schema": "sunlight.reference-inputs.v1", "artifacts": {
            "database": {"sha256": hashlib.sha256(self.db.read_bytes()).hexdigest(), "locator": None},
            "cases": {"sha256": hashlib.sha256(self.cases.read_bytes()).hexdigest(), "locator": None}}}

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_bytes_admit_inputs_but_do_not_claim_a_floor_run(self):
        result = verify_reference_inputs(self.manifest, database=self.db, cases=self.cases)
        self.assertTrue(result["ready_to_run_reference_protocols"])
        self.assertFalse(result["reference_protocols_executed"])
        self.assertFalse(result["artifacts"]["database"]["storage_locator_registered"])

    def test_missing_is_not_zero_and_nothing_is_created(self):
        absent = self.root / "missing.db"
        result = verify_reference_inputs(self.manifest, database=absent)
        self.assertEqual(result["artifacts"]["database"]["state"], "missing")
        self.assertIsNone(result["artifacts"]["database"]["observed_size_bytes"])
        self.assertEqual(result["artifacts"]["cases"]["state"], "not_configured")
        self.assertFalse(absent.exists())

    def test_a_wrong_file_is_preserved_and_refused(self):
        self.db.write_bytes(b"different synthetic data")
        result = verify_reference_inputs(self.manifest, database=self.db, cases=self.cases)
        self.assertEqual(result["artifacts"]["database"]["state"], "hash_mismatch")
        self.assertFalse(result["ready_to_run_reference_protocols"])
        self.assertEqual(self.db.read_bytes(), b"different synthetic data")

    def test_directory_is_not_a_database(self):
        result = verify_reference_inputs(self.manifest, database=self.root)
        self.assertEqual(result["artifacts"]["database"]["state"], "not_a_file")

    def test_bad_digest_is_not_silently_accepted(self):
        self.manifest["artifacts"]["database"]["sha256"] = "unknown"
        with self.assertRaises(ValueError):
            verify_reference_inputs(self.manifest, database=self.db)

    def test_empty_bytes_are_a_measured_file_not_a_missing_file(self):
        self.db.write_bytes(b"")
        result = verify_reference_inputs(self.manifest, database=self.db)
        self.assertEqual(result["artifacts"]["database"]["observed_size_bytes"], 0)
        self.assertEqual(result["artifacts"]["database"]["state"], "hash_mismatch")


if __name__ == "__main__":
    unittest.main()
