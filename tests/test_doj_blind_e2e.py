"""
Blind end-to-end DOJ gate: does the REAL scoring engine flag the DOJ cases?

WHAT THIS RUNS
    For each of the 10 DOJ reference cases in tests/fixtures/prosecuted_cases.json
    a synthetic contract is built the way code/doj_validation.py and
    code/evaluation.py build one: award = median(comparables) * (1 + markup/100),
    vendor / agency / description from the case, sole-source and donations flags
    from the legal basis. It is then scored by the same functions the release
    ritual and the worker behind the API call:

        institutional_pipeline.score_contract  ->  institutional_pipeline.assign_tier

    with the doj_federal calibration profile (code/calibration_config.py), a
    per-case seed from derive_contract_seed(42, case_id), and 1,000 bootstrap
    iterations. One test also drives InstitutionalPipeline.run() over a real
    SQLite database (the path jobs.run_scan_pipeline takes for the API worker)
    and checks that it agrees with the function path.

WHERE THE COMPARABLES COME FROM
    The repo's own definition of a realistic peer cohort: the sample_comparables
    fixture in tests/conftest.py ("Realistic comparable contract amounts from a
    single agency", coefficient of variation 0.158). Its ten values are expressed
    as multiples of their median and rescaled to each case's contract size. The
    shape was fixed before any result was looked at; nothing here was tuned to
    pass.

WHAT WAS MEASURED (2026-09-21, python 3.14, numpy from requirements.txt)
    8 of the 9 price-fraud cases are flagged (RED or YELLOW). The 9th, DynCorp
    2005 at the 75% "empirical floor", scores GREEN: its bootstrap lower bound is
    48.9%, below the 66% min_ci_yellow gate. A dispersion sweep shows the floor
    case is flagged only when the peer cohort's coefficient of variation is about
    0.05 or lower. Of the three cases at or above 300% markup, only Boeing reaches
    RED; Oracle (350%) and Lockheed (320%) land at YELLOW because their lower
    bounds (282.8%, 257.3%) sit under the 300% RED gate.

    docs/evaluation_report.json (2026-06-11, real USAspending comparables, not in
    this repo) recorded DynCorp as YELLOW and all three extreme cases as RED. The
    difference is comparables dispersion, which that artifact does not record.

    Those three outcomes are kept as strict xfails below, with this reason. A
    strict xfail is a recorded failure that turns into a hard failure the moment
    the engine's behaviour changes, in either direction. It is not a skip.

HOW THIS RELATES TO THE README
    README: "100% recall on 32 prosecuted reference cases". This gate reproduces
    8/9 on the 9 US price-fraud cases with repo-realistic comparables. See
    CLAIMS.md for the ledger entry.
"""
import json
import logging
import os
import sqlite3
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))
from institutional_pipeline import (  # noqa: E402
    InstitutionalPipeline, assign_tier, derive_contract_seed, score_contract,
)
from institutional_statistical_rigor import BootstrapAnalyzer  # noqa: E402
from calibration_config import get_profile, get_tier_thresholds  # noqa: E402

from tests.doj_fixture import verify_doj_cases_file  # noqa: E402

# Silence the engine's per-decision INFO lines; they are not test output.
logging.getLogger("sunlight.pipeline").setLevel(logging.WARNING)

RUN_SEED = 42
N_BOOTSTRAP = 1000
CALIBRATION_PROFILE = "doj_federal"
FLAGGED = {"RED", "YELLOW"}
NOT_FLAGGED = {"GREEN", "GRAY"}

# tests/conftest.py::sample_comparables, as multiples of its own median.
_SAMPLE_COMPARABLES = np.array(
    [5_000_000, 7_200_000, 6_800_000, 8_100_000, 5_500_000,
     6_300_000, 7_900_000, 6_100_000, 5_800_000, 7_500_000], dtype=float)
COMPARABLES_SHAPE = _SAMPLE_COMPARABLES / np.median(_SAMPLE_COMPARABLES)
COMPARABLES_CV = float(_SAMPLE_COMPARABLES.std(ddof=1) / _SAMPLE_COMPARABLES.mean())  # 0.158

# Measured 2026-09-21 with the shape above. Each entry is a recorded failure
# of a README-level expectation, kept strict so a change in engine behaviour
# cannot pass silently.
FLOOR_CASE_NOT_FLAGGED = pytest.mark.xfail(
    strict=True,
    reason="Measured 2026-09-21: DynCorp 2005 (75% floor) scores GREEN with "
           "CV=0.158 comparables (markup CI lower 48.9 < min_ci_yellow 66). "
           "Flagged only at CV <= ~0.05. README's 100% recall depends on "
           "comparables dispersion that docs/evaluation_report.json does not record.",
)
EXTREME_CASE_NOT_RED = {
    "US_v_Oracle_2011": pytest.mark.xfail(
        strict=True,
        reason="Measured 2026-09-21: Oracle (350%) scores YELLOW, CI lower 282.8 < 300."),
    "US_v_Lockheed_Martin_2012": pytest.mark.xfail(
        strict=True,
        reason="Measured 2026-09-21: Lockheed (320%) scores YELLOW, CI lower 257.3 < 300."),
}


def _load_cases():
    return json.loads(verify_doj_cases_file())["cases"]


def build_case_contract(case, dispersion_scale=1.0):
    """Synthetic contract + peer cohort for one DOJ case.

    Mirrors doj_validation.synthesize_doj_contract: the award is set so the
    markup over the peer median equals the case's documented markup. The peer
    median is derived from the case's own contract amount so the cohort sits at
    a plausible size for that agency. dispersion_scale stretches or shrinks the
    cohort's deviations from its median (1.0 = the repo's sample shape).
    """
    peer_median = case["contract_amount"] / (1 + case["markup_pct"] / 100)
    deviations = COMPARABLES_SHAPE - 1.0
    comparables = ((1.0 + deviations * dispersion_scale) * peer_median).round(2).tolist()
    award = float(np.median(comparables) * (1 + case["markup_pct"] / 100))
    legal = case.get("legal_basis", "").lower()
    return {
        "contract_id": case["case_id"],
        "award_amount": award,
        "vendor_name": case["vendor"],
        "agency_name": case["agency"],
        "description": case["description"],
        "is_sole_source": "sole" in legal,
        "has_donations": "kickback" in legal or "quid pro quo" in case.get("fraud_type", "").lower(),
        "comparables": comparables,
    }


def score_case(case, dispersion_scale=1.0):
    """Run the real scorer over one case. Returns (tier, score_dict)."""
    profile = get_profile(CALIBRATION_PROFILE)
    thresholds = get_tier_thresholds(profile)
    ba = BootstrapAnalyzer(n_iterations=N_BOOTSTRAP)
    config = {"confidence_level": 0.95, "min_comparables": 3}
    contract = build_case_contract(case, dispersion_scale)
    seed = derive_contract_seed(RUN_SEED, case["case_id"])
    score = score_contract(contract, seed, config, ba, calibration_profile=profile)
    # Single-case scoring: no FDR benefit, exactly as doj_validation/evaluation do.
    tier, _priority = assign_tier(score, score.get("raw_pvalue", 1.0), False, thresholds=thresholds)
    return tier, score


_CASES = _load_cases()
_PRICE_CASES = [c for c in _CASES if c["markup_pct"] > 0]
_NON_PRICE_CASES = [c for c in _CASES if c["markup_pct"] == 0]
_EXTREME_CASES = [c for c in _PRICE_CASES if c["markup_pct"] >= 300]


def _param(case, marks_by_id=None, floor_mark=None):
    marks = []
    if floor_mark is not None and case["case_id"] == "US_v_DynCorp_2005":
        marks.append(floor_mark)
    if marks_by_id and case["case_id"] in marks_by_id:
        marks.append(marks_by_id[case["case_id"]])
    return pytest.param(case, id=case["case_id"], marks=marks)


class TestEngineFlagsPriceFraudCases:
    """README: '100% recall means every prosecuted case in the corpus is detected'."""

    @pytest.mark.parametrize("case", [_param(c, floor_mark=FLOOR_CASE_NOT_FLAGGED) for c in _PRICE_CASES])
    def test_price_fraud_case_is_flagged_by_engine(self, case):
        tier, score = score_case(case)
        assert tier in FLAGGED, (
            f"{case['case_id']} ({case['markup_pct']}% markup) scored {tier}; "
            f"markup CI [{score['markup_ci_lower']}, {score['markup_ci_upper']}], "
            f"posterior {score['bayesian_posterior']:.3f}, "
            f"comparables CV {COMPARABLES_CV:.3f}"
        )

    def test_nine_price_fraud_cases_present(self):
        assert len(_PRICE_CASES) == 9

    def test_recall_on_price_fraud_cases_is_recorded(self):
        """Recall through the engine, measured and pinned.

        8/9 with repo-realistic comparables (2026-09-21). If this number moves,
        CLAIMS.md and the xfail above must move with it.
        """
        flagged = sum(1 for c in _PRICE_CASES if score_case(c)[0] in FLAGGED)
        assert flagged == 8, f"engine flagged {flagged}/9 price-fraud cases"


class TestEngineDoesNotFlagNonPriceFraud:
    """README: non-price fraud is outside the statistical price scope."""

    @pytest.mark.parametrize("case", [_param(c) for c in _NON_PRICE_CASES])
    def test_non_price_case_is_not_flagged_by_engine(self, case):
        tier, _ = score_case(case)
        assert tier in NOT_FLAGGED, f"{case['case_id']} (0% markup) scored {tier}"


class TestEngineRedTierForExtremeMarkup:
    """Old constant test claimed cases >= 300% 'map to RED'. Through the engine:"""

    @pytest.mark.parametrize("case", [_param(c, marks_by_id=EXTREME_CASE_NOT_RED) for c in _EXTREME_CASES])
    def test_extreme_markup_case_is_red_by_engine(self, case):
        tier, score = score_case(case)
        assert tier == "RED", (
            f"{case['case_id']} ({case['markup_pct']}% markup) scored {tier}; "
            f"markup CI lower {score['markup_ci_lower']} vs RED gate 300"
        )

    def test_three_extreme_cases_present(self):
        assert {c["case_id"] for c in _EXTREME_CASES} == {
            "US_v_Oracle_2011", "US_v_Boeing_2006", "US_v_Lockheed_Martin_2012"}


class TestFloorCaseDependsOnDispersion:
    """Pins the contingency the README does not state.

    The 75% floor case is flagged when the peer cohort is tight and not when it
    is repo-realistic. Both ends are asserted so a change in either direction is
    visible.
    """

    def _floor_case(self):
        return next(c for c in _CASES if c["case_id"] == "US_v_DynCorp_2005")

    def test_floor_case_flagged_with_tight_cohort(self):
        tier, score = score_case(self._floor_case(), dispersion_scale=0.3)  # CV ~ 0.048
        assert tier in FLAGGED, f"tight cohort: {tier}, CI lower {score['markup_ci_lower']}"

    def test_floor_case_not_flagged_with_repo_realistic_cohort(self):
        tier, score = score_case(self._floor_case(), dispersion_scale=1.0)  # CV 0.158
        assert tier in NOT_FLAGGED, f"repo cohort: {tier}, CI lower {score['markup_ci_lower']}"


class TestWorkerDatabasePathAgreesWithFunctionPath:
    """The API worker path: jobs.run_scan_pipeline -> InstitutionalPipeline.run.

    Each case and its peer cohort are written to a real SQLite database with
    the production schema (tests/conftest.py::temp_db), the pipeline is run,
    and the persisted tier must equal the function-path tier. This is the
    entry point the deployed service actually executes.
    """

    @pytest.mark.parametrize("case", [_param(c) for c in _CASES])
    def test_pipeline_tier_matches_function_tier(self, case, temp_db):
        contract = build_case_contract(case)
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        for i, amount in enumerate(contract["comparables"]):
            cur.execute(
                "INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?)",
                (f"{case['case_id']}-PEER-{i:02d}", amount, f"PEER_VENDOR_{i:02d}",
                 case["agency"], "peer contract", "2025-01-01", None, None, f"peer{i}"))
        cur.execute(
            "INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?)",
            (case["case_id"], contract["award_amount"], case["vendor"], case["agency"],
             case["description"], "2025-01-01", None, None, "case"))
        conn.commit()
        conn.close()

        result = InstitutionalPipeline(temp_db).run(
            run_seed=RUN_SEED, config={"n_bootstrap": N_BOOTSTRAP}, verbose=False,
            calibration_profile=CALIBRATION_PROFILE)
        assert result["n_errors"] == 0

        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT tier, markup_ci_lower FROM contract_scores WHERE contract_id=? AND run_id=?",
            (case["case_id"], result["run_id"])).fetchone()
        conn.close()
        assert row is not None, "case was not scored by the pipeline"
        db_tier, db_ci_lower = row

        fn_tier, fn_score = score_case(case)
        assert db_tier == fn_tier, f"worker path {db_tier} != function path {fn_tier}"
        assert db_ci_lower == pytest.approx(fn_score["markup_ci_lower"], abs=0.05)
