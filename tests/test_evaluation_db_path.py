"""
Tests for evaluation.py DB path resolution and sanity checks.
==============================================================

Three regression tests hardening the DOJ regression gate against
silent path mis-resolution (the sub-task B incident).

Run with:  pytest tests/test_evaluation_db_path.py -v
"""

import os
import sqlite3
import tempfile

import pytest

# evaluation.py adds code/ to sys.path at import time
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evaluation import resolve_db_path, verify_db_has_contracts


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════


def _create_db_with_tables(path: str, tables: list[str]) -> None:
    """Create a SQLite DB at path with the given table names."""
    conn = sqlite3.connect(path)
    for table in tables:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════


class TestVerifyDbHasContracts:
    """verify_db_has_contracts raises RuntimeError on wrong DB."""

    def test_missing_contracts_table_raises_with_resolved_path(self, tmp_path):
        """A DB without contracts table raises RuntimeError including the path."""
        db_path = str(tmp_path / "bad.db")
        _create_db_with_tables(db_path, ["api_keys", "tenants"])
        with pytest.raises(RuntimeError, match=db_path):
            verify_db_has_contracts(db_path)

    def test_error_message_contains_canonical_path_hint(self, tmp_path):
        """The error message contains the hint about the production DB location."""
        db_path = str(tmp_path / "bad.db")
        _create_db_with_tables(db_path, ["api_keys"])
        with pytest.raises(RuntimeError, match="production DB is at"):
            verify_db_has_contracts(db_path)


class TestResolveDbPath:
    """SUNLIGHT_DB_PATH env var takes precedence over CLI flag."""

    def test_env_var_takes_precedence_over_cli(self, tmp_path, monkeypatch):
        """SUNLIGHT_DB_PATH overrides the CLI --db value."""
        env_db = str(tmp_path / "env.db")
        cli_db = str(tmp_path / "cli.db")
        _create_db_with_tables(env_db, ["contracts"])
        _create_db_with_tables(cli_db, ["contracts"])
        monkeypatch.setenv("SUNLIGHT_DB_PATH", env_db)
        resolved = resolve_db_path(cli_db)
        assert resolved == env_db, (
            f"Expected env var path {env_db}, got {resolved}"
        )
