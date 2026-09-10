"""
Domain profile for Arms Trade Treaty reporting-consistency readings.

All thresholds, citations and the dated embargo table are DATA. Rules
read them through _get_att_param (getattr with default), so a profile
lacking a field degrades to UNASSESSABLE, never to a silent zero.
Nothing here assesses Article 7 and nothing here names a violation.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _get_att_param(profile: Any, name: str, default: Any = None) -> Any:
    return getattr(profile, name, default)


@dataclass
class ATTProfile:
    name: str = "att_reporting_v0"
    # ATT-HIST-001: recipient history
    history_baseline_years: List[int] = field(default_factory=lambda: [2011])
    min_history_items: int = 100
    new_recipient_min_items: int = 500
    # ATT-CONC-001: recipient concentration across exporters
    concentration_min_exporters: int = 3
    # ATT-TRAN-001: transit recurrence
    transit_recurrence_min: int = 2
    # ATT-REP-001: missing subsequent report
    missing_report_min_prior_items: int = 1000
    # Exporter scope for history and concentration (None means all exporters)
    exporter_scope: Optional[List[str]] = None
    # Dated Security Council arms embargoes (destination, resolution, from, to, scope, exemptions)
    embargoes: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"destination": "Yemen", "resolution": "2216 (2015)", "from": 2015, "to": None,
         "scope": "non-state: Houthi and Saleh-affiliated forces", "exemptions": "Government of Yemen and coalition not covered"},
        {"destination": "Libya", "resolution": "1970 (2011)", "from": 2011, "to": None,
         "scope": "state and non-state", "exemptions": "committee-approved supplies; 2819 (2026) training exemption"},
        {"destination": "Somalia", "resolution": "733 (1992); 2713 (2023)", "from": 1992, "to": None,
         "scope": "non-state from 2023 (Al-Shabaab); government exempt with notification earlier", "exemptions": "see resolution text"},
        {"destination": "South Sudan", "resolution": "2428 (2018)", "from": 2018, "to": None,
         "scope": "state and non-state", "exemptions": "committee-approved supplies"},
        {"destination": "Iraq", "resolution": "1546 (2004)", "from": 2004, "to": None,
         "scope": "non-state", "exemptions": "Government of Iraq not covered"},
    ])
    citations: Dict[str, str] = field(default_factory=lambda: {
        "ATT-HIST-001": "ATT Article 11(2): the exporting State Party shall assess the risk of diversion of the export",
        "ATT-CONC-001": "ATT Article 11(3) and 11(5): cooperation and exchange of information to mitigate the risk of diversion",
        "ATT-TRAN-001": "ATT Article 9: transit and trans-shipment; Article 11(2): diversion risk assessment",
        "ATT-REP-001": "ATT Article 13(3): annual report by 31 May on authorized or actual exports and imports of the preceding year",
        "ATT-REP-002": "UN Register of Conventional Arms, General Assembly resolution 46/36 L; ATT Article 13(3)",
        "ATT-EMB-001": "ATT Article 6(1): transfers that would violate Security Council measures under Chapter VII, in particular arms embargoes",
    })
