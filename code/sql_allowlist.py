"""
SUNLIGHT SQL Allowlist — Defence-in-depth for dynamic SQL identifiers.
=====================================================================

Every f-string-interpolated SQL identifier (table name, column name,
sort direction) in the SUNLIGHT codebase MUST pass through one of
the validators below before reaching a cursor.execute() call.

The canonical sets are derived from the production schema
(sqlite3 sunlight.db ".tables" + PRAGMA table_info for each table).

Raises SQLAllowlistError (a ValueError subclass) on any identifier
not in the corresponding allowlist.

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 1.0.0
"""

from __future__ import annotations

from typing import FrozenSet


# ═══════════════════════════════════════════════════════════
# EXCEPTION
# ═══════════════════════════════════════════════════════════

class SQLAllowlistError(ValueError):
    """Raised when a SQL identifier is not in the allowlist."""
    pass


# ═══════════════════════════════════════════════════════════
# CANONICAL ALLOWLISTS (derived from production schema)
# ═══════════════════════════════════════════════════════════

ALLOWED_TABLES: FrozenSet[str] = frozenset({
    "analysis_results",
    "analysis_runs",
    "api_keys",
    "api_usage",
    "audit_log",
    "contract_amendments",
    "contract_scores",
    "contracts",
    "contracts_clean",
    "dead_letter_queue",
    "ingestion_jobs",
    "political_donations",
    "scan_jobs",
    "tenant_users",
    "tenants",
    "webhook_deliveries",
})

ALLOWED_COLUMNS: FrozenSet[str] = frozenset({
    # analysis_results
    "id", "contract_id", "risk_score", "flags", "analyzed_at",
    # contract_scores
    "score_id", "run_id", "raw_data_hash", "fraud_tier",
    "confidence_score", "markup_pct", "bayesian_posterior",
    "raw_pvalue", "fdr_adjusted_pvalue", "survives_fdr",
    "triage_priority", "tier", "markup_ci_lower", "markup_ci_upper",
    "raw_zscore", "log_zscore", "bootstrap_percentile",
    "percentile_ci_lower", "percentile_ci_upper", "bayesian_prior",
    "bayesian_likelihood_ratio", "comparable_count",
    "insufficient_comparables", "selection_params_json", "scored_at",
    # scan_jobs
    "job_id", "tenant_id", "idempotency_key", "status", "job_type",
    "input_json", "result_json", "progress_pct", "progress_msg",
    "attempt", "max_attempts", "error_message", "error_trace",
    "created_at", "started_at", "completed_at", "next_retry_at",
    "worker_id",
    # analysis_runs
    "model_version", "config_json", "config_hash", "run_seed",
    "environment_json", "code_commit_hash", "dataset_hash",
    "contracts_analyzed", "fdr_n_tests", "fdr_n_significant",
    "fdr_alpha", "n_contracts", "n_scored", "n_errors", "summary_json",
    # contracts
    "award_amount", "vendor_name", "agency_name", "description",
    "start_date", "location", "raw_data",
    # tenant_users
    "user_id", "email", "role", "is_active",
    # api_keys
    "key_id", "key_hash", "client_name", "expires_at", "revoked_at",
    "rate_limit", "rate_window", "scopes", "notes",
    # contracts_clean
    "end_date", "award_type", "num_offers", "extent_competed",
    # tenants
    "name", "slug", "webhook_url", "webhook_secret", "settings_json",
    "max_contracts", "rate_limit_rpm", "max_concurrency", "updated_at",
    # api_usage
    "timestamp", "endpoint", "method", "status_code",
    "response_time_ms", "ip_address",
    # dead_letter_queue
    "dlq_id", "attempts", "original_created_at",
    # webhook_deliveries
    "delivery_id", "event_id", "event_type", "payload_json",
    "last_status_code", "last_error", "delivered_at",
    # audit_log
    "log_id", "sequence_number", "action_type", "entity_id",
    "previous_log_hash", "current_log_hash", "action", "details",
    "previous_hash", "entry_hash",
    # ingestion_jobs
    "source_filename", "source_format", "source_hash", "submitted_at",
    "total_records", "inserted", "duplicates", "errors", "scored",
    "error_details",
    # contract_amendments
    "base_amount", "current_amount", "modification_count",
    "growth_percentage", "last_modified_date",
    # political_donations
    "recipient_name", "amount", "date", "cycle", "source",
})

ALLOWED_DIRECTIONS: FrozenSet[str] = frozenset({"ASC", "DESC"})


# ═══════════════════════════════════════════════════════════
# VALIDATORS
# ═══════════════════════════════════════════════════════════

def validate_identifier(name: str, allowed: FrozenSet[str], kind: str) -> str:
    """
    Generic allowlist validator. Returns the name unchanged if it is
    in the allowed set; raises SQLAllowlistError otherwise.

    Args:
        name: The SQL identifier to validate.
        allowed: The canonical set of allowed identifiers.
        kind: Human-readable label for error messages (e.g. "table", "column").

    Returns:
        The validated identifier (unchanged).

    Raises:
        SQLAllowlistError: If name is not in the allowed set.
    """
    if name not in allowed:
        raise SQLAllowlistError(
            f"SQL {kind} {name!r} is not in the allowlist"
        )
    return name


def validate_table(name: str) -> str:
    """Validate a table name against ALLOWED_TABLES."""
    return validate_identifier(name, ALLOWED_TABLES, "table")


def validate_column(name: str) -> str:
    """Validate a column name against ALLOWED_COLUMNS."""
    return validate_identifier(name, ALLOWED_COLUMNS, "column")


def validate_direction(name: str) -> str:
    """Validate a sort direction against ALLOWED_DIRECTIONS."""
    return validate_identifier(name.upper(), ALLOWED_DIRECTIONS, "direction")
