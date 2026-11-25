"""Sealed watchers: a fixed lens (facts read by path, a selection table, one
rule), hashed with the rule into one seal, carried by every result row.
Constructed cases first, then the committed results of both watchers checked
against the seals recomputed from this repository."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest
from custody import check_row, digest
from invariant_core import InvariantError
from watcher import (SCHEMA, SEAL_SCHEMA, check_lens, check_seal, lens, load_watcher, read_context,
                     seal, select)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import measure_events_in_order as eio  # noqa: E402
import measure_section53 as s53  # noqa: E402
from events_in_order import load_profile  # noqa: E402

EIO_WATCHER = 'config/watchers/events-in-order.json'
S53_WATCHER = 'config/watchers/section53.json'
EIO_RESEARCH = ROOT / 'research' / 'events_in_order_2026-11-18'
S53_RESEARCH = ROOT / 'research' / 'section53_2026-11-13' / 'adapter-run'
ACT = {'scheme': 'UKPGA', 'id': '2023/54'}


def copy_tree(tmp_path, *rels):
    for rel in rels:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    return tmp_path


def eio_copy(tmp_path):
    return copy_tree(tmp_path, EIO_WATCHER, eio.RULE_MODULE, eio.RULE_PROFILE)


def rewrite(root, rel, change):
    data = json.loads((root / rel).read_text())
    change(data)
    (root / rel).write_text(json.dumps(data, indent=2) + '\n')


def refused(tmp_path, change, message):
    eio_copy(tmp_path)
    rewrite(tmp_path, EIO_WATCHER, change)
    with pytest.raises(InvariantError, match=message):
        load_watcher(tmp_path, EIO_WATCHER)


def test_watcher_file_is_typed_and_every_part_is_checked():
    watcher = load_watcher(ROOT, EIO_WATCHER)
    assert watcher['schema'] == SCHEMA and watcher['watcher_id'] == 'events_in_order'
    assert watcher['rule'] == {'rule_id': 'events_in_order', 'module': eio.RULE_MODULE, 'profile': eio.RULE_PROFILE}
    assert [f['fact'] for f in watcher['facts']] == ['procurement_method']
    assert load_watcher(ROOT, S53_WATCHER)['facts'][0]['path'] == ['tender', 'legalBasis']


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('otherwise'), 'otherwise required'),
    (lambda d: d.update(extra=1), 'Typed watcher'),
    (lambda d: d.update(watcher_id='Events In Order'), 'slug'),
    (lambda d: d['rule'].update(threshold=1), 'Rule with rule_id'),
    (lambda d: d['facts'][0]['definition'].pop('source'), 'definition with text and source'),
    (lambda d: d['facts'][0]['definition']['source'].update(sha256='abc'), 'without a sha256'),
    (lambda d: d['facts'][0].update(path=[]), 'Fact path required'),
    (lambda d: d['facts'][0].update(kind='score'), 'Fact kind required'),
    (lambda d: d['facts'][0].pop('codes_source'), 'codelist citation'),
    (lambda d: d['facts'].append(dict(d['facts'][0])), 'distinct'),
    (lambda d: d['selection'][0]['when'].update(value_band={'in': ['high']}), 'fact the watcher does not read'),
    (lambda d: d['selection'][0]['when'].update(procurement_method={'in': ['tender']}), 'codes of a code fact only'),
    (lambda d: d['selection'][0]['when'].update(procurement_method={'above': 1}), 'Selection condition'),
    (lambda d: d['selection'][0].update(apply=['section53']), 'only the rule this watcher carries'),
    (lambda d: d['selection'][0].update(when={}), 'at least one fact'),
    (lambda d: d['selection'].clear(), 'At least one selection row'),
    (lambda d: d['otherwise'].update(outcome='UNASSESSABLE'), 'NOT_SELECTED'),
    (lambda d: d['otherwise'].update(reason=' '), 'otherwise reason required'),
])
def test_missing_malformed_or_extra_parts_are_refused(tmp_path, change, message):
    refused(tmp_path, change, message)


def test_seal_hashes_watcher_file_rule_version_and_every_fact_source():
    sealed = seal(ROOT, EIO_WATCHER)
    assert sealed['schema'] == SEAL_SCHEMA and sealed['watcher_id'] == 'events_in_order'
    assert sealed['watcher_file'] == EIO_WATCHER
    assert sealed['watcher_sha256'] == hashlib.sha256((ROOT / EIO_WATCHER).read_bytes()).hexdigest()
    assert sealed['rule_version'] == eio.current_rule_version()
    assert {s['sha256'] for s in sealed['fact_sources']} == {
        'fac192e1ccfb061f5164bdb2d64c29e517c0f81661996b97de40cebc55a2c1bc',
        '8a956d41ead70abe583c6d0121729ec8a0ffb4f1c9aa18017d587ff794d8a589'}
    body = {k: v for k, v in sealed.items() if k != 'watcher_seal_sha256'}
    assert sealed['watcher_seal_sha256'] == digest(body)
    s53_seal = seal(ROOT, S53_WATCHER)
    assert s53_seal['rule_version'] == s53.current_rule_version()
    assert 'cf02d2582249df2eea9c44a1e903548f4e4917a755ff5b38f3425aeb6a2b7cec' in {s['sha256'] for s in s53_seal['fact_sources']}


def test_seal_is_stable_across_locations_and_moves_with_any_part(tmp_path):
    base = seal(eio_copy(tmp_path), EIO_WATCHER)
    assert base == seal(ROOT, EIO_WATCHER)
    # A byte of the watcher file.
    (tmp_path / EIO_WATCHER).write_bytes((ROOT / EIO_WATCHER).read_bytes() + b'\n')
    assert seal(tmp_path, EIO_WATCHER)['watcher_seal_sha256'] != base['watcher_seal_sha256']
    # A byte of the rule module.
    eio_copy(tmp_path)
    (tmp_path / eio.RULE_MODULE).write_bytes((ROOT / eio.RULE_MODULE).read_bytes() + b'\n')
    moved = seal(tmp_path, EIO_WATCHER)
    assert moved['rule_version'] != base['rule_version'] and moved['watcher_seal_sha256'] != base['watcher_seal_sha256']
    # The selection table, with the same facts and rule.
    eio_copy(tmp_path)
    rewrite(tmp_path, EIO_WATCHER, lambda d: d['selection'].pop())
    assert seal(tmp_path, EIO_WATCHER)['watcher_seal_sha256'] != base['watcher_seal_sha256']
    # A cited fact source.
    eio_copy(tmp_path)
    rewrite(tmp_path, EIO_WATCHER, lambda d: d['facts'][0]['codes_source'].update(sha256='ab' * 32))
    assert seal(tmp_path, EIO_WATCHER)['fact_sources'] != base['fact_sources']


def test_facts_are_read_by_path_never_inferred():
    watcher = load_watcher(ROOT, EIO_WATCHER)
    assert read_context(watcher, {'procurement_method': 'open'}) == {
        'facts': {'procurement_method': 'open'}, 'missing': [], 'unreadable': []}
    assert read_context(watcher, {'procurement_method': None})['missing'] == ['procurement_method']
    assert read_context(watcher, {})['missing'] == ['procurement_method']
    assert read_context(watcher, {'procurement_method': 7})['unreadable'] == ['procurement_method']
    assert read_context(watcher, {'procurement_method': ''})['unreadable'] == ['procurement_method']
    # A published code outside the codelist is read as published; selection decides.
    assert read_context(watcher, {'procurement_method': 'tender'})['facts'] == {'procurement_method': 'tender'}
    s53_watcher = load_watcher(ROOT, S53_WATCHER)
    assert read_context(s53_watcher, {'tender': {'legalBasis': {**ACT, 'description': 'x'}}})['facts'] == {'legal_basis': ACT}
    assert read_context(s53_watcher, {'tender': {'legalBasis': {'scheme': 'UKPGA'}}})['unreadable'] == ['legal_basis']
    assert read_context(s53_watcher, {'tender': {}})['missing'] == ['legal_basis']
    assert read_context(s53_watcher, {'tender': 'x'})['missing'] == ['legal_basis']
    with pytest.raises(InvariantError):
        read_context(watcher, ['not', 'a', 'record'])


def test_selection_takes_the_first_matching_row_or_the_otherwise():
    watcher = load_watcher(ROOT, EIO_WATCHER)
    assert select(watcher, read_context(watcher, {'procurement_method': 'direct'})) == {
        'outcome': 'SELECTED', 'row': 0, 'apply': ['events_in_order']}
    assert select(watcher, read_context(watcher, {}))['row'] == 1
    not_selected = select(watcher, read_context(watcher, {'procurement_method': 'tender'}))
    assert not_selected['outcome'] == 'NOT_SELECTED' and not_selected['apply'] == [] and not_selected['row'] is None
    assert not_selected['reason'] == watcher['otherwise']['reason']
    assert select(watcher, read_context(watcher, {'procurement_method': 7}))['outcome'] == 'NOT_SELECTED'
    s53_watcher = load_watcher(ROOT, S53_WATCHER)
    assert select(s53_watcher, read_context(s53_watcher, {'tender': {'legalBasis': ACT}}))['row'] == 0
    for basis in ({'scheme': 'CELEX', 'id': '32014L0024'}, {'scheme': 'UKPGA', 'id': '2023/55'}, None):
        context = read_context(s53_watcher, {'tender': {'legalBasis': basis}})
        assert select(s53_watcher, context)['outcome'] == 'NOT_SELECTED'


def test_lens_and_its_check_find_every_kind_of_tampering():
    watcher, sealed = eio.current_watcher()
    record = {'procurement_method': 'selective'}
    block = lens(watcher, sealed, record)
    assert set(block) == {'watcher_id', 'watcher_seal_sha256', 'context', 'selection'}
    assert block['watcher_seal_sha256'] == sealed['watcher_seal_sha256']
    row = {'ocid': 'x', 'watcher': block}
    assert check_lens(row, watcher=watcher, sealed=sealed, record=record) == []
    cases = {
        'watcher_id differs': lambda b: b.update(watcher_id='section53'),
        'watcher_seal_sha256 differs': lambda b: b.update(watcher_seal_sha256='ab' * 32),
        'context differs': lambda b: b['context']['facts'].update(procurement_method='open'),
        'selection differs': lambda b: b['selection'].update(row=1),
        'parts that are not its own': lambda b: b.update(score=1),
    }
    for message, change in cases.items():
        tampered = copy.deepcopy(block)
        change(tampered)
        problems = check_lens({'watcher': tampered}, watcher=watcher, sealed=sealed, record=record)
        assert any(message in p for p in problems), message
    assert check_lens({'ocid': 'x'}, watcher=watcher, sealed=sealed, record=record) == ['watcher block missing']
    # The lens read from another record does not recompute.
    assert check_lens(row, watcher=watcher, sealed=sealed, record={'procurement_method': 'open'}) == [
        'context differs from the facts read from the record']
    with pytest.raises(InvariantError):
        lens(watcher, {**sealed, 'watcher_id': 'other'}, record)
    assert check_seal({'watcher_seal': sealed}, sealed) == []
    assert check_seal({'watcher_seal': {**sealed, 'watcher_seal_sha256': 'ab' * 32}}, sealed) != []


def test_a_record_the_watcher_does_not_select_gets_no_rule_run():
    pairs = {'pairs': [{'ocid': 'ocds-x', 'award_id': 'ocds-x-1', 'award_date': '2026-01-02T00:00:00Z',
                        'tender_end_date': '2026-01-01T00:00:00Z', 'procurement_method': 'tender',
                        'capture_seq': 3, 'capture_hash': 'ab' * 32}]}
    out = eio.replay(pairs, load_profile(ROOT / eio.RULE_PROFILE))
    row = out['results'][0]
    assert row['watcher']['selection']['outcome'] == 'NOT_SELECTED' and out['not_selected'] == 1
    assert row['state'] == 'UNASSESSABLE' and row['reason'].startswith('Not selected by the watcher: ')
    assert row['days_award_after_deadline'] is None and row['procurement_method'] == 'tender'
    assert check_row(row, rule=eio.current_rule_version()) == []
    captured = json.loads((S53_RESEARCH / 'capture.json').read_text())
    page = captured['pages'][0]
    item = next(i for i in page['projection']['records'] if i['record'].get('contracts'))
    item['record']['tender']['legalBasis'] = {'scheme': 'CELEX', 'id': '32014L0024'}
    page['projection_sha256'] = hashlib.sha256(s53.canonical(page['projection'])).hexdigest()
    out = s53.replay(captured)
    affected = [r for r in out['results'] if r['release_id'] == item['record']['id']]
    assert affected and all(r['assessment'] is None and r['watcher']['selection']['outcome'] == 'NOT_SELECTED' for r in affected)
    assert out['counts']['not_selected_rows'] == len(affected) and out['counts']['contract_notice_rows'] == 150
    assert out['counts']['states'] == {'UNASSESSABLE': 150 - len(affected)}


def test_committed_results_carry_the_lens_that_recomputes_from_this_repository():
    results = json.loads((EIO_RESEARCH / 'results.json').read_text())
    watcher, sealed = eio.current_watcher()
    assert check_seal(results, sealed) == []
    pairs = {(p['ocid'], p['award_id'], p['award_date'], p['tender_end_date']): p
             for p in json.loads((EIO_RESEARCH / 'pairs.json').read_text())['pairs']}
    rows = {0: 0, 1: 0}
    for row in results['results']:
        record = pairs[(row['ocid'], row['award_id'], row['award_date'], row['tender_end_date'])]
        assert check_lens(row, watcher=watcher, sealed=sealed, record=record) == []
        rows[row['watcher']['selection']['row']] += 1
    assert rows == {0: 168, 1: 25} and results['not_selected'] == 0
    assert all(r['watcher']['context']['missing'] == ['procurement_method'] for r in results['results']
               if r['watcher']['selection']['row'] == 1)
    results = json.loads((S53_RESEARCH / 'results.json').read_text())
    watcher, sealed = s53.current_watcher()
    assert check_seal(results, sealed) == []
    assert results['counts']['not_selected_rows'] == 0 and len(results['results']) == 150
    assert all(r['watcher']['context']['facts'] == {'legal_basis': ACT} and r['watcher']['selection']['row'] == 0
               for r in results['results'])


def test_verify_script_reads_only_and_exits_zero_on_both_committed_results(tmp_path, capsys, monkeypatch):
    import verify_watcher as v
    for watcher_file, research, data in ((EIO_WATCHER, EIO_RESEARCH, 'pairs.json'), (S53_WATCHER, S53_RESEARCH, 'capture.json')):
        before = {p: p.stat().st_mtime_ns for p in research.iterdir()}
        monkeypatch.setattr(sys, 'argv', ['verify_watcher.py', watcher_file, str(research / 'results.json'), str(research / data)])
        assert v.main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out['problems'] == [] and out['outcomes']['NOT_SELECTED'] == 0
        assert {p: p.stat().st_mtime_ns for p in research.iterdir()} == before
    tampered = json.loads((EIO_RESEARCH / 'results.json').read_text())
    tampered['results'][4]['watcher']['selection']['row'] = 1
    (tmp_path / 'results.json').write_text(json.dumps(tampered))
    monkeypatch.setattr(sys, 'argv', ['verify_watcher.py', EIO_WATCHER, str(tmp_path / 'results.json'), str(EIO_RESEARCH / 'pairs.json')])
    assert v.main() == 1
    assert json.loads(capsys.readouterr().out)['problems'] == [
        'row 4: selection differs from the sealed selection table', 'row 4: result_sha256 does not recompute']


def test_no_em_dash_no_personal_shaped_content_no_allegation_words():
    for rel in ('code/watcher.py', 'scripts/verify_watcher.py', 'tests/test_watcher.py', EIO_WATCHER, S53_WATCHER):
        text = (ROOT / rel).read_text()
        assert chr(0x2014) not in text, rel
        assert not re.search(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}', text), rel
    for rel in (EIO_WATCHER, S53_WATCHER):
        assert not re.search(r'fraud|corrupt|guilty|illegal|wrongdoing', (ROOT / rel).read_text(), re.I), rel
