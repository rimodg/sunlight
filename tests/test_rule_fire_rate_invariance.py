"""
Tests for TCA rule fire rate invariance across batches (sub-task 2.2.7j).
==========================================================================

Verifies the structural claim that TCA's 16 rules fire at proportionally
invariant rates across batches of contracts under a fixed profile — the
property that makes per-batch findings comparable across UNDP country offices.

Methodology:
    200 clean contracts loaded via the deterministic seeded sample
    (sunlight-doj-v1), partitioned into 4 batches of 50, each batch run
    under us_federal profile. Per-rule fire rates computed per batch,
    coefficient of variation computed across batches per rule.

Three tests:
    1. Per-rule CV invariance: all per-rule CVs (excluding zero-fire rules)
       must be below 0.5.
    2. Zero-fire rule reporting: rules that never fire are surfaced as
       institutional information (not asserted).
    3. Aggregate fire-rate band: total fire rate per batch within ±20% of
       cross-batch mean.

Run with:  pytest tests/test_rule_fire_rate_invariance.py -v -s
"""

import os
import sys
import random
import sqlite3
import statistics
from collections import defaultdict
from typing import Dict, List

import pytest

# Ensure code/ is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from sunlight_core import ContractDossier
from tca_rules import TCAGraphRuleEngine
from jurisdiction_profile import US_FEDERAL


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

# Same deterministic seed as DOJ regression clean sample
SAMPLE_SEED = "sunlight-doj-v1"

# Production DB: one level above the git repo root
PRODUCTION_DB = os.path.join(
    os.path.dirname(__file__), '..', '..', 'data', 'sunlight.db'
)

SAMPLE_SIZE = 200
N_BATCHES = 4
BATCH_SIZE = SAMPLE_SIZE // N_BATCHES  # 50

# Per-rule CV threshold: fire rate coefficient of variation across batches.
# 0.5 is conservative — below this, batch-to-batch comparison is defensible.
CV_THRESHOLD = 0.5

# Aggregate fire-rate band: ±20% of cross-batch mean.
AGGREGATE_BAND = 0.20


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _resolve_db_path() -> str:
    """Resolve the production DB path, or skip tests if unavailable."""
    candidate = os.path.abspath(PRODUCTION_DB)
    if os.path.exists(candidate):
        return candidate
    env_path = os.environ.get("SUNLIGHT_DB_PATH")
    if env_path and os.path.exists(env_path):
        return os.path.abspath(env_path)
    pytest.skip(
        "Production DB not found — invariance tests require the production DB. "
        "Set SUNLIGHT_DB_PATH or run from the SUNLIGHT root directory."
    )


def _load_clean_contracts(db_path: str, n: int = 200) -> List[Dict]:
    """
    Load clean contracts from production DB using the same deterministic
    seed as the DOJ regression (sunlight-doj-v1).

    Returns flat dicts with all available DB columns.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        WITH agency_medians AS (
            SELECT agency_name, AVG(award_amount) as med_amount
            FROM contracts
            WHERE award_amount > 0
            GROUP BY agency_name
            HAVING COUNT(*) >= 10
        )
        SELECT c.contract_id, c.award_amount, c.vendor_name, c.agency_name,
               c.description, c.start_date, c.location
        FROM contracts c
        JOIN agency_medians am ON c.agency_name = am.agency_name
        WHERE c.award_amount < am.med_amount
        AND c.award_amount > 100000
        ORDER BY c.contract_id
    """)
    all_rows = [dict(row) for row in c.fetchall()]
    conn.close()

    rng = random.Random(SAMPLE_SEED)
    return rng.sample(all_rows, min(n, len(all_rows)))


def _contract_to_dossier(row: Dict) -> ContractDossier:
    """
    Convert a flat DB contract row into a ContractDossier with
    realistic OCDS structure for TCA rule evaluation.

    Uses all available DB fields (start_date for temporal rules,
    award_amount for financial rules, etc.) to maximize the number
    of rules that can fire and make the invariance test meaningful.
    """
    amount = row["award_amount"]
    vendor = row["vendor_name"] or "Unknown Vendor"
    agency = row["agency_name"] or "Unknown Agency"
    start_date = row.get("start_date") or ""

    raw_ocds = {
        "ocid": f"ocds-US-{row['contract_id']}",
        "tag": ["US"],
        "parties": [
            {
                "name": agency,
                "roles": ["buyer"],
                "address": {"countryName": "us"},
            },
            {
                "name": vendor,
                "id": f"US-{row['contract_id']}-vendor",
                "roles": ["supplier"],
                "address": {"countryName": "us"},
            },
        ],
        "tender": {
            "value": {"amount": amount, "currency": "USD"},
            "procurementMethod": "open",
            "numberOfTenderers": None,
            "mainProcurementCategory": "goods",
        },
        "awards": [{
            "value": {"amount": amount, "currency": "USD"},
            "date": start_date,
        }],
    }

    return ContractDossier(
        contract_id=row["contract_id"],
        ocid=f"ocds-US-{row['contract_id']}",
        raw_ocds=raw_ocds,
        buyer_name=agency,
        supplier_name=vendor,
        procurement_method="open",
        tender_value=amount,
        award_value=amount,
        currency="USD",
        number_of_tenderers=None,
        award_date=start_date,
        country_code="US",
        sector="goods",
    )


def _run_batch(engine: TCAGraphRuleEngine, contracts: List[Dict]) -> Dict[str, int]:
    """
    Run a batch of contracts through the TCA engine and return
    per-rule fire counts.
    """
    fire_counts = defaultdict(int)
    all_rules = set()

    for row in contracts:
        dossier = _contract_to_dossier(row)
        engine.build_graph(dossier)
        rule_fire_log = dossier.graph["metadata"]["rule_fire_log"]
        for rule_id, fired in rule_fire_log.items():
            all_rules.add(rule_id)
            if fired:
                fire_counts[rule_id] += 1

    # Ensure all rules are represented (even those that never fired)
    for rule_id in all_rules:
        if rule_id not in fire_counts:
            fire_counts[rule_id] = 0

    return dict(fire_counts)


# ═══════════════════════════════════════════════════════════════════════════
# Fixture: shared across all three tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def batch_fire_rates():
    """
    Load 200 clean contracts, partition into 4 batches of 50,
    run each batch through TCA under us_federal profile, and
    compute per-rule fire rates per batch.

    Returns dict with batch_results, all_rule_ids, n_batches, batch_size.
    """
    db_path = _resolve_db_path()
    contracts = _load_clean_contracts(db_path, SAMPLE_SIZE)
    assert len(contracts) >= SAMPLE_SIZE, (
        f"Expected {SAMPLE_SIZE} contracts, got {len(contracts)}"
    )

    # Partition into N_BATCHES equal batches
    batches = [
        contracts[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        for i in range(N_BATCHES)
    ]
    assert all(len(b) == BATCH_SIZE for b in batches)

    # Run each batch through the engine (fresh engine per batch for isolation)
    batch_results = []
    for batch in batches:
        engine = TCAGraphRuleEngine(profile=US_FEDERAL)
        fire_counts = _run_batch(engine, batch)
        fire_rates = {
            rule_id: count / BATCH_SIZE
            for rule_id, count in fire_counts.items()
        }
        batch_results.append(fire_rates)

    # Collect all rule IDs seen across all batches
    all_rule_ids = set()
    for rates in batch_results:
        all_rule_ids.update(rates.keys())

    return {
        "batch_results": batch_results,
        "all_rule_ids": sorted(all_rule_ids),
        "n_batches": N_BATCHES,
        "batch_size": BATCH_SIZE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Test Suite
# ═══════════════════════════════════════════════════════════════════════════


class TestRuleFireRateInvariance:
    """Tests covering rule fire rate stability across contract batches."""

    def test_per_rule_cv_below_threshold(self, batch_fire_rates):
        """
        For each TCA rule that fires at least once across all batches,
        the coefficient of variation of its fire rate across batches
        must be below 0.5.

        Rules that never fire have undefined CV and are treated as PASS
        (no drift possible if no fires). They are reported separately
        in test_zero_fire_rules_reported.
        """
        results = batch_fire_rates["batch_results"]
        all_rules = batch_fire_rates["all_rule_ids"]
        batch_size = batch_fire_rates["batch_size"]

        cv_table = {}
        zero_fire_rules = []
        violations = []

        for rule_id in all_rules:
            rates = [r.get(rule_id, 0.0) for r in results]
            total_fires = sum(
                r.get(rule_id, 0.0) * batch_size for r in results
            )

            if total_fires == 0:
                zero_fire_rules.append(rule_id)
                cv_table[rule_id] = {
                    "rates": rates, "cv": None, "zero_fire": True,
                }
                continue

            mean_rate = statistics.mean(rates)
            if mean_rate == 0:
                zero_fire_rules.append(rule_id)
                cv_table[rule_id] = {
                    "rates": rates, "cv": None, "zero_fire": True,
                }
                continue

            stdev = statistics.stdev(rates) if len(rates) > 1 else 0.0
            cv = stdev / mean_rate
            cv_table[rule_id] = {
                "rates": [round(r, 4) for r in rates],
                "mean": round(mean_rate, 4),
                "stdev": round(stdev, 4),
                "cv": round(cv, 4),
                "zero_fire": False,
            }

            if cv > CV_THRESHOLD:
                violations.append((rule_id, cv, rates))

        # Print the full CV table for institutional auditability
        print("\n" + "=" * 88)
        print("PER-RULE FIRE RATE CV TABLE")
        print(f"Profile: us_federal | Batches: {N_BATCHES} x {BATCH_SIZE} contracts")
        print("=" * 88)
        header = (
            f"{'Rule ID':<12} "
            f"{'B1':>6} {'B2':>6} {'B3':>6} {'B4':>6} "
            f"{'Mean':>8} {'StdDev':>8} {'CV':>8} {'Status':>8}"
        )
        print(header)
        print("-" * 88)

        for rule_id in all_rules:
            entry = cv_table[rule_id]
            rates = entry["rates"]
            rate_str = " ".join(f"{r:>6.2f}" for r in rates)
            if entry["zero_fire"]:
                print(f"{rule_id:<12} {rate_str} {'—':>8} {'—':>8} {'—':>8} {'ZERO':>8}")
            else:
                status = "PASS" if entry["cv"] <= CV_THRESHOLD else "DRIFT"
                print(
                    f"{rule_id:<12} {rate_str} "
                    f"{entry['mean']:>8.4f} {entry['stdev']:>8.4f} "
                    f"{entry['cv']:>8.4f} {status:>8}"
                )

        print("=" * 88)
        print(f"Firing rules: {len(all_rules) - len(zero_fire_rules)} | "
              f"Zero-fire rules: {len(zero_fire_rules)} | "
              f"CV threshold: {CV_THRESHOLD}")
        print("=" * 88)

        if violations:
            msg_parts = [
                f"  {rid}: CV={cv:.4f}, rates={[round(r, 4) for r in rates]}"
                for rid, cv, rates in violations
            ]
            pytest.fail(
                f"Rule fire rate drift detected ({len(violations)} rules exceed "
                f"CV threshold {CV_THRESHOLD}):\n" + "\n".join(msg_parts)
            )

    def test_zero_fire_rules_reported(self, batch_fire_rates):
        """
        Rules that never fire across any batch are reported as institutional
        information. Not asserted — a rule that never fires on the production
        sample is a known characteristic, not a drift signal.
        """
        results = batch_fire_rates["batch_results"]
        all_rules = batch_fire_rates["all_rule_ids"]
        batch_size = batch_fire_rates["batch_size"]

        zero_fire_rules = []
        for rule_id in all_rules:
            total_fires = sum(
                r.get(rule_id, 0.0) * batch_size for r in results
            )
            if total_fires == 0:
                zero_fire_rules.append(rule_id)

        print("\n" + "=" * 60)
        print("ZERO-FIRE RULES (never fired across any batch)")
        print("=" * 60)
        if zero_fire_rules:
            for rule_id in zero_fire_rules:
                print(f"  {rule_id}")
            print(f"\nTotal: {len(zero_fire_rules)} of {len(all_rules)} rules "
                  f"never fired on {SAMPLE_SIZE} clean contracts")
        else:
            print("  (all rules fired at least once)")
        print("=" * 60)

        # Informational test — always passes
        assert True

    def test_aggregate_fire_rate_band(self, batch_fire_rates):
        """
        The aggregate fire rate (sum of per-rule fire rates) per batch
        must be within ±20% of the cross-batch mean. This catches
        systemic drift even if individual rules look stable.
        """
        results = batch_fire_rates["batch_results"]

        # Aggregate fire rate per batch = sum of all per-rule fire rates
        aggregate_rates = []
        for batch_rates in results:
            aggregate_rates.append(sum(batch_rates.values()))

        mean_agg = statistics.mean(aggregate_rates)

        print("\n" + "=" * 60)
        print("AGGREGATE FIRE RATE PER BATCH")
        print("=" * 60)
        for i, rate in enumerate(aggregate_rates):
            deviation = (
                (rate - mean_agg) / mean_agg * 100 if mean_agg > 0 else 0
            )
            print(f"  Batch {i+1}: {rate:.4f} ({deviation:+.1f}% from mean)")
        print(f"  Mean:    {mean_agg:.4f}")
        print(f"  Band:    ±{AGGREGATE_BAND * 100:.0f}%")
        print("=" * 60)

        if mean_agg == 0:
            pytest.skip("No rules fired across any batch — cannot test band")

        for i, rate in enumerate(aggregate_rates):
            deviation = abs(rate - mean_agg) / mean_agg
            assert deviation <= AGGREGATE_BAND, (
                f"Batch {i+1} aggregate fire rate {rate:.4f} deviates "
                f"{deviation:.1%} from mean {mean_agg:.4f} "
                f"(limit: ±{AGGREGATE_BAND:.0%})"
            )
