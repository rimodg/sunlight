"""The roster: which watchers exist, each with its seal, as one hashed list.
Constructed cases first (every missing, malformed or extra part refused; the
hash moves with every part; a watcher off the roster or differing from its
entry does not run), then the committed roster and both committed results
files checked against the watchers sealed from this repository."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest
from custody import digest
from invariant_core import InvariantError
from roster import (ENTRY_KEYS, ROSTER_FILE, SCHEMA, build_roster, check_reference, check_roster, enrol,
                    entry_for, load_roster, reference, roster_digest)
from watcher import seal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import measure_events_in_order as eio  # noqa: E402
import measure_section53 as s53  # noqa: E402
from events_in_order import load_profile  # noqa: E402

EIO_WATCHER = 'config/watchers/events-in-order.json'
S53_WATCHER = 'config/watchers/section53.json'
EIO_RESEARCH = ROOT / 'research' / 'events_in_order_2026-11-18'
S53_RESEARCH = ROOT / 'research' / 'section53_2026-11-13' / 'adapter-run'
RULE_FILES = ('code/events_in_order.py', 'config/events-in-order-profile.json',
              'code/section53.py', 'config/section53-profile.json')


def copy_tree(tmp_path, *rels):
    for rel in rels:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    return tmp_path


def full_copy(tmp_path):
    return copy_tree(tmp_path, ROSTER_FILE, EIO_WATCHER, S53_WATCHER, *RULE_FILES)


def rewrite(root, rel, change):
    data = json.loads((root / rel).read_text())
    change(data)
    (root / rel).write_text(json.dumps(data, indent=2) + '\n')


def reseal(data):
    data['roster_sha256'] = roster_digest(data)


def refused(tmp_path, change, message, resealed=True):
    full_copy(tmp_path)
    rewrite(tmp_path, ROSTER_FILE, lambda d: (change(d), reseal(d) if resealed else None))
    with pytest.raises(InvariantError, match=message):
        load_roster(tmp_path, ROSTER_FILE)


def test_roster_file_is_typed_and_names_both_watchers_with_their_seals():
    roster = load_roster(ROOT, ROSTER_FILE)
    assert roster['schema'] == SCHEMA and set(roster) == {'schema', 'purpose', 'watchers', 'roster_sha256'}
    assert [e['watcher_id'] for e in roster['watchers']] == ['events_in_order', 'section53']
    assert [e['file'] for e in roster['watchers']] == [EIO_WATCHER, S53_WATCHER]
    for entry, (watcher_file, rule) in zip(roster['watchers'], ((EIO_WATCHER, eio), (S53_WATCHER, s53))):
        sealed = seal(ROOT, watcher_file)
        assert entry['watcher_seal_sha256'] == sealed['watcher_seal_sha256']
        assert entry['watcher_sha256'] == hashlib.sha256((ROOT / watcher_file).read_bytes()).hexdigest()
        assert entry['rule_version_sha256'] == rule.current_rule_version()['rule_version_sha256']
        assert entry['rule_id'] == rule.current_rule_version()['rule_id']
    assert roster['roster_sha256'] == digest({k: v for k, v in roster.items() if k != 'roster_sha256'})


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('purpose'), 'Typed roster'),
    (lambda d: d.update(extra=1), 'Typed roster'),
    (lambda d: d.update(schema='sunlight.roster.v0'), 'Typed roster'),
    (lambda d: d.update(purpose=' '), 'purpose required'),
    (lambda d: d['watchers'].clear(), 'At least one watcher'),
    (lambda d: d['watchers'][0].pop('watcher_seal_sha256'), 'Roster entry with'),
    (lambda d: d['watchers'][0].update(enabled=True), 'Roster entry with'),
    (lambda d: d['watchers'][0].update(watcher_id='Events'), 'watcher_id required as a slug'),
    (lambda d: d['watchers'][0].update(file='code/watcher.py'), 'under config/watchers'),
    (lambda d: d['watchers'][0].update(file='config/watchers/../roster.json'), 'under config/watchers'),
    (lambda d: d['watchers'][0].update(watcher_seal_sha256='abc'), 'watcher_seal_sha256 required'),
    (lambda d: d['watchers'].reverse(), 'ordered by watcher_id'),
    (lambda d: d['watchers'].append(dict(d['watchers'][0])), 'distinct and ordered'),
    (lambda d: d['watchers'][1].update(watcher_id='zz', file=d['watchers'][0]['file']), 'distinct files'),
])
def test_missing_malformed_or_extra_parts_are_refused(tmp_path, change, message):
    refused(tmp_path, change, message)


def test_a_roster_whose_hash_does_not_recompute_is_refused(tmp_path):
    refused(tmp_path, lambda d: d['watchers'][0].update(watcher_seal_sha256='ab' * 32), 'does not recompute', resealed=False)
    refused(tmp_path, lambda d: d.update(roster_sha256='ab' * 32), 'does not recompute', resealed=False)
    with pytest.raises(InvariantError, match='Roster file required'):
        load_roster(tmp_path, 'config/no-roster.json')


def test_roster_hash_is_stable_across_locations_and_moves_with_every_part(tmp_path):
    base = load_roster(full_copy(tmp_path), ROSTER_FILE)
    assert base == load_roster(ROOT, ROSTER_FILE)
    assert build_roster(tmp_path, base['purpose']) == base
    for change in (lambda d: d.update(purpose=d['purpose'] + '.'),
                   lambda d: d['watchers'].pop(),
                   lambda d: d['watchers'][0].update(watcher_seal_sha256='ab' * 32),
                   lambda d: d['watchers'][0].update(rule_version_sha256='ab' * 32),
                   lambda d: d['watchers'][0].update(watcher_sha256='ab' * 32)):
        moved = copy.deepcopy(base)
        change(moved)
        assert roster_digest(moved) != base['roster_sha256']


def test_check_roster_finds_every_entry_that_no_longer_recomputes(tmp_path):
    full_copy(tmp_path)
    roster = load_roster(tmp_path, ROSTER_FILE)
    assert check_roster(tmp_path, roster) == []
    # A byte of a watcher file: the file hash and the seal move, the rule version does not.
    (tmp_path / EIO_WATCHER).write_bytes((ROOT / EIO_WATCHER).read_bytes() + b'\n')
    problems = check_roster(tmp_path, roster)
    assert problems == [f'{EIO_WATCHER}: watcher_sha256 differs from the watcher sealed from this checkout',
                        f'{EIO_WATCHER}: watcher_seal_sha256 differs from the watcher sealed from this checkout']
    # A byte of a rule module: the rule version and the seal move.
    full_copy(tmp_path)
    (tmp_path / 'code/section53.py').write_bytes((ROOT / 'code/section53.py').read_bytes() + b'\n')
    problems = check_roster(tmp_path, roster)
    assert problems == [f'{S53_WATCHER}: rule_version_sha256 differs from the watcher sealed from this checkout',
                        f'{S53_WATCHER}: watcher_seal_sha256 differs from the watcher sealed from this checkout']
    # A watcher file that is on the roster but cannot be sealed.
    full_copy(tmp_path)
    (tmp_path / S53_WATCHER).unlink()
    assert any('cannot be sealed' in p for p in check_roster(tmp_path, roster))
    # A watcher file under config/watchers that the roster does not name.
    full_copy(tmp_path)
    (tmp_path / 'config/watchers/other.json').write_bytes((ROOT / S53_WATCHER).read_bytes())
    assert check_roster(tmp_path, roster) == ['config/watchers/other.json: watcher file is not on the roster']
    # A roster entry whose id differs from the watcher file.
    (tmp_path / 'config/watchers/other.json').unlink()
    full_copy(tmp_path)
    rewrite(tmp_path, ROSTER_FILE, lambda d: (d['watchers'][0].update(watcher_id='events_in_disorder'), reseal(d)))
    assert check_roster(tmp_path, load_roster(tmp_path, ROSTER_FILE)) == [
        f'{EIO_WATCHER}: watcher_id differs from the watcher sealed from this checkout']


def test_a_watcher_off_the_roster_or_differing_from_its_entry_does_not_run(tmp_path):
    roster = load_roster(ROOT, ROSTER_FILE)
    sealed = seal(ROOT, EIO_WATCHER)
    assert enrol(roster, sealed, EIO_WATCHER) == roster['watchers'][0]
    with pytest.raises(InvariantError, match='not on the roster'):
        enrol(roster, sealed, 'config/watchers/other.json')
    for key in ('watcher_seal_sha256', 'watcher_sha256', 'watcher_id'):
        with pytest.raises(InvariantError, match='differs from its roster entry'):
            enrol(roster, {**sealed, key: 'x'}, EIO_WATCHER)
    with pytest.raises(InvariantError, match='differs from its roster entry'):
        enrol(roster, {**sealed, 'rule_version': {**sealed['rule_version'], 'rule_version_sha256': 'ab' * 32}}, EIO_WATCHER)
    # Through the measure scripts: a changed watcher under an unchanged roster is refused before any row is read.
    full_copy(tmp_path)
    rewrite(tmp_path, EIO_WATCHER, lambda d: d['selection'].pop())
    changed = (eio.load_watcher(tmp_path, EIO_WATCHER), eio.seal(tmp_path, EIO_WATCHER))
    pairs = json.loads((EIO_RESEARCH / 'pairs.json').read_text())
    with pytest.raises(InvariantError, match='does not run'):
        eio.replay(pairs, load_profile(ROOT / eio.RULE_PROFILE), watcher=changed, roster=roster)
    off_roster = copy.deepcopy(roster)
    off_roster['watchers'] = [roster['watchers'][1]]
    reseal(off_roster)
    with pytest.raises(InvariantError, match='not on the roster'):
        eio.replay(pairs, load_profile(ROOT / eio.RULE_PROFILE), roster=off_roster)
    captured = json.loads((S53_RESEARCH / 'capture.json').read_text())
    s53.replay(captured, roster=off_roster)  # section53 is the one watcher this roster names.
    only_eio = copy.deepcopy(roster)
    only_eio['watchers'] = [roster['watchers'][0]]
    reseal(only_eio)
    with pytest.raises(InvariantError, match='not on the roster'):
        s53.replay(captured, roster=only_eio)
    # The same changed watcher runs once a roster made from that checkout names it: the roster is the gate.
    resealed = build_roster(tmp_path, roster['purpose'])
    assert resealed['watchers'][0]['watcher_seal_sha256'] == changed[1]['watcher_seal_sha256']
    out = eio.replay(pairs, load_profile(ROOT / eio.RULE_PROFILE), watcher=changed, roster=resealed, root=tmp_path)
    assert out['roster']['roster_sha256'] == resealed['roster_sha256'] and out['not_selected'] == 25


def test_committed_results_name_the_committed_roster_and_a_watcher_on_it():
    roster = load_roster(ROOT, ROSTER_FILE)
    assert check_roster(ROOT, roster) == []
    for research in (EIO_RESEARCH, S53_RESEARCH):
        results = json.loads((research / 'results.json').read_text())
        assert results['roster'] == reference(ROOT, roster, ROSTER_FILE)
        assert results['roster']['watchers'] == 2 and results['roster']['roster_sha256'] == roster['roster_sha256']
        assert results['roster']['roster_file_sha256'] == hashlib.sha256((ROOT / ROSTER_FILE).read_bytes()).hexdigest()
        assert check_reference(results, ROOT, roster, ROSTER_FILE) == []
        tampered = copy.deepcopy(results)
        tampered['roster']['roster_sha256'] = 'ab' * 32
        assert check_reference(tampered, ROOT, roster, ROSTER_FILE) == [
            'file-level roster reference differs from the roster in this repository']
        tampered = copy.deepcopy(results)
        tampered['watcher_seal']['watcher_seal_sha256'] = 'ab' * 32
        assert check_reference(tampered, ROOT, roster, ROSTER_FILE) == ['Watcher differs from its roster entry; it does not run']
        tampered = copy.deepcopy(results)
        del tampered['watcher_seal']
        assert check_reference(tampered, ROOT, roster, ROSTER_FILE) == ['file-level watcher_seal missing']


def test_adding_the_roster_moved_no_row_of_either_results_file():
    # Every row, custody stamp and result_sha256 included, is what the sealed-watcher files carried.
    # The digests below are of the row lists of the two schema v3 files at commit d695aa3.
    rows = json.loads((EIO_RESEARCH / 'results.json').read_text())['results']
    assert len(rows) == 193
    assert digest(rows) == '7ccef4bd3b6aa3b28e046c8089d72394fa6716589f4027708859308635d4c1bc'
    rows = json.loads((S53_RESEARCH / 'results.json').read_text())['results']
    assert len(rows) == 150
    assert digest(rows) == '006e5f2a2f88b94d7026384573fc92ee94407aa3aaa685c42dc5593353ac0d5f'


def test_scripts_read_only_and_exit_zero_on_the_committed_files(tmp_path, capsys, monkeypatch):
    import seal_roster
    import verify_roster
    watched = [ROOT / ROSTER_FILE, ROOT / EIO_WATCHER, ROOT / S53_WATCHER, EIO_RESEARCH / 'results.json', S53_RESEARCH / 'results.json']
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched}
    monkeypatch.setattr(sys, 'argv', ['verify_roster.py', str(EIO_RESEARCH / 'results.json'), str(S53_RESEARCH / 'results.json')])
    assert verify_roster.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out['problems'] == [] and [w['watcher_id'] for w in out['watchers']] == ['events_in_order', 'section53']
    assert all(f['problems'] == [] for f in out['results_files'].values())
    monkeypatch.setattr(sys, 'argv', ['seal_roster.py'])
    assert seal_roster.main() == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == load_roster(ROOT, ROSTER_FILE)
    assert {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched} == before
    assert sorted(ROOT.glob('config/watchers/*')) == [ROOT / EIO_WATCHER, ROOT / S53_WATCHER]
    # A results file naming another roster fails the verifier.
    tampered = json.loads((EIO_RESEARCH / 'results.json').read_text())
    tampered['roster']['watchers'] = 3
    (tmp_path / 'results.json').write_text(json.dumps(tampered))
    monkeypatch.setattr(sys, 'argv', ['verify_roster.py', str(tmp_path / 'results.json')])
    assert verify_roster.main() == 1
    assert json.loads(capsys.readouterr().out)['problems'] == [
        f'{tmp_path / "results.json"}: file-level roster reference differs from the roster in this repository']


def test_no_em_dash_no_personal_shaped_content_no_allegation_words():
    for rel in ('code/roster.py', 'scripts/verify_roster.py', 'scripts/seal_roster.py', 'tests/test_roster.py', ROSTER_FILE):
        text = (ROOT / rel).read_text()
        assert chr(0x2014) not in text, rel
        assert not re.search(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}', text), rel
    assert not re.search(r'fraud|corrupt|guilty|illegal|wrongdoing', (ROOT / ROSTER_FILE).read_text(), re.I)
