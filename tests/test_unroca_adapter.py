"""UN Register compilation adapter: determinism, band derivation, quarantine.

Fixture: four pages of A/71/138 (2015 compilation) covering the three layouts
the adapter must handle: a main table with "Final importer", a main table with
"Trading partner" (Slovakia), and the small-arms section with numbered
categories and a split header.
"""
import sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))
from unroca_adapter import parse

FIX = str(Path(__file__).parent / "fixtures" / "unroca" / "A71138_pages_17_20_57_62.pdf")

def _recs():
    return parse(FIX, "A/71/138", 2015)

def test_parses_records_from_all_three_layouts():
    recs = _recs()
    assert len(recs) > 20
    states = {r['state'] for r in recs if r['state']}
    assert {"Serbia", "Slovakia", "Romania"} <= states

def test_determinism_byte_identical():
    assert _recs() == _recs()

def test_serbia_mortar_row_columns_are_correctly_separated():
    """The row that must never regress: origin and transit are different columns."""
    recs = _recs()
    row = [r for r in recs if r['state'] == "Serbia" and "Saudi Arabia" in r['importer'] and r['number'] == 500]
    assert len(row) == 1
    r = row[0]
    assert "Bosnia" in r['origin'], r
    assert r['intermediate'].strip() == "Bulgaria", r
    assert "Mortar" in r['description']
    assert r['table'] == "Exports" and r['page'] == 1

def test_trading_partner_header_variant_is_read():
    recs = _recs()
    assert [r for r in recs if r['state'] == "Slovakia" and r['importer'].strip()]

def test_small_arms_numbered_categories_are_carried():
    recs = _recs()
    salw = [r for r in recs if r['category'] and r['category'][0].isdigit()]
    assert salw, "numbered small-arms categories not parsed"

def test_every_record_carries_source_locator_and_hash():
    sha = hashlib.sha256(open(FIX, 'rb').read()).hexdigest()[:16]
    for r in _recs():
        assert r['symbol'] == "A/71/138" and r['year'] == 2015
        assert r['page'] >= 1 and r['sha256_16'] == sha

def test_numbers_are_integers_and_never_negative():
    assert all(isinstance(r['number'], int) and r['number'] >= 0 for r in _recs())

def test_no_wall_clock_in_adapter():
    src = open(str(Path(__file__).parent.parent / "code" / "unroca_adapter.py")).read()
    assert "datetime.now" not in src and ".today(" not in src and "utcnow" not in src
