"""
Ingestion quality assessor. A deterministic report of what the engines
saw when a contract entered the pipeline, so a finding's provenance can
honestly state its input-quality context.

Constitutional rules of this module, enforced by tests:
1. Never modifies the composite. The score is REPORTED on findings; it
   does not widen confidence intervals, downrank verdicts, or influence
   any downstream computation.
2. Deterministic and total: same dossier yields the same report; every
   degenerate input yields a stated result, never a raise.
3. No wall clock. The score is a function of dossier content.
4. Equal weighting per engine-consumed field. Any future weight change
   is a versioned Phase 1.1 change with proof of necessity.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, List


# The 15 dossier fields the CRI/TCA/EVG engines actually consume from
# ingestion. Excludes: engine-computed outputs (entity/price/structure/
# gate/recovery/lead/outcome), mode/state (stage/mode/errors), metadata
# (dossier_id/ocid/contract_id/graph/created_at/updated_at/processing_ms/
# methodology_version/disclaimer), and raw_ocds (the source, not a
# structural input judged for presence).
ENGINE_CONSUMED_FIELDS = (
    "country_code",
    "country_name",
    "buyer_name",
    "buyer_id",
    "supplier_name",
    "supplier_id",
    "suppliers",
    "tender_value",
    "award_value",
    "currency",
    "procurement_method",
    "number_of_tenderers",
    "tender_start",
    "tender_end",
    "award_date",
)

SCORING_VERSION = "ingestion_quality_v1"


@dataclass
class IngestionQualityReport:
    """What the engines saw at ingestion, in the dossier's own units."""
    data_quality_score: float
    missing_fields: List[str]
    fields_present: int
    fields_total: int
    scoring_version: str = SCORING_VERSION

    def to_provenance(self) -> dict:
        """Serializable form for inclusion in finding provenance blocks."""
        return {
            "data_quality_score": round(self.data_quality_score, 4),
            "missing_fields": list(self.missing_fields),
            "fields_present": self.fields_present,
            "fields_total": self.fields_total,
            "scoring_version": self.scoring_version,
        }


def _is_present(value: Any) -> bool:
    """A field is present when it holds a non-empty value of the expected
    type. None, empty string, empty list, and zero for numeric fields all
    count as missing. This is the honest read of what the engine received."""
    if value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    return True


def assess_ingestion_quality(dossier: Any) -> IngestionQualityReport:
    """Pure function: reads dossier fields, returns a quality report.

    Never raises: a dossier missing an expected field entirely (via
    getattr default) is treated the same as a field with a missing value.
    """
    missing = []
    for field_name in ENGINE_CONSUMED_FIELDS:
        value = getattr(dossier, field_name, None)
        if not _is_present(value):
            missing.append(field_name)

    total = len(ENGINE_CONSUMED_FIELDS)
    present = total - len(missing)
    score = present / total  # equal weight per field

    return IngestionQualityReport(
        data_quality_score=score,
        missing_fields=missing,
        fields_present=present,
        fields_total=total,
    )
