"""Chain of custody: every result names its source capture and the exact rule
that computed it, and a hash binds them. Constructed cases, then the committed
measured results checked against the rule in this repository."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest
from custody import (SCHEMA, canonical, check_journal, check_results, check_row, cited_sources,
                     digest, rule_version, source_reference, stamp)
from invariant_core import InvariantError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from measure_events_in_order import RULE_MODULE, RULE_PROFILE, current_rule_version, replay  # noqa: E402
from events_in_order import load_profile  # noqa: E402

RESEARCH = ROOT / 'research' / 'events_in_order_2026-11-18'
PROFILE = load_profile(ROOT / RULE_PROFILE)
OUTCOME_KEYS = ('ocid', 'award_id', 'award_date', 'tender_end_date', 'procurement_method',
                'days_award_after_deadline', 'deadline_after_notice_publication', 'state', 'reason')
# sha256 of the 193 outcome tuples (OUTCOME_KEYS, in file order) of results.json
# schema v1 as committed in PR #26 and unchanged by PR #27 (commit 8cb4d46).
# Adding custody must not move one outcome.
V1_OUTCOME_SHA256 = 'ebe4cbf49aa344a301c4ff26cb5f43c44ce5f97b12d6a973d375f3137c86e829'
SOURCE = {'capture_seq': 1549, 'capture_hash': '4d' * 32}
ROW = {'ocid': 'ocds-x', 'award_id': 'ocds-x-1', 'state': 'CONSISTENT', 'reason': 'r'}


def copy_rule_files(tmp_path):
    for rel in (RULE_MODULE, RULE_PROFILE):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    return tmp_path


def version_at(root):
    return rule_version(rule_id='events_in_order', root=root, module=RULE_MODULE, profile=RULE_PROFILE)


def test_rule_version_is_typed_and_cites_every_profile_source():
    rule = current_rule_version()
    assert rule['schema'] == SCHEMA and rule['rule_id'] == 'events_in_order'
    assert rule['rule_module'] == RULE_MODULE and rule['profile'] == RULE_PROFILE
    assert rule['rule_module_sha256'] == hashlib.sha256((ROOT / RULE_MODULE).read_bytes()).hexdigest()
    assert rule['profile_sha256'] == hashlib.sha256((ROOT / RULE_PROFILE).read_bytes()).hexdigest()
    # The profile cites the OCDS release schema and the method codelist.
    assert {c['sha256'] for c in rule['cited_sources']} == {
        'fac192e1ccfb061f5164bdb2d64c29e517c0f81661996b97de40cebc55a2c1bc',
        '8a956d41ead70abe583c6d0121729ec8a0ffb4f1c9aa18017d587ff794d8a589'}
    without = {k: v for k, v in rule.items() if k != 'rule_version_sha256'}
    assert rule['rule_version_sha256'] == digest(without)


def test_rule_version_is_stable_across_locations(tmp_path):
    assert version_at(copy_rule_files(tmp_path)) == current_rule_version()


def test_any_change_to_module_profile_or_cited_source_changes_the_version(tmp_path):
    base = version_at(copy_rule_files(tmp_path))
    module = tmp_path / RULE_MODULE
    module.write_bytes(module.read_bytes() + b'\n# one more line\n')
    changed_module = version_at(tmp_path)
    assert changed_module['rule_version_sha256'] != base['rule_version_sha256']
    module.write_bytes((ROOT / RULE_MODULE).read_bytes())
    profile = tmp_path / RULE_PROFILE
    data = json.loads(profile.read_text())
    data['definitions']['award_date']['source']['sha256'] = 'ab' * 32
    profile.write_text(json.dumps(data, indent=2))
    changed_source = version_at(tmp_path)
    assert changed_source['rule_version_sha256'] not in {base['rule_version_sha256'], changed_module['rule_version_sha256']}
    assert changed_source['cited_sources'] != base['cited_sources']


def test_rule_version_refuses_missing_files_and_uncited_profiles(tmp_path):
    with pytest.raises(InvariantError):
        version_at(tmp_path)
    copy_rule_files(tmp_path)
    (tmp_path / RULE_PROFILE).write_text(json.dumps({'schema': 'x', 'methods': {}}))
    with pytest.raises(InvariantError):
        version_at(tmp_path)
    (tmp_path / RULE_PROFILE).write_text(json.dumps({'schema': 'x', 'a': {'source': 's', 'locator': 'l', 'sha256': 'short'}}))
    with pytest.raises(InvariantError):
        version_at(tmp_path)


def test_cited_sources_are_deduplicated_and_sorted():
    c = {'source': 'https://b', 'locator': 'l', 'sha256': 'ab' * 32}
    d = {'source': 'https://a', 'locator': 'l', 'sha256': 'cd' * 32}
    assert cited_sources({'x': [c, {'y': c}], 'z': d}) == [d, c]


def test_source_reference_requires_both_parts():
    assert source_reference(1549, '4d' * 32) == {'journal': 'watch', 'capture_seq': 1549, 'capture_hash': '4d' * 32}
    for seq, h in ((None, '4d' * 32), (0, '4d' * 32), (True, '4d' * 32), ('1549', '4d' * 32),
                   (1549, None), (1549, ''), (1549, '4D' * 32), (1549, '4d' * 31)):
        with pytest.raises(InvariantError):
            source_reference(seq, h)


def test_stamp_binds_row_source_and_rule():
    rule = current_rule_version()
    stamped = stamp(ROW, source=SOURCE, rule=rule)
    assert stamped['custody'] == {'source': {'journal': 'watch', **SOURCE}, 'rule_id': 'events_in_order',
                                  'rule_version_sha256': rule['rule_version_sha256']}
    body = {k: v for k, v in stamped.items() if k != 'result_sha256'}
    assert stamped['result_sha256'] == digest(body)
    assert check_row(stamped, rule=rule) == []
    assert {k: stamped[k] for k in ROW} == ROW


def test_stamp_refuses_missing_source_restamping_and_untyped_rules():
    rule = current_rule_version()
    with pytest.raises(InvariantError):
        stamp(ROW, source={'capture_seq': None, 'capture_hash': None}, rule=rule)
    with pytest.raises(InvariantError):
        stamp(stamp(ROW, source=SOURCE, rule=rule), source=SOURCE, rule=rule)
    with pytest.raises(InvariantError):
        stamp(ROW, source=SOURCE, rule={'rule_id': 'events_in_order', 'rule_version_sha256': 'ab' * 32})


def test_check_row_finds_every_kind_of_tampering():
    rule = current_rule_version()
    good = stamp(ROW, source=SOURCE, rule=rule)
    assert check_row({**good, 'state': 'INCONSISTENT'}, rule=rule) == ['result_sha256 does not recompute']
    other = {**rule, 'rule_version_sha256': 'ab' * 32}
    assert 'rule_version_sha256 differs from the rule in this repository' in check_row(good, rule=other)
    assert check_row({k: v for k, v in good.items() if k != 'custody'}, rule=rule) == ['custody block missing']
    broken = json.loads(canonical(good))
    broken['custody']['source']['capture_hash'] = 'nope'
    assert 'source reference missing or malformed' in check_row(broken, rule=rule)
    assert 'result_sha256 does not recompute' in check_row(broken, rule=rule)


def test_check_results_ties_rows_to_the_pair_export():
    rule = current_rule_version()
    pairs = {'pairs': [{'ocid': 'ocds-x', 'award_id': 'ocds-x-1', 'award_date': 'a', 'tender_end_date': 't',
                        **SOURCE}]}
    raw = json.dumps(pairs).encode()
    row = stamp({**ROW, 'award_date': 'a', 'tender_end_date': 't'}, source=SOURCE, rule=rule)
    results = {'rule_version': rule, 'input_sha256': hashlib.sha256(raw).hexdigest(), 'results': [row]}
    assert check_results(results, rule=rule, pairs=pairs, pairs_bytes=raw) == []
    wrong_capture = stamp({**ROW, 'award_date': 'a', 'tender_end_date': 't'},
                          source={'capture_seq': 1550, 'capture_hash': '4d' * 32}, rule=rule)
    problems = check_results({**results, 'results': [wrong_capture]}, rule=rule, pairs=pairs, pairs_bytes=raw)
    assert problems == ['row 0: cited capture differs from the pair export']
    problems = check_results({**results, 'input_sha256': 'ab' * 32, 'rule_version': {}}, rule=rule, pairs=pairs, pairs_bytes=raw)
    assert 'file-level rule_version differs from the rule in this repository' in problems
    assert 'input_sha256 does not match the pair export bytes' in problems
    assert 'row count differs from the number of distinct pairs' in check_results(
        {**results, 'results': []}, rule=rule, pairs=pairs, pairs_bytes=raw)


def journal_with(tmp_path, rows):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / 'journal.sqlite3'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE watch_events (seq INTEGER PRIMARY KEY, id TEXT, kind TEXT, at TEXT, payload TEXT, previous TEXT, hash TEXT)')
    db.executemany('INSERT INTO watch_events VALUES (?,?,?,?,?,?,?)', rows)
    db.commit()
    db.close()
    return path


def test_check_journal_links_cited_captures_read_only(tmp_path):
    rule = current_rule_version()
    row = stamp(ROW, source=SOURCE, rule=rule)
    results = {'results': [row]}
    payload = json.dumps({'sha256': 'ab' * 32, 'projection': {}})
    path = journal_with(tmp_path, [(1549, 'id', 'capture', 't', payload, '0' * 64, '4d' * 32)])
    assert check_journal(results, path) == []
    assert check_journal(results, journal_with(tmp_path / 'b', [(1549, 'id', 'capture', 't', payload, '0' * 64, '4e' * 32)])) == [
        'capture seq 1549: journal hash differs from the cited capture hash']
    assert check_journal(results, journal_with(tmp_path / 'c', [(1549, 'id', 'observations', 't', payload, '0' * 64, '4d' * 32)])) == [
        'capture seq 1549: journal event is observations, not capture']
    assert check_journal(results, journal_with(tmp_path / 'd', [])) == ['capture seq 1549: not in journal']
    assert check_journal(results, journal_with(tmp_path / 'e', [(1549, 'id', 'capture', 't', '{}', '0' * 64, '4d' * 32)])) == [
        'capture seq 1549: capture carries no original response sha256']
    # Read-only: the journal bytes are untouched by a check.
    before = path.read_bytes()
    check_journal(results, path)
    assert path.read_bytes() == before


def test_committed_results_carry_custody_that_recomputes_from_this_repository():
    raw = (RESEARCH / 'pairs.json').read_bytes()
    results = json.loads((RESEARCH / 'results.json').read_text())
    assert results['schema'] == 'sunlight.events-in-order-results.v3'
    assert check_results(results, rule=current_rule_version(), pairs=json.loads(raw), pairs_bytes=raw) == []
    assert len(results['results']) == 193
    assert all('custody' in r and 'result_sha256' in r for r in results['results'])
    assert len({r['custody']['source']['capture_seq'] for r in results['results']}) == 25


def test_custody_moved_no_measured_outcome():
    results = json.loads((RESEARCH / 'results.json').read_text())
    outcomes = [[r[k] for k in OUTCOME_KEYS] for r in results['results']]
    assert hashlib.sha256(json.dumps(outcomes, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == V1_OUTCOME_SHA256


def test_replay_with_another_rule_version_is_detected():
    pairs = json.loads((RESEARCH / 'pairs.json').read_text())
    rule = current_rule_version()
    other = {**rule, 'rule_version_sha256': 'ab' * 32}
    out = replay(pairs, PROFILE, other)
    problems = check_results(out, rule=rule, pairs=pairs)
    assert 'file-level rule_version differs from the rule in this repository' in problems
    assert sum(p.endswith('rule_version_sha256 differs from the rule in this repository') for p in problems) == 193


def test_no_em_dash_and_no_personal_shaped_content():
    for path in (ROOT / 'code' / 'custody.py', ROOT / 'scripts' / 'verify_custody.py', RESEARCH / 'results.json'):
        assert chr(0x2014) not in path.read_text()
    assert '@' not in (RESEARCH / 'results.json').read_text()
