"""Chain of custody for section 53 results: every row names the capture-file
page it was computed from and the exact rule that computed it, and a hash
binds them. Constructed cases, then the committed measured results checked
against the rule in this repository."""
import hashlib
import json
from pathlib import Path
import sys

import pytest
from custody import (SCHEMA, any_source_reference, check_capture_file, check_results, check_row,
                     digest, page_reference, rule_version, stamp)
from invariant_core import InvariantError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from measure_section53 import CAPTURE_FILE, RULE_MODULE, RULE_PROFILE, canonical, current_rule_version, replay  # noqa: E402

RESEARCH = ROOT / 'research' / 'section53_2026-11-13' / 'adapter-run'
# sha256 (custody.digest) of the list of 150 result rows of results.json schema
# v1 as committed at PR #28 head 39d1f48 (every field of every row, file order).
# Adding custody, then the sealed watcher's lens, must not move one outcome.
V1_ROWS_SHA256 = 'eea5124b4ba8d0a15f69929bca34abde5d69afb05dd991b99b2bbbdc243786d9'
PAGE = {'capture_file': 'research/x/capture.json', 'page': 0, 'source_sha256': 'ab' * 32, 'projection_sha256': 'cd' * 32}
ROW = {'ocid': 'ocds-x', 'release_id': 'r-1', 'page': 0, 'source_sha256': 'ab' * 32, 'source_url': 'https://example.invalid/p'}


def copy_rule_files(tmp_path):
    for rel in (RULE_MODULE, RULE_PROFILE):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    return tmp_path


def version_at(root):
    return rule_version(rule_id='section53', root=root, module=RULE_MODULE, profile=RULE_PROFILE)


def test_rule_version_is_typed_and_cites_the_act_and_the_commencement_order():
    rule = current_rule_version()
    assert rule['schema'] == SCHEMA and rule['rule_id'] == 'section53'
    assert rule['rule_module'] == RULE_MODULE and rule['profile'] == RULE_PROFILE
    assert rule['rule_module_sha256'] == hashlib.sha256((ROOT / RULE_MODULE).read_bytes()).hexdigest()
    assert rule['profile_sha256'] == hashlib.sha256((ROOT / RULE_PROFILE).read_bytes()).hexdigest()
    assert rule['profile_schema'] == 'sunlight.section53-profile.v1'
    # The profile cites section 53 of the Act and the commencement regulations.
    assert {c['sha256'] for c in rule['cited_sources']} == {
        '11b80c792bc3736eeaddbe966bf3372cd8a1b12689f000eb5b1345c49d2e92be',
        'da8e15821886289df707a959ae0c0c32cf5a98cff6c2a3d6ba14a4f3428be238'}


def test_any_change_to_module_or_profile_changes_the_version(tmp_path):
    base = version_at(copy_rule_files(tmp_path))
    assert base == current_rule_version()
    (tmp_path / RULE_MODULE).write_bytes((ROOT / RULE_MODULE).read_bytes() + b'\n')
    changed_module = version_at(tmp_path)
    assert changed_module['rule_version_sha256'] != base['rule_version_sha256']
    copy_rule_files(tmp_path)
    profile = json.loads((ROOT / RULE_PROFILE).read_text())
    profile['variants']['ordinary']['days'] = '31'
    (tmp_path / RULE_PROFILE).write_text(json.dumps(profile))
    assert version_at(tmp_path)['rule_version_sha256'] not in {base['rule_version_sha256'], changed_module['rule_version_sha256']}


def test_page_reference_requires_every_part_and_a_relative_path():
    assert page_reference(**PAGE) == {'capture': 'file', **PAGE}
    for bad in ({**PAGE, 'capture_file': '/abs/capture.json'}, {**PAGE, 'capture_file': '../capture.json'},
                {**PAGE, 'capture_file': ''}, {**PAGE, 'capture_file': None}, {**PAGE, 'page': -1},
                {**PAGE, 'page': True}, {**PAGE, 'page': '0'}, {**PAGE, 'source_sha256': 'ab' * 31},
                {**PAGE, 'source_sha256': None}, {**PAGE, 'projection_sha256': 'CD' * 32},
                {**PAGE, 'projection_sha256': None}):
        with pytest.raises(InvariantError):
            page_reference(**bad)


def test_source_kinds_are_told_apart_by_their_own_parts_only():
    assert any_source_reference(PAGE)['capture'] == 'file'
    assert any_source_reference({'capture_seq': 3, 'capture_hash': 'ef' * 32})['journal'] == 'watch'
    for bad in ({}, None, {'source_sha256': 'ab' * 32}, {'capture_seq': 3, **PAGE}, {'capture_file': 'x'}):
        with pytest.raises(InvariantError):
            any_source_reference(bad)


def test_stamp_with_a_page_reference_binds_row_source_and_rule():
    rule = current_rule_version()
    stamped = stamp(ROW, source=PAGE, rule=rule)
    assert stamped['custody'] == {'source': {'capture': 'file', **PAGE}, 'rule_id': 'section53',
                                  'rule_version_sha256': rule['rule_version_sha256']}
    body = {k: v for k, v in stamped.items() if k != 'result_sha256'}
    assert stamped['result_sha256'] == digest(body)
    assert check_row(stamped, rule=rule) == []
    with pytest.raises(InvariantError):
        stamp(ROW, source={**PAGE, 'page': None}, rule=rule)


def test_check_row_finds_tampering_of_a_page_stamped_row():
    rule = current_rule_version()
    stamped = stamp(ROW, source=PAGE, rule=rule)
    assert 'result_sha256 does not recompute' in check_row({**stamped, 'ocid': 'ocds-y'}, rule=rule)
    foreign = {**stamped, 'custody': {**stamped['custody'], 'source': {**stamped['custody']['source'], 'extra': 1}}}
    assert any('not its own' in p for p in check_row(foreign, rule=rule))
    broken = {**stamped, 'custody': {**stamped['custody'], 'source': {**stamped['custody']['source'], 'page': -1}}}
    assert 'source reference missing or malformed' in check_row(broken, rule=rule)
    swapped = {**stamped, 'custody': {**stamped['custody'], 'source': {'journal': 'watch', 'capture_seq': 1, 'capture_hash': 'ef' * 32}}}
    assert 'result_sha256 does not recompute' in check_row(swapped, rule=rule)


def constructed_capture_and_results():
    projection = {'adapter_version': 'central-platform-contract-details.v1', 'records': [], 'refusals': [], 'received_count': 0, 'next': None}
    page = {'url': ROW['source_url'], 'source_sha256': PAGE['source_sha256'], 'projection': projection,
            'projection_sha256': hashlib.sha256(canonical(projection)).hexdigest()}
    source = {**PAGE, 'projection_sha256': page['projection_sha256']}
    rule = current_rule_version()
    results = {'rule_version': rule, 'results': [stamp(ROW, source=source, rule=rule)]}
    return {'pages': [page]}, results, rule


def test_check_capture_file_ties_rows_to_the_capture_file():
    capture, results, rule = constructed_capture_and_results()
    ok = dict(capture_file=PAGE['capture_file'], projection_bytes=canonical)
    assert check_results(results, rule=rule) == []
    assert check_capture_file(results, capture, **ok) == []
    assert check_capture_file(results, capture, **{**ok, 'capture_file': 'research/y/capture.json'}) == ['row 0: cites another capture file']
    assert check_capture_file(results, {'pages': []}, **ok) == ['row 0: cited page is not in the capture file']
    assert check_capture_file(results, {}, **ok) == ['capture file carries no pages']
    altered = {'pages': [{**capture['pages'][0], 'projection': {**capture['pages'][0]['projection'], 'received_count': 1}}]}
    assert check_capture_file(results, altered, **ok) == ['row 0: cited projection_sha256 does not recompute from the capture file']
    other_bytes = {'pages': [{**capture['pages'][0], 'source_sha256': 'ee' * 32}]}
    assert check_capture_file(results, other_bytes, **ok) == ['row 0: capture page source_sha256 differs from the cited one']
    moved_url = {'pages': [{**capture['pages'][0], 'url': 'https://example.invalid/q'}]}
    assert check_capture_file(results, moved_url, **ok) == ['row 0: row source_url differs from the cited page']
    row = results['results'][0]
    off_page = {'results': [{**row, 'page': 1}]}
    assert check_capture_file(off_page, capture, **ok) == ['row 0: row page differs from the cited page']
    journal_row = {'results': [{**row, 'custody': {**row['custody'], 'source': {'journal': 'watch', 'capture_seq': 1, 'capture_hash': 'ef' * 32}}}]}
    assert check_capture_file(journal_row, capture, **ok) == ['row 0: source is not a capture-file page']


def test_committed_results_carry_custody_that_recomputes_from_this_repository():
    results = json.loads((RESEARCH / 'results.json').read_text())
    capture = json.loads((RESEARCH / 'capture.json').read_text())
    rule = current_rule_version()
    assert results['schema'] == 'sunlight.section53-results.v3'
    assert results['rule_version'] == rule
    assert len(results['results']) == 150
    assert check_results(results, rule=rule) == []
    assert check_capture_file(results, capture, capture_file=CAPTURE_FILE, projection_bytes=canonical) == []
    assert {r['custody']['source']['page'] for r in results['results']} == set(range(len(capture['pages'])))


def test_custody_moved_no_measured_outcome():
    results = json.loads((RESEARCH / 'results.json').read_text())
    rows = [{k: v for k, v in r.items() if k not in ('custody', 'result_sha256', 'watcher')} for r in results['results']]
    assert digest(rows) == V1_ROWS_SHA256
    assert results['counts']['states'] == {'UNASSESSABLE': 150} and results['counts']['assessable'] == 0


def test_replay_cites_the_capture_file_it_was_given_and_another_rule_version_is_detected(tmp_path):
    captured = json.loads((RESEARCH / 'capture.json').read_text())
    assert replay(captured) == json.loads((RESEARCH / 'results.json').read_text())
    elsewhere = replay(captured, capture_file='scratch/capture.json')
    assert elsewhere['results'][0]['custody']['source']['capture_file'] == 'scratch/capture.json'
    assert check_capture_file(elsewhere, captured, capture_file=CAPTURE_FILE, projection_bytes=canonical)[0] == 'row 0: cites another capture file'
    copy_rule_files(tmp_path)
    (tmp_path / RULE_MODULE).write_bytes((ROOT / RULE_MODULE).read_bytes() + b'\n')
    other = replay(captured, rule=version_at(tmp_path))
    problems = check_results(other, rule=current_rule_version())
    assert problems[0] == 'file-level rule_version differs from the rule in this repository'
    assert all('rule_version_sha256 differs' in p for p in problems[1:]) and len(problems) == 151


def test_verify_script_reads_only_and_exits_zero_on_the_committed_results(tmp_path, capsys, monkeypatch):
    import verify_section53_custody as v
    before = {p: p.stat().st_mtime_ns for p in RESEARCH.iterdir()}
    monkeypatch.setattr(sys, 'argv', ['verify_section53_custody.py', str(RESEARCH / 'results.json'), str(RESEARCH / 'capture.json')])
    assert v.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out['problems'] == [] and out['rows'] == 150 and out['distinct_cited_pages'] == 5
    assert {p: p.stat().st_mtime_ns for p in RESEARCH.iterdir()} == before
    tampered = json.loads((RESEARCH / 'results.json').read_text())
    tampered['results'][7]['assessment']['finding']['reason'] += '.'
    (tmp_path / 'results.json').write_text(json.dumps(tampered))
    monkeypatch.setattr(sys, 'argv', ['verify_section53_custody.py', str(tmp_path / 'results.json'), str(RESEARCH / 'capture.json')])
    assert v.main() == 1
    assert json.loads(capsys.readouterr().out)['problems'] == ['row 7: result_sha256 does not recompute']


def test_no_em_dash_and_no_personal_shaped_content():
    import re
    for rel in ('code/custody.py', 'scripts/measure_section53.py', 'scripts/verify_section53_custody.py',
                'tests/test_section53_custody.py', 'research/section53_2026-11-13/adapter-run/results.json'):
        text = (ROOT / rel).read_text()
        assert chr(0x2014) not in text, rel
        assert not re.search(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}', text), rel
