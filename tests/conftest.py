"""
Shared fixtures for SUNLIGHT test suite.
"""
import sys
import os
import pytest
import numpy as np
import sqlite3
import tempfile
import json

# Disable auth for tests by default
os.environ['SUNLIGHT_AUTH_ENABLED'] = 'false'

# Add code directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))


@pytest.fixture
def rng_seed():
    """Reset numpy RNG to known state before each test."""
    np.random.seed(42)
    return 42


@pytest.fixture
def sample_comparables():
    """Realistic comparable contract amounts (millions) from a single agency."""
    return [5_000_000, 7_200_000, 6_800_000, 8_100_000, 5_500_000,
            6_300_000, 7_900_000, 6_100_000, 5_800_000, 7_500_000]


@pytest.fixture
def small_comparables():
    """Minimal valid set of 3 comparables."""
    return [1_000_000, 1_200_000, 1_100_000]


@pytest.fixture
def doj_cases():
    """Load DOJ prosecuted cases."""
    cases_path = os.path.join(os.path.dirname(__file__), '..', 'prosecuted_cases.json')
    with open(cases_path) as f:
        return json.load(f)['cases']


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with SUNLIGHT schema."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    c = conn.cursor()

    c.execute("""CREATE TABLE contracts (
        contract_id TEXT PRIMARY KEY,
        award_amount REAL,
        vendor_name TEXT,
        agency_name TEXT,
        description TEXT,
        start_date TEXT,
        location TEXT,
        raw_data TEXT,
        raw_data_hash TEXT
    )""")

    c.execute("""CREATE TABLE political_donations (
        vendor_name TEXT,
        recipient_name TEXT,
        amount REAL,
        date TEXT,
        cycle TEXT,
        source TEXT
    )""")

    c.execute("""CREATE TABLE analysis_runs (
        run_id TEXT PRIMARY KEY,
        started_at TEXT,
        completed_at TEXT,
        status TEXT,
        run_seed INTEGER,
        config_json TEXT,
        config_hash TEXT,
        dataset_hash TEXT,
        contracts_analyzed INTEGER,
        n_contracts INTEGER,
        n_scored INTEGER,
        n_errors INTEGER,
        code_commit_hash TEXT,
        environment_json TEXT,
        model_version TEXT,
        summary_json TEXT,
        fdr_n_tests INTEGER,
        fdr_n_significant INTEGER
    )""")

    c.execute("""CREATE TABLE contract_scores (
        score_id TEXT PRIMARY KEY,
        contract_id TEXT,
        run_id TEXT,
        fraud_tier TEXT,
        tier TEXT,
        triage_priority INTEGER,
        confidence_score INTEGER,
        raw_pvalue REAL,
        fdr_adjusted_pvalue REAL,
        survives_fdr INTEGER,
        markup_pct REAL,
        markup_ci_lower REAL,
        markup_ci_upper REAL,
        raw_zscore REAL,
        log_zscore REAL,
        bootstrap_percentile REAL,
        percentile_ci_lower REAL,
        percentile_ci_upper REAL,
        bayesian_prior REAL,
        bayesian_likelihood_ratio REAL,
        bayesian_posterior REAL,
        comparable_count INTEGER,
        insufficient_comparables INTEGER,
        selection_params_json TEXT,
        scored_at TEXT,
        analyzed_at TEXT,
        UNIQUE(contract_id, run_id)
    )""")

    c.execute("""CREATE TABLE audit_log (
        log_id TEXT PRIMARY KEY,
        sequence_number INTEGER UNIQUE,
        timestamp TEXT,
        action_type TEXT,
        entity_id TEXT,
        previous_log_hash TEXT,
        current_log_hash TEXT,
        action TEXT,
        run_id TEXT,
        details TEXT,
        previous_hash TEXT,
        entry_hash TEXT
    )""")

    c.execute("""CREATE TABLE contract_amendments (
        amendment_id TEXT PRIMARY KEY,
        contract_id TEXT,
        modification_number TEXT,
        base_amount REAL,
        current_amount REAL,
        growth_percentage REAL,
        description TEXT,
        effective_date TEXT
    )""")

    conn.commit()
    conn.close()

    yield path

    os.unlink(path)


@pytest.fixture
def populated_db(temp_db):
    """Temp DB with realistic contract data seeded."""
    conn = sqlite3.connect(temp_db)
    c = conn.cursor()

    import hashlib

    # Insert contracts across multiple agencies with varied amounts
    contracts = [
        # Department of Defense — normal range
        ('DOD-001', 5_000_000, 'VENDOR_A', 'Department of Defense', 'Standard equipment maintenance'),
        ('DOD-002', 7_200_000, 'VENDOR_B', 'Department of Defense', 'IT systems upgrade'),
        ('DOD-003', 6_800_000, 'VENDOR_C', 'Department of Defense', 'Technology infrastructure'),
        ('DOD-004', 8_100_000, 'VENDOR_D', 'Department of Defense', 'Communications equipment'),
        ('DOD-005', 5_500_000, 'VENDOR_E', 'Department of Defense', 'Spare parts supply'),
        ('DOD-006', 6_300_000, 'VENDOR_F', 'Department of Defense', 'Training services'),
        ('DOD-007', 7_900_000, 'VENDOR_G', 'Department of Defense', 'Logistics support'),
        ('DOD-008', 6_100_000, 'VENDOR_H', 'Department of Defense', 'Vehicle maintenance'),
        ('DOD-009', 5_800_000, 'VENDOR_I', 'Department of Defense', 'Security systems'),
        ('DOD-010', 7_500_000, 'VENDOR_J', 'Department of Defense', 'Consulting services'),
        # Outlier — 5x the median
        ('DOD-OUTLIER', 35_000_000, 'SUSPECT_VENDOR', 'Department of Defense', 'Special project alpha'),
        # Department of Energy — different range
        ('DOE-001', 2_000_000, 'VENDOR_K', 'Department of Energy', 'Solar panel installation'),
        ('DOE-002', 2_500_000, 'VENDOR_L', 'Department of Energy', 'Wind turbine maintenance'),
        ('DOE-003', 1_800_000, 'VENDOR_M', 'Department of Energy', 'Grid modernization'),
        ('DOE-004', 2_200_000, 'VENDOR_N', 'Department of Energy', 'Nuclear facility support'),
        ('DOE-005', 3_000_000, 'VENDOR_O', 'Department of Energy', 'Research equipment'),
    ]

    for cid, amount, vendor, agency, desc in contracts:
        raw_hash = hashlib.sha256(f"{cid}:{amount}".encode()).hexdigest()
        c.execute(
            "INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, amount, vendor, agency, desc, '2025-01-01', None, None, raw_hash)
        )

    # Political donation for suspect vendor
    c.execute(
        "INSERT INTO political_donations VALUES (?,?,?,?,?,?)",
        ('SUSPECT_VENDOR', 'Senate Armed Services Committee', 500_000,
         '2024-06-01', '2024', 'MOCK_DATA')
    )

    conn.commit()
    conn.close()
    return temp_db
