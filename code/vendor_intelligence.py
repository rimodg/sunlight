"""
Vendor Intelligence — risk profiling for government contractors.

Given a vendor ID (name), aggregates contract history and computes
a composite risk score (0-100) based on:
  - Total awards and average contract value
  - Win rate on sole-source vs competitive bids
  - Agency concentration (revenue dependency on a single agency)
  - Historical pricing anomalies
"""

import sqlite3
import math
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class VendorProfile:
    """Computed risk profile for a single vendor."""

    vendor_name: str
    contract_count: int = 0
    total_awards: float = 0.0
    average_value: float = 0.0
    sole_source_count: int = 0
    competitive_count: int = 0
    sole_source_rate: float = 0.0
    agency_count: int = 0
    top_agency: str = ""
    top_agency_pct: float = 0.0
    concentration_score: float = 0.0  # Herfindahl-Hirschman index, 0-1
    flagged_contract_count: int = 0
    red_count: int = 0
    yellow_count: int = 0
    avg_confidence_score: float = 0.0
    risk_score: float = 0.0  # Composite 0-100
    risk_factors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Component scorers (each returns 0-100)
# ---------------------------------------------------------------------------

def _sole_source_risk(profile: VendorProfile) -> float:
    """High sole-source rate = higher risk. Baseline ~30% is normal for federal."""
    if profile.contract_count == 0:
        return 0.0
    rate = profile.sole_source_rate
    if rate <= 0.30:
        return rate / 0.30 * 20  # 0-20 for normal range
    if rate <= 0.60:
        return 20 + (rate - 0.30) / 0.30 * 40  # 20-60 for elevated
    return 60 + (rate - 0.60) / 0.40 * 40  # 60-100 for extreme


def _concentration_risk(profile: VendorProfile) -> float:
    """Revenue concentration in one agency = dependency risk.

    Uses the Herfindahl-Hirschman Index (HHI) already computed.
    HHI=1.0 means all revenue from one agency; HHI→0 means diversified.
    """
    return min(profile.concentration_score * 100, 100.0)


def _flag_history_risk(profile: VendorProfile) -> float:
    """Prior red/yellow flags increase risk."""
    if profile.contract_count == 0:
        return 0.0
    flag_rate = profile.flagged_contract_count / profile.contract_count
    red_weight = profile.red_count * 3 + profile.yellow_count
    raw = flag_rate * 50 + min(red_weight * 10, 50)
    return min(raw, 100.0)


def _value_outlier_risk(profile: VendorProfile) -> float:
    """Extremely high average contract value relative to count = risk signal."""
    if profile.contract_count == 0 or profile.average_value <= 0:
        return 0.0
    # log-scale: $10M avg with few contracts is suspicious
    log_val = math.log10(max(profile.average_value, 1))
    # Normalize: $100K=5, $1M=6, $10M=7, $100M=8
    if log_val < 6:
        return 0.0
    return min((log_val - 6) * 33, 100.0)


# ---------------------------------------------------------------------------
# Composite risk score
# ---------------------------------------------------------------------------

RISK_WEIGHTS = {
    "sole_source": 0.25,
    "concentration": 0.25,
    "flag_history": 0.35,
    "value_outlier": 0.15,
}


def compute_risk_score(profile: VendorProfile) -> float:
    """Weighted composite risk score, 0-100."""
    components = {
        "sole_source": _sole_source_risk(profile),
        "concentration": _concentration_risk(profile),
        "flag_history": _flag_history_risk(profile),
        "value_outlier": _value_outlier_risk(profile),
    }
    score = sum(components[k] * RISK_WEIGHTS[k] for k in RISK_WEIGHTS)

    factors = []
    if components["sole_source"] > 40:
        factors.append(f"High sole-source rate ({profile.sole_source_rate:.0%})")
    if components["concentration"] > 60:
        factors.append(f"Revenue concentrated in {profile.top_agency} ({profile.top_agency_pct:.0%})")
    if components["flag_history"] > 30:
        factors.append(f"{profile.flagged_contract_count} prior flags ({profile.red_count} RED)")
    if components["value_outlier"] > 30:
        factors.append(f"High avg contract value (${profile.average_value:,.0f})")

    profile.risk_factors = factors
    profile.risk_score = round(min(score, 100.0), 1)
    return profile.risk_score


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def build_vendor_profile(db_path: str, vendor_name: str, run_id: Optional[str] = None) -> VendorProfile:
    """Build a full vendor risk profile from the database.

    Args:
        db_path: Path to SQLite database.
        vendor_name: Exact vendor name to profile.
        run_id: Optional analysis run ID. If None, uses the latest completed run.

    Returns:
        VendorProfile with all fields populated and risk_score computed.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    profile = VendorProfile(vendor_name=vendor_name)

    # --- Contract history ---
    c.execute(
        """
        SELECT COUNT(*) as cnt,
               COALESCE(SUM(award_amount), 0) as total,
               COALESCE(AVG(award_amount), 0) as avg_val
        FROM contracts
        WHERE vendor_name = ?
        """,
        (vendor_name,),
    )
    row = c.fetchone()
    profile.contract_count = row["cnt"]
    profile.total_awards = row["total"]
    profile.average_value = row["avg_val"]

    if profile.contract_count == 0:
        conn.close()
        compute_risk_score(profile)
        return profile

    # --- Sole-source vs competitive (from contracts_clean if available) ---
    c.execute(
        """
        SELECT extent_competed, COUNT(*) as cnt
        FROM contracts_clean
        WHERE vendor_name = ?
        GROUP BY extent_competed
        """,
        (vendor_name,),
    )
    competed_rows = c.fetchall()
    if competed_rows:
        for r in competed_rows:
            ec = (r["extent_competed"] or "").upper()
            if "NOT" in ec or ec == "":
                profile.sole_source_count += r["cnt"]
            else:
                profile.competitive_count += r["cnt"]
        total_competed = profile.sole_source_count + profile.competitive_count
        profile.sole_source_rate = (
            profile.sole_source_count / total_competed if total_competed > 0 else 0.0
        )

    # --- Agency concentration (HHI) ---
    c.execute(
        """
        SELECT agency_name, SUM(award_amount) as agency_total
        FROM contracts
        WHERE vendor_name = ?
        GROUP BY agency_name
        ORDER BY agency_total DESC
        """,
        (vendor_name,),
    )
    agency_rows = c.fetchall()
    profile.agency_count = len(agency_rows)
    if agency_rows and profile.total_awards > 0:
        profile.top_agency = agency_rows[0]["agency_name"]
        profile.top_agency_pct = agency_rows[0]["agency_total"] / profile.total_awards
        # HHI = sum of squared market shares
        shares = [r["agency_total"] / profile.total_awards for r in agency_rows]
        profile.concentration_score = sum(s * s for s in shares)

    # --- Flag history from scoring ---
    if run_id is None:
        c.execute(
            "SELECT run_id FROM analysis_runs WHERE status = 'COMPLETED' ORDER BY completed_at DESC LIMIT 1"
        )
        run_row = c.fetchone()
        if run_row:
            run_id = run_row["run_id"]

    if run_id:
        c.execute(
            """
            SELECT cs.fraud_tier, cs.confidence_score
            FROM contract_scores cs
            JOIN contracts ct ON cs.contract_id = ct.contract_id
            WHERE ct.vendor_name = ? AND cs.run_id = ?
            """,
            (vendor_name, run_id),
        )
        score_rows = c.fetchall()
        confs = []
        for sr in score_rows:
            tier = sr["fraud_tier"]
            if tier in ("RED", "YELLOW"):
                profile.flagged_contract_count += 1
            if tier == "RED":
                profile.red_count += 1
            elif tier == "YELLOW":
                profile.yellow_count += 1
            if sr["confidence_score"] is not None:
                confs.append(sr["confidence_score"])
        if confs:
            profile.avg_confidence_score = sum(confs) / len(confs)

    conn.close()
    compute_risk_score(profile)
    return profile


def build_vendor_profiles_batch(db_path: str, vendor_names: list, run_id: Optional[str] = None) -> list:
    """Build profiles for multiple vendors."""
    return [build_vendor_profile(db_path, v, run_id) for v in vendor_names]
