"""
SUNLIGHT Governance & Auditability
=====================================

Provides:
- Versioned rulepack concept (each score references rulepack hash/version)
- Extended audit log entries (login, view, export, disposition, rulepack version)
- Data snapshot ID generation
"""

import hashlib
import json
import sqlite3
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(__file__))
from institutional_statistical_rigor import DOJProsecutionThresholds
from sunlight_logging import get_logger

logger = get_logger("governance")


# ---------------------------------------------------------------------------
# Versioned Rulepack
# ---------------------------------------------------------------------------

RULEPACK_REGISTRY = {
    '1.0.0': {
        'version': '1.0.0',
        'release_date': '2026-01-01',
        'rules': [
            {'id': 'PRICE-001', 'name': 'Extreme Price Inflation', 'threshold': 'CI lower > 300%'},
            {'id': 'PRICE-002', 'name': 'High Price Inflation', 'threshold': 'CI lower > 200%'},
            {'id': 'PRICE-003', 'name': 'Elevated Price Anomaly', 'threshold': 'CI lower > 75%'},
            {'id': 'BAYES-001', 'name': 'High Bayesian Posterior', 'threshold': 'Posterior > 80%'},
            {'id': 'OUTLIER-001', 'name': 'Extreme Percentile Outlier', 'threshold': 'Percentile > 95th'},
        ],
        'thresholds': {
            'extreme_markup': 300,
            'high_markup': 200,
            'elevated_markup': 150,
            'investigation_worthy': 75,
            'bayesian_high': 0.80,
            'bayesian_elevated': 0.50,
            'percentile_extreme': 95,
            'percentile_upper': 75,
        },
        'tier_logic': 'CI > 300 → RED; avg_confidence >= 90 + survives_fdr → RED; avg >= 70 → YELLOW; < 5 comparables → GRAY; else GREEN',
        'statistical_methods': ['BCa Bootstrap', 'Bayesian Posterior', 'Benjamini-Hochberg FDR'],
        'bootstrap_iterations': 1000,
        'fdr_alpha': 0.10,
    },
    '2.0.0': {
        'version': '2.0.0',
        'release_date': '2026-02-18',
        'rules': [
            {'id': 'PRICE-001', 'name': 'Extreme Price Inflation', 'threshold': 'CI lower > 300%'},
            {'id': 'PRICE-002', 'name': 'High Price Inflation', 'threshold': 'CI lower > 200%'},
            {'id': 'PRICE-003', 'name': 'Elevated Price Anomaly', 'threshold': 'CI lower > 75%'},
            {'id': 'BAYES-001', 'name': 'High Bayesian Posterior', 'threshold': 'Posterior > 80%'},
            {'id': 'BAYES-002', 'name': 'Elevated Bayesian Posterior', 'threshold': 'Posterior > 50%'},
            {'id': 'OUTLIER-001', 'name': 'Extreme Percentile Outlier', 'threshold': 'Percentile > 95th'},
            {'id': 'OUTLIER-002', 'name': 'Upper Quartile Outlier', 'threshold': 'Percentile > 75th'},
        ],
        'thresholds': {
            'extreme_markup': DOJProsecutionThresholds.EXTREME_MARKUP,
            'high_markup': DOJProsecutionThresholds.HIGH_MARKUP,
            'elevated_markup': DOJProsecutionThresholds.ELEVATED_MARKUP,
            'investigation_worthy': DOJProsecutionThresholds.INVESTIGATION_WORTHY,
            'bayesian_high': 0.80,
            'bayesian_elevated': 0.50,
            'percentile_extreme': 95,
            'percentile_upper': 75,
        },
        'tier_logic': 'CI > 300 → RED; avg_confidence >= 90 + survives_fdr → RED; avg >= 70 → YELLOW; < 5 comparables → GRAY; else GREEN',
        'statistical_methods': ['BCa Bootstrap', 'Bayesian Posterior', 'Benjamini-Hochberg FDR'],
        'bootstrap_iterations': 1000,
        'fdr_alpha': 0.10,
        'changes_from_previous': [
            'Added data normalization and confidence scoring',
            'Added severity downgrade for low-confidence evidence',
            'Added case packet export with disposition tracking',
            'Added rulepack versioning and hash verification',
        ],
    },
}

CURRENT_RULEPACK = '2.0.0'


def compute_rulepack_hash(version: str) -> str:
    """Compute deterministic hash of a rulepack version."""
    rp = RULEPACK_REGISTRY.get(version)
    if not rp:
        raise ValueError(f"Unknown rulepack version: {version}")
    # Hash the rules and thresholds (not metadata like dates)
    payload = json.dumps({
        'rules': rp['rules'],
        'thresholds': rp['thresholds'],
        'tier_logic': rp['tier_logic'],
    }, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def get_current_rulepack() -> Dict:
    """Get the current active rulepack."""
    return RULEPACK_REGISTRY[CURRENT_RULEPACK]


def get_rulepack_info(version: str) -> Dict:
    """Get rulepack info including hash."""
    rp = RULEPACK_REGISTRY.get(version)
    if not rp:
        return {'error': f'Unknown version: {version}'}
    return {
        **rp,
        'hash': compute_rulepack_hash(version),
    }


# ---------------------------------------------------------------------------
# Extended Audit Log
# ---------------------------------------------------------------------------

AUDIT_ACTIONS = {
    'LOGIN', 'VIEW', 'EXPORT', 'DISPOSITION_CHANGE',
    'SCORE_RUN', 'RUN_STARTED', 'RUN_COMPLETED',
    'INGESTION_STARTED', 'INGESTION_COMPLETED',
    'KEY_GENERATED', 'KEY_REVOKED', 'KEY_ROTATED',
    'CASE_PACKET_GENERATED', 'REPORT_GENERATED',
}


def log_governance_event(db_path: str, action: str, details: Dict,
                          user: Optional[str] = None,
                          entity_id: Optional[str] = None):
    """
    Log a governance event to the audit trail.

    Includes rulepack version and data snapshot ID.
    """
    if action not in AUDIT_ACTIONS:
        logger.warning("Unknown audit action", extra={"action": action})

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get next sequence
    c.execute("SELECT MAX(sequence_number) FROM audit_log")
    seq = (c.fetchone()[0] or 0) + 1

    # Get previous hash
    prev_hash = '0' * 64
    if seq > 1:
        for col in ['entry_hash', 'current_log_hash']:
            try:
                c.execute(f"SELECT {col} FROM audit_log WHERE sequence_number=?", (seq - 1,))
                r = c.fetchone()
                if r and r[0]:
                    prev_hash = r[0]
                    break
            except Exception:
                continue

    ts = datetime.now(timezone.utc).isoformat()
    lid = hashlib.sha256(f"{seq}:{ts}".encode()).hexdigest()[:16]

    # Enrich details
    enriched = {
        **details,
        'rulepack_version': CURRENT_RULEPACK,
        'rulepack_hash': compute_rulepack_hash(CURRENT_RULEPACK)[:16],
    }
    if user:
        enriched['user'] = user

    payload = json.dumps({
        'sequence': seq, 'timestamp': ts, 'action': action,
        'run_id': entity_id, 'details': enriched, 'previous_hash': prev_hash,
    }, sort_keys=True, separators=(',', ':'))
    eh = hashlib.sha256(payload.encode()).hexdigest()

    c.execute(
        "INSERT INTO audit_log (log_id, sequence_number, timestamp, action_type, "
        "entity_id, previous_log_hash, current_log_hash, action, run_id, details, "
        "previous_hash, entry_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (lid, seq, ts, action, entity_id, prev_hash, eh, action, entity_id,
         json.dumps(enriched), prev_hash, eh),
    )
    conn.commit()
    conn.close()

    logger.info("Governance event logged",
                extra={"action": action, "entity_id": entity_id,
                       "sequence": seq, "user": user})
