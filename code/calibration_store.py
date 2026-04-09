"""
SUNLIGHT Empirical Calibration Store
=====================================

Per-profile operational statistics accumulator for the monotonic-learning
property. Observes what flows through the pipeline to build a progressively
sharper estimate of the normal contract distribution for each jurisdiction
profile, without ever learning from detection output, rule definitions, or
fraud patterns.

Architectural separation: the store learns "what normal looks like" from
operational flow; the Jurisprudence corpus teaches "what fraud looks like"
from external legal validation; the two channels never cross.

This is phase one (observation only). Phase two (future sub-task 2.2.7l)
will wire the accumulated distributions into the detection path as empirical
priors.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile


@dataclass
class BatchObservation:
    """
    Per-contract observation passed to the empirical calibration store.
    Intentionally minimal and free of FastAPI/Pydantic dependencies so
    the store module can be imported and tested in isolation.
    """
    verdict: str
    confidence: float
    risk_score: float
    fired_rule_ids: List[str]


@dataclass
class EmpiricalCalibrationState:
    """
    Per-profile running empirical statistics accumulated from operational
    flow. Holds only observational data about what SUNLIGHT has analyzed;
    never holds rule definitions, fraud patterns, threshold values, or
    anything learned from detection output.

    The store's monotonic-learning property: every field that represents
    a count or sum only grows over operational time, never shrinks. The
    accumulated statistics become a progressively sharper estimate of the
    normal contract distribution for this jurisdiction profile, which is
    the empirical baseline that future phases (2.2.7l onward) will consume
    to refine the statistical posterior in the detection path.

    Fields are initialized to zero/empty and updated in-place by the
    update_from_batch() method. Persistence is handled by the store class,
    not by the state itself.
    """
    profile_name: str
    total_contracts_analyzed: int = 0
    verdict_counts: Dict[str, int] = field(default_factory=dict)
    rule_fire_counts: Dict[str, int] = field(default_factory=dict)
    risk_score_sum: float = 0.0
    risk_score_sum_squared: float = 0.0
    risk_score_min: Optional[float] = None
    risk_score_max: Optional[float] = None
    first_observation_utc: Optional[str] = None
    last_observation_utc: Optional[str] = None
    schema_version: str = "1.0"

    def mean_risk_score(self) -> Optional[float]:
        """
        Running mean of risk scores observed in this profile. Returns
        None if no contracts have been analyzed yet.
        """
        if self.total_contracts_analyzed == 0:
            return None
        return self.risk_score_sum / self.total_contracts_analyzed

    def variance_risk_score(self) -> Optional[float]:
        """
        Running variance of risk scores via the sum-of-squares formula.
        Numerically stable enough for the scales SUNLIGHT operates at
        (up to ~10^8 observations). Returns None if fewer than 2
        contracts have been analyzed.
        """
        n = self.total_contracts_analyzed
        if n < 2:
            return None
        mean = self.risk_score_sum / n
        return (self.risk_score_sum_squared / n) - (mean * mean)

    def rule_fire_rate(self, rule_id: str) -> Optional[float]:
        """
        Observed fire rate for the given rule across all contracts in
        this profile. Returns None if no contracts observed or the rule
        has never fired (the caller should distinguish 'never observed'
        from 'fire rate of zero' based on total_contracts_analyzed).
        """
        if self.total_contracts_analyzed == 0:
            return None
        return self.rule_fire_counts.get(rule_id, 0) / self.total_contracts_analyzed


class EmpiricalCalibrationStore:
    """
    Per-profile empirical calibration store with atomic persistence.

    Each profile's state is held in a separate JSON file at
    {base_dir}/empirical_{profile_name}.json. Writes are atomic via
    the write-temp-then-rename pattern so concurrent readers never see
    a partially-written file. Reads are straight JSON loads with a
    fresh state returned if the file does not yet exist.

    The store is designed for single-writer scenarios (the SUNLIGHT
    API process), not for distributed concurrent writes. If SUNLIGHT
    is ever deployed as multiple API replicas, the store will need to
    move to a shared backend (SQLite row lock, Redis, etc.) — but
    that migration is out of scope for phase one. The current design
    is correct for the intended single-process deployment.
    """

    def __init__(self, base_dir: str = "calibration"):
        # Allow environment variable override for testing
        base_dir = os.environ.get('SUNLIGHT_CALIBRATION_DIR', base_dir)
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, profile_name: str) -> Path:
        """Return the filesystem path for a profile's state file."""
        safe = "".join(c for c in profile_name if c.isalnum() or c in ("_", "-"))
        if not safe:
            raise ValueError(f"Invalid profile name for store path: {profile_name!r}")
        return self.base_dir / f"empirical_{safe}.json"

    def load(self, profile_name: str) -> EmpiricalCalibrationState:
        """
        Load the current state for a profile. If no state file exists,
        return a fresh zero-initialized state — not an error. The store
        treats absence as "no observations yet" rather than failure.
        """
        path = self._path_for(profile_name)
        if not path.exists():
            return EmpiricalCalibrationState(profile_name=profile_name)
        with open(path, "r") as f:
            data = json.load(f)
        return EmpiricalCalibrationState(**data)

    def save(self, state: EmpiricalCalibrationState) -> None:
        """
        Persist state atomically. Writes to a temporary file in the
        same directory, then renames it over the target path. On POSIX
        filesystems the rename is atomic, so concurrent readers always
        see either the previous consistent state or the new consistent
        state — never a partial write.
        """
        path = self._path_for(state.profile_name)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self.base_dir,
            prefix=f".empirical_{state.profile_name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(asdict(state), f, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def update_from_batch(
        self,
        profile_name: str,
        batch_observations: List[BatchObservation],
    ) -> EmpiricalCalibrationState:
        """
        Update the stored state with observations from a completed batch
        analysis. Loads current state, applies all updates atomically
        in memory, writes the new state to disk via save().

        The function is idempotent with respect to the current state
        content but NOT with respect to time: calling it twice with
        the same batch observations will double-count those observations,
        because the store has no notion of batch identity or dedup. The
        caller is responsible for calling update_from_batch() exactly
        once per completed batch.

        Every field updated here is a pure accumulator (sum, count, min,
        max). No field is ever reduced, cleared, or overwritten based on
        the new observations. This is the monotonic-learning property
        enforced at the implementation level.
        """
        state = self.load(profile_name)
        now = datetime.now(timezone.utc).isoformat()
        if state.first_observation_utc is None:
            state.first_observation_utc = now
        state.last_observation_utc = now

        for obs in batch_observations:
            state.total_contracts_analyzed += 1
            verdict = obs.verdict.lower()
            state.verdict_counts[verdict] = state.verdict_counts.get(verdict, 0) + 1
            for rule_id in obs.fired_rule_ids:
                state.rule_fire_counts[rule_id] = state.rule_fire_counts.get(rule_id, 0) + 1
            rs = obs.risk_score
            state.risk_score_sum += rs
            state.risk_score_sum_squared += rs * rs
            if state.risk_score_min is None or rs < state.risk_score_min:
                state.risk_score_min = rs
            if state.risk_score_max is None or rs > state.risk_score_max:
                state.risk_score_max = rs

        self.save(state)
        return state
