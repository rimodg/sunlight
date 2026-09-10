"""
Arms Trade Treaty reporting-consistency rules over a transfer ledger.

Constitutional rules, enforced by tests:
1. Every output is a reporting-consistency indicator, never a finding of
   violation and never an assessment under Article 7.
2. Deterministic and total: sorted iteration, no wall clock, every
   degenerate input yields a stated result.
3. Missing baseline data yields UNASSESSABLE; a non-filing importer yields
   UNAVAILABLE. Neither is ever rendered as zero or as contradiction.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from collections import defaultdict
from att_profile import ATTProfile, _get_att_param


@dataclass
class TransferRecord:
    year: int
    exporter: str
    importer: str
    items: int
    category: str = ""
    description: str = ""
    origin: str = ""
    intermediate: str = ""
    table: str = "Exports"
    symbol: str = ""
    page: int = 0
    sha256_16: str = ""


@dataclass
class ATTFinding:
    rule_id: str
    rule_name: str
    layer: str
    severity: str           # high | medium | low | info
    status: str             # INDICATOR | UNASSESSABLE | UNAVAILABLE
    year: int
    exporter: Optional[str]
    importer: Optional[str]
    description: str
    evidence: str
    legal_citation: str
    sources: List[str] = field(default_factory=list)


def _cite(profile, rule_id):
    return _get_att_param(profile, "citations", {}).get(rule_id, "citation not stated in profile")


def _in_scope(profile, exporter):
    scope = _get_att_param(profile, "exporter_scope")
    return True if not scope else any(s in exporter for s in scope)


def assess_transfers(records: List[TransferRecord], filers_by_year: Dict[int, List[str]], profile: ATTProfile) -> List[ATTFinding]:
    """Pure function. records: export rows. filers_by_year: states with a
    submission in each year's compilation (for REP rules). Returns findings
    in deterministic order."""
    out: List[ATTFinding] = []
    aliases = _get_att_param(profile, "state_aliases", {}) or {}
    def canon(name):
        for k, v in aliases.items():
            if k in name: name = name.replace(k, v)
        return name
    records = [TransferRecord(r.year, canon(r.exporter), canon(r.importer), r.items, r.category, r.description, canon(r.origin), canon(r.intermediate), r.table, r.symbol, r.page, r.sha256_16) for r in records]
    filers_by_year = {y: [canon(f) for f in fs] for y, fs in filers_by_year.items()}
    ambiguous = [r for r in records if any(ch.isdigit() for ch in r.importer)]
    if ambiguous:
        out.append(ATTFinding("ATT-CAT-000", "Ambiguous importer rows excluded", "ingestion", "info", "UNASSESSABLE", 0, None, None,
                              f"{len(ambiguous)} rows excluded because the importer field carries digits (adapter artifact)", "", "ingestion gate, not a treaty reading"))
    records = [r for r in records if r not in ambiguous]
    exp = sorted((r for r in records if r.table == "Exports" and _in_scope(profile, r.exporter)),
                 key=lambda r: (r.year, r.exporter, r.importer, r.page))
    years = sorted({r.year for r in exp})
    baseline = _get_att_param(profile, "history_baseline_years")
    by_imp_year = defaultdict(int); by_imp_year_exps = defaultdict(set); by_exp_year = defaultdict(int)
    for r in exp:
        by_imp_year[(r.importer, r.year)] += r.items
        by_imp_year_exps[(r.importer, r.year)].add(r.exporter)
        by_exp_year[(r.exporter, r.year)] += r.items

    # ATT-HIST-001 new recipient without prior history
    if baseline is None:
        out.append(ATTFinding("ATT-HIST-001", "Recipient history", "temporal", "info", "UNASSESSABLE", 0, None, None,
                              "profile states no history_baseline_years; recipient history cannot be assessed", "", _cite(profile, "ATT-HIST-001")))
    else:
        min_hist = _get_att_param(profile, "min_history_items", 100); min_new = _get_att_param(profile, "new_recipient_min_items", 500)
        for (imp, yr) in sorted(by_imp_year):
            if yr in baseline: continue
            if not any(y in years for y in baseline):
                out.append(ATTFinding("ATT-HIST-001", "Recipient history", "temporal", "info", "UNASSESSABLE", yr, None, imp,
                                      f"baseline year(s) {baseline} not present in ledger; history for {imp} in {yr} cannot be assessed", "", _cite(profile, "ATT-HIST-001")))
                continue
            prior = sum(by_imp_year.get((imp, y), 0) for y in baseline)
            cur = by_imp_year[(imp, yr)]
            contributing = sorted(by_imp_year_exps[(imp, yr)])
            covered = [e for e in contributing if all(any(e in f for f in filers_by_year.get(y, [])) for y in baseline)]
            if cur >= min_new and prior < min_hist and not covered:
                out.append(ATTFinding("ATT-HIST-001", "Recipient history", "temporal", "info", "UNASSESSABLE", yr, None, imp,
                                      f"{imp} received {cur} declared items in {yr}, but none of the contributing exporters {contributing} filed in baseline {baseline}; zero filings are not zero transfers",
                                      "", _cite(profile, "ATT-HIST-001")))
                continue
            if cur >= min_new and prior < min_hist:
                out.append(ATTFinding("ATT-HIST-001", "New recipient without prior history", "temporal", "high", "INDICATOR", yr, None, imp,
                                      f"{imp} received {cur} declared items in {yr} from in-scope exporters against {prior} in baseline {baseline}",
                                      f"items {yr}={cur}; baseline={prior}; exporters={contributing}; filed in baseline={covered}; not filed in baseline={[e for e in contributing if e not in covered]}", _cite(profile, "ATT-HIST-001")))

    # ATT-CONC-001 recipient concentration across exporters
    k = _get_att_param(profile, "concentration_min_exporters", 3)
    for (imp, yr) in sorted(by_imp_year_exps):
        exps = sorted(by_imp_year_exps[(imp, yr)])
        if len(exps) >= k:
            out.append(ATTFinding("ATT-CONC-001", "Recipient concentration across exporters", "network", "high", "INDICATOR", yr, None, imp,
                                  f"{imp} declared as final importer by {len(exps)} in-scope exporters in {yr}",
                                  f"exporters={exps}; items={by_imp_year[(imp, yr)]}", _cite(profile, "ATT-CONC-001")))

    # ATT-TRAN-001 declared transit nodes and recurrence
    transit_rows = [r for r in exp if r.intermediate.strip()]
    counts = defaultdict(int)
    for r in transit_rows: counts[r.intermediate.strip()] += 1
    tmin = _get_att_param(profile, "transit_recurrence_min", 2)
    for r in transit_rows:
        node = r.intermediate.strip(); rec = counts[node]
        out.append(ATTFinding("ATT-TRAN-001", "Declared transit node", "network", "medium" if rec >= tmin else "low", "INDICATOR", r.year, r.exporter, r.importer,
                              f"{r.exporter} declared {node} as intermediate location for {r.items} items to {r.importer} ({r.category or 'uncategorised'})",
                              f"transit node {node} appears on {rec} in-scope rows", _cite(profile, "ATT-TRAN-001"),
                              [f"{r.symbol} p{r.page} sha {r.sha256_16}"]))

    # ATT-REP-001 missing subsequent report for a heavy exporter
    mmin = _get_att_param(profile, "missing_report_min_prior_items", 1000)
    for (ex, yr) in sorted(by_exp_year):
        nxt = yr + 1
        if by_exp_year[(ex, yr)] >= mmin and nxt in filers_by_year:
            if not any(ex in f for f in filers_by_year[nxt]):
                out.append(ATTFinding("ATT-REP-001", "No submission in the following compilation", "reporting", "high", "INDICATOR", nxt, ex, None,
                                      f"{ex} declared {by_exp_year[(ex, yr)]} in-scope items in {yr} and has no submission in the {nxt} compilation read",
                                      f"filers {nxt}: {len(filers_by_year[nxt])} states; note: the online Register may hold late filings not read", _cite(profile, "ATT-REP-001")))

    # ATT-REP-002 importer report availability
    for (imp, yr) in sorted(by_imp_year):
        if yr in filers_by_year and not any(imp in f for f in filers_by_year[yr]):
            out.append(ATTFinding("ATT-REP-002", "Importer submission unavailable", "reporting", "info", "UNAVAILABLE", yr, None, imp,
                                  f"no submission by {imp} in the {yr} compilation; mirror comparison unavailable, not contradicted", "", _cite(profile, "ATT-REP-002")))

    # ATT-EMB-001 embargo contradiction (dated, exemption-aware at the destination level)
    for r in exp:
        for e in _get_att_param(profile, "embargoes", []):
            if e["destination"] in r.importer and e["from"] <= r.year and (e["to"] is None or r.year <= e["to"]):
                out.append(ATTFinding("ATT-EMB-001", "Declared transfer to an embargoed destination", "prohibition", "high", "INDICATOR", r.year, r.exporter, r.importer,
                                      f"{r.exporter} declared {r.items} items to {r.importer} in {r.year}; destination under {e['resolution']}; scope: {e['scope']}; exemptions: {e['exemptions']}",
                                      "exemption applicability requires human review", _cite(profile, "ATT-EMB-001"), [f"{r.symbol} p{r.page}"]))
    return out
