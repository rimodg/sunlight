"""
SUNLIGHT Admin Dashboard
=========================

Provides system health metrics, detection statistics over time,
API usage per client, and the flagged contracts queue for
administrative oversight.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sunlight_logging import get_logger

logger = get_logger("dashboard")


def get_system_health(db_path: str) -> Dict[str, Any]:
    """Comprehensive system health snapshot."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Database size
    db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    # Table counts
    tables = {}
    from sql_allowlist import validate_table
    for table in ['contracts', 'contract_scores', 'analysis_runs', 'audit_log',
                  'political_donations', 'api_keys', 'api_usage', 'ingestion_jobs']:
        try:
            c.execute(f"SELECT COUNT(*) FROM {validate_table(table)}")
            tables[table] = c.fetchone()[0]
        except sqlite3.OperationalError:
            tables[table] = 0

    # Latest run
    c.execute("""
        SELECT run_id, status, started_at, completed_at, n_scored, n_errors
        FROM analysis_runs ORDER BY started_at DESC LIMIT 1
    """)
    latest_run = None
    row = c.fetchone()
    if row:
        latest_run = dict(row)

    # Stale runs
    c.execute("""
        SELECT COUNT(*) FROM analysis_runs
        WHERE status = 'RUNNING'
        AND started_at < datetime('now', '-1 hour')
    """)
    stale_runs = c.fetchone()[0]

    # Audit chain integrity
    try:
        c.execute("""
            WITH chain AS (
                SELECT sequence_number,
                       previous_log_hash,
                       current_log_hash,
                       LAG(current_log_hash) OVER (ORDER BY sequence_number) AS expected_prev
                FROM audit_log
            )
            SELECT COUNT(*) FROM chain
            WHERE sequence_number > 1 AND previous_log_hash != expected_prev
        """)
        chain_breaks = c.fetchone()[0]
        audit_chain_valid = chain_breaks == 0
    except sqlite3.OperationalError:
        audit_chain_valid = True
        chain_breaks = 0

    # Ingestion jobs in last 24h
    c.execute("""
        SELECT status, COUNT(*) as count
        FROM ingestion_jobs
        WHERE submitted_at > datetime('now', '-1 day')
        GROUP BY status
    """)
    recent_ingestions = {row['status']: row['count'] for row in c.fetchall()}

    conn.close()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "path": os.path.basename(db_path),
            "size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "table_counts": tables,
        },
        "pipeline": {
            "latest_run": latest_run,
            "stale_runs": stale_runs,
            "audit_chain_valid": audit_chain_valid,
            "audit_chain_breaks": chain_breaks,
        },
        "ingestion_24h": recent_ingestions,
        "status": "healthy" if stale_runs == 0 and audit_chain_valid else "degraded",
    }


def get_detection_stats(db_path: str, days: int = 30) -> Dict[str, Any]:
    """Detection statistics over time."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Overall tier distribution
    c.execute("""
        SELECT fraud_tier, COUNT(*) as count
        FROM contract_scores
        GROUP BY fraud_tier
        ORDER BY count DESC
    """)
    tier_distribution = {row['fraud_tier']: row['count'] for row in c.fetchall()}

    # Total scored
    total_scored = sum(tier_distribution.values())

    # FDR survival
    c.execute("SELECT COUNT(*) FROM contract_scores WHERE survives_fdr = 1")
    survives_fdr = c.fetchone()[0]

    # Per-run stats (most recent runs)
    c.execute("""
        SELECT ar.run_id, ar.started_at, ar.status, ar.n_scored, ar.n_errors,
               COUNT(CASE WHEN cs.fraud_tier = 'RED' THEN 1 END) as red_count,
               COUNT(CASE WHEN cs.fraud_tier = 'YELLOW' THEN 1 END) as yellow_count,
               COUNT(CASE WHEN cs.fraud_tier = 'GREEN' THEN 1 END) as green_count,
               COUNT(CASE WHEN cs.fraud_tier = 'GRAY' THEN 1 END) as gray_count
        FROM analysis_runs ar
        LEFT JOIN contract_scores cs ON ar.run_id = cs.run_id
        GROUP BY ar.run_id
        ORDER BY ar.started_at DESC
        LIMIT 10
    """)
    run_history = [dict(row) for row in c.fetchall()]

    # Top flagged vendors (RED + YELLOW, across all runs)
    c.execute("""
        SELECT c.vendor_name,
               COUNT(*) as flag_count,
               COUNT(CASE WHEN cs.fraud_tier = 'RED' THEN 1 END) as red_count,
               COUNT(CASE WHEN cs.fraud_tier = 'YELLOW' THEN 1 END) as yellow_count,
               MAX(cs.markup_pct) as max_markup,
               SUM(c.award_amount) as total_value
        FROM contract_scores cs
        JOIN contracts c ON cs.contract_id = c.contract_id
        WHERE cs.fraud_tier IN ('RED', 'YELLOW')
        GROUP BY c.vendor_name
        ORDER BY red_count DESC, yellow_count DESC
        LIMIT 20
    """)
    top_flagged_vendors = [dict(row) for row in c.fetchall()]

    # Top flagged agencies
    c.execute("""
        SELECT c.agency_name,
               COUNT(*) as flag_count,
               COUNT(CASE WHEN cs.fraud_tier = 'RED' THEN 1 END) as red_count,
               COUNT(CASE WHEN cs.fraud_tier = 'YELLOW' THEN 1 END) as yellow_count,
               SUM(c.award_amount) as total_value
        FROM contract_scores cs
        JOIN contracts c ON cs.contract_id = c.contract_id
        WHERE cs.fraud_tier IN ('RED', 'YELLOW')
        GROUP BY c.agency_name
        ORDER BY red_count DESC, flag_count DESC
        LIMIT 20
    """)
    top_flagged_agencies = [dict(row) for row in c.fetchall()]

    # Markup distribution for flagged contracts
    c.execute("""
        SELECT
            CASE
                WHEN markup_pct > 300 THEN '>300%'
                WHEN markup_pct > 200 THEN '200-300%'
                WHEN markup_pct > 100 THEN '100-200%'
                WHEN markup_pct > 50 THEN '50-100%'
                ELSE '<50%'
            END as markup_range,
            COUNT(*) as count
        FROM contract_scores
        WHERE fraud_tier IN ('RED', 'YELLOW') AND markup_pct IS NOT NULL
        GROUP BY markup_range
        ORDER BY MIN(markup_pct) DESC
    """)
    markup_distribution = {row['markup_range']: row['count'] for row in c.fetchall()}

    conn.close()

    return {
        "summary": {
            "total_scored": total_scored,
            "tier_distribution": tier_distribution,
            "survives_fdr": survives_fdr,
            "flagged_rate": round(
                (tier_distribution.get('RED', 0) + tier_distribution.get('YELLOW', 0)) / total_scored * 100, 1
            ) if total_scored > 0 else 0,
        },
        "run_history": run_history,
        "top_flagged_vendors": top_flagged_vendors,
        "top_flagged_agencies": top_flagged_agencies,
        "markup_distribution": markup_distribution,
    }


def get_api_usage(db_path: str, days: int = 30) -> Dict[str, Any]:
    """API usage statistics per client."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Per-client usage
    c.execute("""
        SELECT ak.client_name, ak.key_id, ak.scopes, ak.is_active,
               ak.rate_limit, ak.created_at,
               COUNT(au.id) as total_requests,
               COUNT(CASE WHEN au.timestamp > datetime('now', '-1 day') THEN 1 END) as requests_24h,
               COUNT(CASE WHEN au.timestamp > datetime('now', '-7 days') THEN 1 END) as requests_7d,
               MAX(au.timestamp) as last_request
        FROM api_keys ak
        LEFT JOIN api_usage au ON ak.key_id = au.key_id
        GROUP BY ak.key_id
        ORDER BY total_requests DESC
    """)
    per_client = []
    for row in c.fetchall():
        d = dict(row)
        d['is_active'] = bool(d.get('is_active'))
        per_client.append(d)

    # Top endpoints
    c.execute("""
        SELECT endpoint, method,
               COUNT(*) as count,
               COUNT(CASE WHEN timestamp > datetime('now', '-1 day') THEN 1 END) as count_24h
        FROM api_usage
        GROUP BY endpoint, method
        ORDER BY count DESC
        LIMIT 20
    """)
    top_endpoints = [dict(row) for row in c.fetchall()]

    # Total request volume
    c.execute("SELECT COUNT(*) FROM api_usage")
    total_all_time = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp > datetime('now', '-1 day')")
    total_24h = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM api_usage WHERE timestamp > datetime('now', '-7 days')")
    total_7d = c.fetchone()[0]

    # Active keys
    c.execute("SELECT COUNT(*) FROM api_keys WHERE is_active = 1")
    active_keys = c.fetchone()[0]

    conn.close()

    return {
        "volume": {
            "total_all_time": total_all_time,
            "total_24h": total_24h,
            "total_7d": total_7d,
            "active_keys": active_keys,
        },
        "per_client": per_client,
        "top_endpoints": top_endpoints,
    }


def get_flagged_queue(db_path: str, tier: Optional[str] = None,
                      run_id: Optional[str] = None,
                      offset: int = 0, limit: int = 50) -> Dict[str, Any]:
    """Prioritized queue of flagged contracts for investigation."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    where_clauses = ["cs.fraud_tier IN ('RED', 'YELLOW')"]
    params = []

    if tier:
        where_clauses = ["cs.fraud_tier = ?"]
        params.append(tier)
    if run_id:
        where_clauses.append("cs.run_id = ?")
        params.append(run_id)

    # Safe by construction: where_clauses contains only hardcoded SQL fragments
    # with parameterized "?" placeholders — no user-controlled identifiers.
    where_sql = " AND ".join(where_clauses)

    # Total count
    c.execute(f"SELECT COUNT(*) FROM contract_scores cs WHERE {where_sql}", params)
    total = c.fetchone()[0]

    # Flagged contracts with full context
    c.execute(f"""
        SELECT cs.score_id, cs.contract_id, cs.run_id, cs.fraud_tier,
               cs.confidence_score, cs.markup_pct, cs.markup_ci_lower,
               cs.markup_ci_upper, cs.bayesian_posterior, cs.raw_pvalue,
               cs.survives_fdr, cs.comparable_count, cs.triage_priority,
               c.award_amount, c.vendor_name, c.agency_name, c.description,
               c.start_date
        FROM contract_scores cs
        JOIN contracts c ON cs.contract_id = c.contract_id
        WHERE {where_sql}
        ORDER BY cs.triage_priority ASC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    items = []
    for row in c.fetchall():
        d = dict(row)
        d['survives_fdr'] = bool(d.get('survives_fdr'))
        items.append(d)

    # Summary stats for the filtered set
    c.execute(f"""
        SELECT
            COUNT(CASE WHEN cs.fraud_tier = 'RED' THEN 1 END) as red_count,
            COUNT(CASE WHEN cs.fraud_tier = 'YELLOW' THEN 1 END) as yellow_count,
            COUNT(CASE WHEN cs.survives_fdr = 1 THEN 1 END) as fdr_survivors,
            COALESCE(SUM(c.award_amount), 0) as total_flagged_value,
            COALESCE(AVG(cs.markup_pct), 0) as avg_markup
        FROM contract_scores cs
        JOIN contracts c ON cs.contract_id = c.contract_id
        WHERE {where_sql}
    """, params)
    summary = dict(c.fetchone())

    conn.close()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "summary": summary,
        "items": items,
    }
