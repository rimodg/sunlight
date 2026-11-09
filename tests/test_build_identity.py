"""Offline packaged-build identity tests. No image pulls or external requests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from build_identity import runtime_identity, version_label, write_manifest


class BuildIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "code").mkdir()
        (self.root / "code/app.py").write_text("SYNTHETIC = True\n")
        (self.root / "requirements.lock").write_text("synthetic==1\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_no_git_still_has_actual_source_identity(self):
        value = runtime_identity(self.root)
        self.assertIsNone(value["git_commit"])
        self.assertEqual(value["state"], "source_fingerprint_only")
        self.assertIn(value["source_sha256"][:12], version_label(value))
        self.assertNotIn("unknown", version_label(value))
        self.assertNotIn("unversioned", version_label(value))

    def test_declared_revision_and_actual_packaged_files_are_distinct(self):
        manifest = write_manifest(self.root, commit="a" * 40)
        value = runtime_identity(self.root)
        self.assertEqual(value["git_commit"], "a" * 40)
        self.assertEqual(value["git_commit_basis"], "declared_build_input")
        self.assertEqual(value["state"], "packaged_files_match")
        self.assertEqual(value["identity_sha256"], manifest["sha256"])

    def test_source_changes_and_new_files_refuse_old_manifest(self):
        write_manifest(self.root)
        (self.root / "code/app.py").write_text("SYNTHETIC = False\n")
        with self.assertRaisesRegex(ValueError, "Packaged source"):
            runtime_identity(self.root)
        write_manifest(self.root)
        (self.root / "code/new_rule.py").write_text("SYNTHETIC = True\n")
        with self.assertRaisesRegex(ValueError, "Packaged source"):
            runtime_identity(self.root)

    def test_manifest_tamper_is_not_a_verified_build(self):
        write_manifest(self.root)
        path = self.root / "build_identity.json"
        data = json.loads(path.read_text())
        data["payload"]["git_commit"] = "b" * 40
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "manifest digest"):
            runtime_identity(self.root)

    def test_environment_drift_refuses_startup(self):
        write_manifest(self.root)
        with patch("build_identity.environment", return_value={"python": "synthetic-other-runtime"}):
            with self.assertRaisesRegex(ValueError, "Runtime environment"):
                runtime_identity(self.root)

    def test_revision_must_be_full_and_not_a_branch_name(self):
        for revision in ["main", "945c347", "a" * 39, "bad revision"]:
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                write_manifest(self.root, commit=revision)
        self.assertFalse((self.root / "build_identity.json").exists())

    def test_manifest_does_not_include_captures_or_itself(self):
        (self.root / "journal.sqlite3").write_bytes(b"synthetic private state")
        first = write_manifest(self.root)
        second = write_manifest(self.root)
        self.assertEqual(first, second)
        self.assertNotIn("journal.sqlite3", second["payload"]["source_files"])
        self.assertNotIn("build_identity.json", second["payload"]["source_files"])


class VersionEndpointTests(unittest.TestCase):
    def test_actual_api_reports_frozen_startup_identity(self):
        import api
        from fastapi.testclient import TestClient
        with TestClient(api.app) as client:
            first = client.get("/version")
            self.assertEqual(first.status_code, 200)
            value = first.json()
            self.assertEqual(value["git_commit"], api._RUNNING_BUILD_IDENTITY["git_commit"])
            self.assertEqual(value["build"]["source_sha256"], api._RUNNING_BUILD_IDENTITY["source_sha256"])
            with patch("build_identity.git_state", side_effect=AssertionError("Request must not re-read Git")):
                self.assertEqual(client.get("/version").json(), value)
            profiles = client.get("/profiles").json()["profiles"]
            self.assertEqual(set(value["profiles"]), {p["name"] for p in profiles})


if __name__ == "__main__":
    unittest.main()
