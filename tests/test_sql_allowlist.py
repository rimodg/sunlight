"""
Tests for SQL allowlist validation (security hardening).
=========================================================

Verifies that the sql_allowlist module correctly validates SQL identifiers
against canonical allowlists and blocks injection attempts.

Run with:  pytest tests/test_sql_allowlist.py -v
"""

import os
import sys

import pytest

# Ensure code/ is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from sql_allowlist import (
    SQLAllowlistError,
    ALLOWED_TABLES,
    ALLOWED_COLUMNS,
    ALLOWED_DIRECTIONS,
    validate_table,
    validate_column,
    validate_direction,
    validate_identifier,
)


class TestAllowlistSets:
    """Canonical allowlist integrity."""

    def test_allowed_tables_contains_core_tables(self):
        """Every table interpolated in the codebase must be in ALLOWED_TABLES."""
        required = {
            "contracts", "contract_scores", "analysis_runs", "audit_log",
            "political_donations", "api_keys", "api_usage", "ingestion_jobs",
            "contracts_clean", "scan_jobs", "tenants",
        }
        assert required.issubset(ALLOWED_TABLES)

    def test_allowed_columns_contains_interpolated_columns(self):
        """Every column interpolated in the codebase must be in ALLOWED_COLUMNS."""
        required = {
            # ingestion.py _ALLOWED_JOB_COLUMNS
            "status", "completed_at", "total_records", "inserted",
            "duplicates", "errors", "scored", "error_details",
            # institutional_pipeline.py + governance.py
            "entry_hash", "current_log_hash",
            # tenancy.py
            "name", "webhook_url", "settings_json", "tier",
            "rate_limit_rpm", "max_concurrency", "max_contracts", "updated_at",
            # data_quality_monitor.py CRITICAL_FIELDS
            "contract_id", "award_amount", "vendor_name", "agency_name",
            "start_date", "award_type",
        }
        assert required.issubset(ALLOWED_COLUMNS)

    def test_allowed_directions(self):
        """Only ASC and DESC are valid sort directions."""
        assert ALLOWED_DIRECTIONS == frozenset({"ASC", "DESC"})


class TestValidateTable:
    """validate_table accepts good names, rejects bad ones."""

    def test_valid_table(self):
        assert validate_table("contracts") == "contracts"
        assert validate_table("contracts_clean") == "contracts_clean"

    def test_invalid_table_raises(self):
        with pytest.raises(SQLAllowlistError, match="table"):
            validate_table("users; DROP TABLE contracts")

    def test_empty_string_raises(self):
        with pytest.raises(SQLAllowlistError):
            validate_table("")


class TestValidateColumn:
    """validate_column accepts good names, rejects bad ones."""

    def test_valid_column(self):
        assert validate_column("award_amount") == "award_amount"
        assert validate_column("entry_hash") == "entry_hash"

    def test_invalid_column_raises(self):
        with pytest.raises(SQLAllowlistError, match="column"):
            validate_column("1=1; --")

    def test_empty_string_raises(self):
        with pytest.raises(SQLAllowlistError):
            validate_column("")


class TestValidateDirection:
    """validate_direction accepts ASC/DESC (case-insensitive), rejects others."""

    def test_valid_asc(self):
        assert validate_direction("ASC") == "ASC"

    def test_valid_desc_lowercase(self):
        assert validate_direction("desc") == "DESC"

    def test_invalid_direction_raises(self):
        with pytest.raises(SQLAllowlistError, match="direction"):
            validate_direction("RANDOM")


class TestValidateIdentifier:
    """Generic validate_identifier works for arbitrary allowlists."""

    def test_generic_pass(self):
        allowed = frozenset({"alpha", "beta"})
        assert validate_identifier("alpha", allowed, "test") == "alpha"

    def test_generic_fail(self):
        allowed = frozenset({"alpha", "beta"})
        with pytest.raises(SQLAllowlistError, match="test"):
            validate_identifier("gamma", allowed, "test")


class TestSQLAllowlistError:
    """SQLAllowlistError is a ValueError subclass."""

    def test_is_value_error_subclass(self):
        assert issubclass(SQLAllowlistError, ValueError)

    def test_can_be_caught_as_value_error(self):
        with pytest.raises(ValueError):
            validate_table("nonexistent_table")
