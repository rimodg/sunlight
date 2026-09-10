"""ATT reporting-consistency rules: determinism, totality, refusals."""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))
from dataclasses import asdict
from att_profile import ATTProfile, _get_att_param
from att_rules import TransferRecord, assess_transfers

B = ("Serbia","Romania","Slovakia","Croatia","Czech Republic")
def R(year, ex, imp, items, inter="", table="Exports", page=1):
    return TransferRecord(year, ex, imp, items, category="4. Assault rifles", intermediate=inter, table=table, symbol="A/71/138", page=page, sha256_16="abc")

def _ledger():
    return [R(2011, "Slovakia", "Saudi Arabia", 6),
            R(2015, "Serbia", "Saudi Arabia", 60000, inter="Bulgaria", page=62),
            R(2015, "Serbia", "Saudi Arabia", 800, inter="Bulgaria", page=64),
            R(2015, "Romania", "Saudi Arabia", 22000, page=57),
            R(2015, "Slovakia", "Saudi Arabia", 200, page=20),
            R(2015, "Serbia", "Jordan", 105, page=62)]
FILERS = {2011: ["Slovakia","Turkey"], 2015: ["Serbia","Romania","Slovakia","Turkey"], 2016: ["Slovakia","Romania","Turkey"]}
def _prof(**kw):
    p = ATTProfile(exporter_scope=list(B)); [setattr(p, k, v) for k, v in kw.items()]; return p
def by(fs, rid): return [f for f in fs if f.rule_id == rid]

def test_determinism_byte_identical():
    a = [asdict(f) for f in assess_transfers(_ledger(), FILERS, _prof())]
    b = [asdict(f) for f in assess_transfers(_ledger(), FILERS, _prof())]
    assert a == b

def test_no_wall_clock_in_source():
    for m in ("code/att_rules.py", "code/att_profile.py"):
        src = open(m).read()
        assert "datetime.now" not in src and ".today(" not in src and "utcnow" not in src

def test_outputs_never_assess_article7_or_claim_violation():
    """The refusal is a property of what the rules SAY. Generate every rule
    family, including an embargo hit, and assert no output text judges an
    authorization or names a violation."""
    led = _ledger() + [R(2016, "Serbia", "Libya", 10)]
    fs = assess_transfers(led, FILERS, _prof())
    assert {f.rule_id for f in fs} >= {"ATT-HIST-001","ATT-CONC-001","ATT-TRAN-001","ATT-REP-001","ATT-REP-002","ATT-EMB-001"}
    for f in fs:
        text = " ".join([f.rule_name, f.description, f.evidence, f.legal_citation])
        assert not re.search(r"Article 7|should not have been authori|violated|violation of", text), text

def test_total_on_empty_ledger():
    fs = assess_transfers([], {}, _prof())
    assert isinstance(fs, list)

def test_history_fires_on_new_recipient_and_not_on_established():
    fs = by(assess_transfers(_ledger(), FILERS, _prof()), "ATT-HIST-001")
    hit = [f for f in fs if f.importer == "Saudi Arabia" and f.year == 2015 and f.status == "INDICATOR"]
    assert len(hit) == 1 and "against 6 in baseline" in hit[0].description
    led = _ledger() + [R(2011, "Serbia", "Saudi Arabia", 5000)]
    fs2 = by(assess_transfers(led, FILERS, _prof()), "ATT-HIST-001")
    assert not [f for f in fs2 if f.importer == "Saudi Arabia" and f.status == "INDICATOR"]

def test_history_unassessable_when_profile_has_no_baseline():
    fs = by(assess_transfers(_ledger(), FILERS, _prof(history_baseline_years=None)), "ATT-HIST-001")
    assert fs and all(f.status == "UNASSESSABLE" for f in fs)

def test_history_unassessable_when_baseline_year_absent_from_ledger():
    led = [r for r in _ledger() if r.year != 2011]
    fs = by(assess_transfers(led, FILERS, _prof()), "ATT-HIST-001")
    assert fs and all(f.status == "UNASSESSABLE" for f in fs) and "not present in ledger" in fs[0].description

def test_concentration_threshold_from_profile():
    fs = by(assess_transfers(_ledger(), FILERS, _prof()), "ATT-CONC-001")
    assert [f.importer for f in fs] == ["Saudi Arabia"] and "3 in-scope exporters" in fs[0].description
    assert not by(assess_transfers(_ledger(), FILERS, _prof(concentration_min_exporters=4)), "ATT-CONC-001")

def test_transit_recurrence_severity():
    fs = by(assess_transfers(_ledger(), FILERS, _prof()), "ATT-TRAN-001")
    assert len(fs) == 2 and all(f.severity == "medium" for f in fs) and all("Bulgaria" in f.description for f in fs)
    fs2 = by(assess_transfers(_ledger(), FILERS, _prof(transit_recurrence_min=3)), "ATT-TRAN-001")
    assert all(f.severity == "low" for f in fs2)

def test_missing_report_fires_for_absent_heavy_exporter_only():
    fs = by(assess_transfers(_ledger(), FILERS, _prof()), "ATT-REP-001")
    assert [f.exporter for f in fs] == ["Serbia"] and fs[0].year == 2016
    assert "may hold late filings" in fs[0].evidence

def test_importer_unavailable_is_status_not_contradiction():
    fs = by(assess_transfers(_ledger(), FILERS, _prof()), "ATT-REP-002")
    assert fs and all(f.status == "UNAVAILABLE" and f.severity == "info" for f in fs)
    assert all("not contradicted" in f.description for f in fs)

def test_embargo_dated_and_absent_for_this_case():
    assert not by(assess_transfers(_ledger(), FILERS, _prof()), "ATT-EMB-001")
    led = _ledger() + [R(2016, "Serbia", "Libya", 10), R(2010, "Serbia", "Libya", 10)]
    fs = by(assess_transfers(led, FILERS, _prof()), "ATT-EMB-001")
    assert [f.year for f in fs] == [2016] and "requires human review" in fs[0].evidence

def test_exporter_scope_filters():
    led = _ledger() + [R(2015, "Germany", "Saudi Arabia", 90000)]
    fs = by(assess_transfers(led, FILERS, _prof()), "ATT-CONC-001")
    assert "Germany" not in fs[0].evidence

def test_every_finding_carries_citation():
    for f in assess_transfers(_ledger(), FILERS, _prof()):
        assert f.legal_citation and "not stated" not in f.legal_citation

def test_get_att_param_default_is_none_not_zero():
    class Bare: pass
    assert _get_att_param(Bare(), "min_history_items") is None

def test_history_unassessable_when_contributing_exporters_did_not_file_in_baseline():
    """Zero filings are not zero transfers: Serbia never filed in 2011, so a
    2015 surge to Saudi Arabia from Serbia alone must be UNASSESSABLE."""
    led = [R(2011, "Slovakia", "Germany", 50), R(2015, "Serbia", "Saudi Arabia", 60000)]
    fs = by(assess_transfers(led, {2011: ["Slovakia"], 2015: ["Serbia","Slovakia"]}, _prof()), "ATT-HIST-001")
    sa = [f for f in fs if f.importer == "Saudi Arabia"]
    assert sa and sa[0].status == "UNASSESSABLE" and "zero filings are not zero transfers" in sa[0].description

def test_history_fires_when_at_least_one_contributor_filed_in_baseline():
    led = [R(2011, "Slovakia", "Germany", 50), R(2015, "Serbia", "Saudi Arabia", 60000), R(2015, "Slovakia", "Saudi Arabia", 200)]
    fs = by(assess_transfers(led, {2011: ["Slovakia"], 2015: ["Serbia","Slovakia"]}, _prof()), "ATT-HIST-001")
    sa = [f for f in fs if f.importer == "Saudi Arabia" and f.status == "INDICATOR"]
    assert sa and "filed in baseline=['Slovakia']" in sa[0].evidence and "not filed in baseline=['Serbia']" in sa[0].evidence

def test_ambiguous_importer_rows_are_excluded_and_reported():
    led = _ledger() + [R(2015, "Serbia", "Saudi Arabia 38", 500)]
    fs = assess_transfers(led, FILERS, _prof())
    gate = by(fs, "ATT-CAT-000"); assert gate and "1 rows excluded" in gate[0].description
    assert not any("Saudi Arabia 38" in (f.importer or "") for f in fs if f.rule_id != "ATT-CAT-000")

def test_state_aliases_unify_filings_across_years():
    led = [R(2011, "Czech Republic", "Germany", 50), R(2015, "Czechia", "United Arab Emirates", 700)]
    fs = by(assess_transfers(led, {2011: ["Czech Republic"], 2015: ["Czechia"]}, _prof()), "ATT-HIST-001")
    uae = [f for f in fs if f.importer == "United Arab Emirates"]
    assert uae and uae[0].status == "INDICATOR" and "filed in baseline=['Czech Republic']" in uae[0].evidence
