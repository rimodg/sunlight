"""The decision inbox: where a result that needs a person's judgement waits.
Constructed cases first (every missing, malformed or extra part of the policy
and of an inbox refused; the hash moves with every part; a row the rule did
not run on never waits; a row whose stamp does not recompute is refused),
then the committed policy and both committed inboxes checked against the
results files and the roster in this repository."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest
from custody import digest
from inbox import (ITEM_KEYS, POLICY_FILE, POLICY_SCHEMA, SCHEMA, TOP_KEYS, build_inbox, check_inbox, inbox_digest,
                   item_digest, load_inbox, load_policy, policy_digest, policy_for, policy_reference, seal_policy)
from invariant_core import InvariantError
from roster import ROSTER_FILE, check_reference, load_roster

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_inbox as build_script  # noqa: E402
import seal_inbox_policy  # noqa: E402
import verify_inbox  # noqa: E402

EIO_RESULTS = 'research/events_in_order_2026-11-18/results.json'
S53_RESULTS = 'research/section53_2026-11-13/adapter-run/results.json'
EIO_INBOX = 'research/events_in_order_2026-11-18/inbox.json'
S53_INBOX = 'research/section53_2026-11-13/adapter-run/inbox.json'
ROSTER_FILES = (ROSTER_FILE, 'config/watchers/events-in-order.json', 'config/watchers/section53.json',
                'code/events_in_order.py', 'config/events-in-order-profile.json',
                'code/section53.py', 'config/section53-profile.json')


def copy_tree(tmp_path, *rels):
    for rel in rels:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    return tmp_path


def full_copy(tmp_path):
    return copy_tree(tmp_path, POLICY_FILE, EIO_RESULTS, S53_RESULTS, EIO_INBOX, S53_INBOX, *ROSTER_FILES)


def rewrite(root, rel, change):
    data = json.loads((root / rel).read_text())
    change(data)
    (root / rel).write_text(json.dumps(data, indent=2) + '\n')


def reseal(data):
    data['policy_sha256'] = policy_digest(data)


def built(root, results_rel=EIO_RESULTS):
    raw = (root / results_rel).read_bytes()
    return build_inbox(json.loads(raw), results_file=results_rel, results_bytes=raw,
                       policy=load_policy(root, POLICY_FILE), root=root, policy_file=POLICY_FILE)


def refused_policy(tmp_path, change, message, resealed=True):
    full_copy(tmp_path)
    rewrite(tmp_path, POLICY_FILE, lambda d: (change(d), reseal(d) if resealed else None))
    with pytest.raises(InvariantError, match=message):
        load_policy(tmp_path, POLICY_FILE)


def test_policy_is_typed_and_names_both_rules_with_one_waiting_state_each():
    policy = load_policy(ROOT, POLICY_FILE)
    assert policy['schema'] == POLICY_SCHEMA and set(policy) == {'schema', 'purpose', 'rules', 'policy_sha256'}
    assert [r['rule_id'] for r in policy['rules']] == ['events_in_order', 'section53']
    assert [[w['state'] for w in r['waits']] for r in policy['rules']] == [['INCONSISTENT'], ['BREAKS']]
    assert policy_for(policy, 'section53')['state_path'] == ['assessment', 'finding', 'state']
    assert policy['policy_sha256'] == digest({k: v for k, v in policy.items() if k != 'policy_sha256'})
    with pytest.raises(InvariantError, match='not on the inbox policy'):
        policy_for(policy, 'other_rule')


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('purpose'), 'Typed inbox policy'),
    (lambda d: d.update(extra=1), 'Typed inbox policy'),
    (lambda d: d.update(schema='sunlight.inbox-policy.v0'), 'Typed inbox policy'),
    (lambda d: d.update(purpose=' '), 'purpose required'),
    (lambda d: d['rules'].clear(), 'At least one policy rule'),
    (lambda d: d['rules'][0].pop('waits'), 'Policy rule with'),
    (lambda d: d['rules'][0].update(threshold=3), 'Policy rule with'),
    (lambda d: d['rules'][0].update(rule_id='Events'), 'rule_id required as a slug'),
    (lambda d: d['rules'][0].update(record=[]), 'record fields required'),
    (lambda d: d['rules'][0].update(state_path='state'), 'state_path required'),
    (lambda d: d['rules'][0].update(reason_path=['a', 'a']), 'reason_path required'),
    (lambda d: d['rules'][0].update(waits={'state': 'INCONSISTENT'}), 'waits required as a list'),
    (lambda d: d['rules'][0]['waits'][0].pop('question'), 'wait with state and question'),
    (lambda d: d['rules'][0]['waits'][0].update(severity=2), 'wait with state and question'),
    (lambda d: d['rules'][0]['waits'][0].update(state='inconsistent'), 'upper-case state name'),
    (lambda d: d['rules'][0]['waits'][0].update(question=''), 'question required'),
    (lambda d: d['rules'][0]['waits'].append(dict(d['rules'][0]['waits'][0])), 'states must be distinct'),
    (lambda d: d['rules'].reverse(), 'ordered by rule_id'),
    (lambda d: d['rules'].append(dict(d['rules'][1])), 'distinct and ordered'),
])
def test_missing_malformed_or_extra_policy_parts_are_refused(tmp_path, change, message):
    refused_policy(tmp_path, change, message)


def test_a_policy_whose_hash_does_not_recompute_is_refused_and_seal_policy_repairs_nothing_else(tmp_path):
    refused_policy(tmp_path, lambda d: d['rules'][0]['waits'][0].update(question='Other question?'), 'does not recompute', resealed=False)
    refused_policy(tmp_path, lambda d: d.update(policy_sha256='ab' * 32), 'does not recompute', resealed=False)
    with pytest.raises(InvariantError, match='policy file required'):
        load_policy(tmp_path, 'config/no-policy.json')
    policy = load_policy(ROOT, POLICY_FILE)
    assert seal_policy({**policy, 'policy_sha256': 'ab' * 32}) == policy
    with pytest.raises(InvariantError, match='Policy rule with'):
        seal_policy({**policy, 'rules': [{'rule_id': 'x'}]})


def test_the_policy_hash_is_stable_across_locations_and_moves_with_every_part(tmp_path):
    base = load_policy(full_copy(tmp_path), POLICY_FILE)
    assert base == load_policy(ROOT, POLICY_FILE)
    for change in (lambda d: d.update(purpose=d['purpose'] + '.'),
                   lambda d: d['rules'].pop(),
                   lambda d: d['rules'][0]['waits'].clear(),
                   lambda d: d['rules'][0]['waits'][0].update(question='Other question?'),
                   lambda d: d['rules'][0]['waits'][0].update(state='UNASSESSABLE'),
                   lambda d: d['rules'][1].update(state_path=['state'])):
        moved = copy.deepcopy(base)
        change(moved)
        assert policy_digest(moved) != base['policy_sha256']


def test_built_inbox_lists_exactly_the_rows_whose_state_waits_in_results_order():
    results = json.loads((ROOT / EIO_RESULTS).read_text())
    inbox = built(ROOT)
    waiting = [(i, r) for i, r in enumerate(results['results']) if r['state'] == 'INCONSISTENT']
    assert inbox['waiting'] == len(inbox['items']) == len(waiting)
    assert [i['position'] for i in inbox['items']] == [i for i, _ in waiting] == [19, 20, 23, 135, 173]
    for item, (position, row) in zip(inbox['items'], waiting):
        assert item['row'] == row and item['result_sha256'] == row['result_sha256']
        assert item['record'] == {'ocid': row['ocid'], 'award_id': row['award_id']}
        assert item['read'] == row['watcher'] and item['said'] == {'state': 'INCONSISTENT', 'reason': row['reason']}
        assert item['question'] == policy_for(load_policy(ROOT), 'events_in_order')['waits'][0]['question']
        assert set(item) == ITEM_KEYS and item['item_sha256'] == item_digest(item)
    assert inbox['rows'] == len(results['results']) == 193
    assert inbox['rule_did_not_run'] == results['not_selected'] == 0
    assert inbox['not_waiting'] == {k: v for k, v in sorted(results['states'].items()) if k != 'INCONSISTENT'}
    assert inbox['waiting'] + inbox['rule_did_not_run'] + sum(inbox['not_waiting'].values()) == inbox['rows']
    assert inbox['roster'] == results['roster'] and inbox['rule_id'] == 'events_in_order'
    assert inbox['rule_version_sha256'] == results['rule_version']['rule_version_sha256']
    assert inbox['watcher_seal_sha256'] == results['watcher_seal']['watcher_seal_sha256']
    assert inbox['results_file_sha256'] == hashlib.sha256((ROOT / EIO_RESULTS).read_bytes()).hexdigest()
    assert inbox['policy'] == policy_reference(ROOT, load_policy(ROOT), POLICY_FILE)
    assert set(inbox) == TOP_KEYS and inbox['inbox_sha256'] == inbox_digest(inbox)


def test_section53_inbox_is_empty_because_no_row_reached_a_waiting_state_and_says_so():
    results = json.loads((ROOT / S53_RESULTS).read_text())
    inbox = built(ROOT, S53_RESULTS)
    assert inbox['items'] == [] and inbox['waiting'] == 0
    assert inbox['rows'] == 150 and inbox['not_waiting'] == {'UNASSESSABLE': 150} and inbox['rule_did_not_run'] == 0
    assert results['counts']['states'] == {'UNASSESSABLE': 150}
    # Were a row to BREAK, it would wait: the policy reads the state at assessment.finding.state.
    changed = copy.deepcopy(results)
    row = changed['results'][3]
    row['assessment']['finding']['state'] = 'BREAKS'
    row['assessment']['finding']['reason'] = 'constructed'
    row['result_sha256'] = digest({k: v for k, v in row.items() if k != 'result_sha256'})
    raw = json.dumps(changed).encode()
    inbox = build_inbox(changed, results_file=S53_RESULTS, results_bytes=raw, policy=load_policy(ROOT), root=ROOT)
    assert [i['position'] for i in inbox['items']] == [3] and inbox['not_waiting'] == {'UNASSESSABLE': 149}
    assert inbox['items'][0]['record'] == {k: row[k] for k in ('ocid', 'release_id', 'contract_id')}
    assert inbox['items'][0]['said'] == {'state': 'BREAKS', 'reason': 'constructed'}


def test_the_inbox_hash_is_stable_across_locations_and_moves_with_every_part(tmp_path):
    base = built(full_copy(tmp_path))
    assert base == built(ROOT) == load_inbox(ROOT / EIO_INBOX)
    for change in (lambda d: d['items'].pop(),
                   lambda d: d['items'][0].update(question='Other question?'),
                   lambda d: d['items'][0]['said'].update(state='CONSISTENT'),
                   lambda d: d['not_waiting'].update(CONSISTENT=118),
                   lambda d: d['policy'].update(policy_sha256='ab' * 32),
                   lambda d: d['roster'].update(roster_sha256='ab' * 32),
                   lambda d: d.update(results_file_sha256='ab' * 32)):
        moved = copy.deepcopy(base)
        change(moved)
        assert inbox_digest(moved) != base['inbox_sha256']


def test_rows_the_rule_did_not_run_on_never_wait_and_unstamped_or_foreign_rows_are_refused():
    results = json.loads((ROOT / EIO_RESULTS).read_text())
    policy = load_policy(ROOT)
    # A row the watcher did not select carries no answer, whatever its state field says.
    changed = copy.deepcopy(results)
    row = changed['results'][19]
    assert row['state'] == 'INCONSISTENT'
    row['watcher']['selection'] = {'outcome': 'NOT_SELECTED', 'row': None, 'apply': [], 'reason': 'constructed'}
    row['result_sha256'] = digest({k: v for k, v in row.items() if k != 'result_sha256'})
    inbox = build_inbox(changed, results_file=EIO_RESULTS, results_bytes=b'x', policy=policy, root=ROOT)
    assert inbox['rule_did_not_run'] == 1 and inbox['waiting'] == 4 and 19 not in {i['position'] for i in inbox['items']}
    # A row whose stamp does not recompute is refused, not listed.
    changed = copy.deepcopy(results)
    changed['results'][0]['state'] = 'INCONSISTENT'
    with pytest.raises(InvariantError, match='row 0: stamped result row'):
        build_inbox(changed, results_file=EIO_RESULTS, results_bytes=b'x', policy=policy, root=ROOT)
    # A row computed by another rule, a state missing at the policy path, a missing record field.
    for change, message in ((lambda r: r['custody'].update(rule_id='section53'), 'another rule'),
                            (lambda r: r.pop('state'), 'rule state required'),
                            (lambda r: r.update(reason=''), 'rule reason required'),
                            (lambda r: r.pop('award_id'), 'record field award_id required')):
        changed = copy.deepcopy(results)
        row = changed['results'][19]
        change(row)
        row['result_sha256'] = digest({k: v for k, v in row.items() if k != 'result_sha256'})
        with pytest.raises(InvariantError, match=message):
            build_inbox(changed, results_file=EIO_RESULTS, results_bytes=b'x', policy=policy, root=ROOT)
    # A results file without a roster reference (schema v3 and earlier) or for a rule off the policy.
    for change, message in ((lambda d: d.pop('roster'), 'without a roster reference'),
                            (lambda d: d.pop('watcher_seal'), 'without a watcher seal'),
                            (lambda d: d['rule_version'].update(rule_id='other_rule'), 'not on the inbox policy')):
        changed = copy.deepcopy(results)
        change(changed)
        with pytest.raises(InvariantError, match=message):
            build_inbox(changed, results_file=EIO_RESULTS, results_bytes=b'x', policy=policy, root=ROOT)
    with pytest.raises(InvariantError, match='relative path'):
        build_inbox(results, results_file='/tmp/results.json', results_bytes=b'x', policy=policy, root=ROOT)


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('purpose'), 'Typed inbox'),
    (lambda d: d.update(decided=0), 'Typed inbox'),
    (lambda d: d.update(results_file='../results.json'), 'relative path'),
    (lambda d: d.update(results_file_sha256='abc'), 'results_file_sha256 required'),
    (lambda d: d.update(rule_id='Rule'), 'rule_id required as a slug'),
    (lambda d: d['roster'].pop('watchers'), 'roster reference required'),
    (lambda d: d['policy'].update(policy_sha256='abc'), 'policy reference required'),
    (lambda d: d.update(rows=-1), 'rows required as a count'),
    (lambda d: d.update(not_waiting={'CONSISTENT': 0}), 'not_waiting required'),
    (lambda d: d.update(waiting=4), 'one per waiting result'),
    (lambda d: d['not_waiting'].update(CONSISTENT=118), 'do not add up'),
    (lambda d: d['items'][0].pop('question'), 'item with every part'),
    (lambda d: d['items'][0].update(decision='ignore'), 'item with every part'),
    (lambda d: d['items'][0].update(record={}), 'item record required'),
    (lambda d: d['items'][0].update(said={'state': 'INCONSISTENT'}), 'said with state and reason'),
    (lambda d: d['items'][0]['row'].update(result_sha256='ab' * 32), 'must carry the result_sha256'),
    (lambda d: d['items'].reverse(), 'in results order'),
])
def test_missing_malformed_or_extra_inbox_parts_are_refused(tmp_path, change, message):
    data = json.loads((ROOT / EIO_INBOX).read_text())
    change(data)
    for item in data['items']:
        if set(item) == ITEM_KEYS:
            item['item_sha256'] = item_digest(item)
    data['inbox_sha256'] = inbox_digest(data)
    (tmp_path / 'inbox.json').write_text(json.dumps(data))
    with pytest.raises(InvariantError, match=message):
        load_inbox(tmp_path / 'inbox.json')


def test_an_inbox_whose_hashes_do_not_recompute_is_refused(tmp_path):
    for change, message in ((lambda d: d['items'][0].update(question='Other question?'), 'item_sha256 does not recompute'),
                            (lambda d: d.update(purpose=d['purpose'] + '.'), 'inbox_sha256 does not recompute'),
                            (lambda d: d.update(inbox_sha256='ab' * 32), 'inbox_sha256 does not recompute')):
        data = json.loads((ROOT / EIO_INBOX).read_text())
        change(data)
        (tmp_path / 'inbox.json').write_text(json.dumps(data))
        with pytest.raises(InvariantError, match=message):
            load_inbox(tmp_path / 'inbox.json')
    with pytest.raises(InvariantError, match='Inbox file required'):
        load_inbox(tmp_path / 'no-inbox.json')


def test_check_inbox_finds_every_difference_from_the_checkout(tmp_path):
    full_copy(tmp_path)
    inbox = load_inbox(tmp_path / EIO_INBOX)
    assert check_inbox(inbox, tmp_path) == []
    # A byte of the results file: its hash moves, every row still waits as before.
    (tmp_path / EIO_RESULTS).write_bytes((ROOT / EIO_RESULTS).read_bytes() + b'\n')
    assert check_inbox(inbox, tmp_path) == ['results_file_sha256 differs from the inbox built from this checkout',
                                            'inbox_sha256 differs from the inbox built from this checkout']
    # A policy that no longer names the state: every item is one that does not wait.
    full_copy(tmp_path)
    rewrite(tmp_path, POLICY_FILE, lambda d: (d['rules'][0]['waits'].clear(), reseal(d)))
    problems = check_inbox(inbox, tmp_path)
    assert 'policy differs from the inbox built from this checkout' in problems
    assert [p for p in problems if 'does not wait under the policy' in p] == [
        f"item at row {i['position']} does not wait under the policy" for i in inbox['items']]
    # A policy that names one more state: rows wait that the inbox does not list.
    full_copy(tmp_path)
    rewrite(tmp_path, POLICY_FILE, lambda d: (d['rules'][0]['waits'].append({'state': 'UNASSESSABLE', 'question': 'Why?'}), reseal(d)))
    problems = check_inbox(inbox, tmp_path)
    assert sum('waits under the policy but is not in the inbox' in p for p in problems) == 60
    # An item altered after the hashes were recomputed around it.
    full_copy(tmp_path)
    altered = copy.deepcopy(inbox)
    altered['items'][0]['said']['reason'] = 'constructed'
    altered['items'][0]['item_sha256'] = item_digest(altered['items'][0])
    altered['inbox_sha256'] = inbox_digest(altered)
    assert check_inbox(altered, tmp_path) == [f"item at row {inbox['items'][0]['position']} differs from the one built from this checkout",
                                              'inbox_sha256 differs from the inbox built from this checkout']
    # A results file that is not in the checkout, and a policy that cannot be loaded.
    assert check_inbox({**inbox, 'results_file': 'research/none.json'}, tmp_path) == ['results file the inbox names is not in this checkout']
    (tmp_path / POLICY_FILE).write_text('{}')
    assert check_inbox(inbox, tmp_path) == ['inbox policy cannot be loaded from this checkout (Typed inbox policy with purpose, rules and policy_sha256 required)']


def test_committed_inboxes_are_what_this_checkout_builds_and_name_the_committed_roster():
    roster = load_roster(ROOT, ROSTER_FILE)
    for inbox_rel, results_rel, waiting in ((EIO_INBOX, EIO_RESULTS, 5), (S53_INBOX, S53_RESULTS, 0)):
        inbox = load_inbox(ROOT / inbox_rel)
        assert inbox == built(ROOT, results_rel) and inbox['waiting'] == waiting
        assert check_inbox(inbox, ROOT) == []
        results = json.loads((ROOT / results_rel).read_text())
        assert inbox['roster'] == results['roster'] and inbox['roster']['roster_sha256'] == roster['roster_sha256']
        assert check_reference(results, ROOT, roster, ROSTER_FILE) == []
        assert inbox['policy']['policy_file_sha256'] == hashlib.sha256((ROOT / POLICY_FILE).read_bytes()).hexdigest()
    # The waiting rows of the events-in-order file are its five INCONSISTENT rows, and the file is unchanged.
    results = json.loads((ROOT / EIO_RESULTS).read_text())
    assert results['states']['INCONSISTENT'] == 5
    assert digest(results['results']) == '7ccef4bd3b6aa3b28e046c8089d72394fa6716589f4027708859308635d4c1bc'
    assert digest(json.loads((ROOT / S53_RESULTS).read_text())['results']) == '006e5f2a2f88b94d7026384573fc92ee94407aa3aaa685c42dc5593353ac0d5f'


def test_scripts_write_only_their_output_and_exit_zero_on_the_committed_files(tmp_path, capsys, monkeypatch):
    watched = [ROOT / p for p in (POLICY_FILE, EIO_RESULTS, S53_RESULTS, EIO_INBOX, S53_INBOX, ROSTER_FILE)]
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched}
    monkeypatch.setattr(sys, 'argv', ['verify_inbox.py', str(ROOT / EIO_INBOX), str(ROOT / S53_INBOX)])
    assert verify_inbox.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out['problems'] == [] and all(f['problems'] == [] for f in out['inboxes'].values())
    assert [f['waiting'] for f in out['inboxes'].values()] == [5, 0]
    monkeypatch.setattr(sys, 'argv', ['seal_inbox_policy.py'])
    assert seal_inbox_policy.main() == 0
    assert json.loads(capsys.readouterr().out) == load_policy(ROOT)
    # The build script writes its output and nothing else, and refuses an existing output.
    out_path = tmp_path / 'inbox.json'
    monkeypatch.setattr(sys, 'argv', ['build_inbox.py', str(ROOT / EIO_RESULTS), str(out_path)])
    assert build_script.main() == 0
    assert json.loads(capsys.readouterr().out)['waiting'] == 5
    assert json.loads(out_path.read_text()) == load_inbox(ROOT / EIO_INBOX)
    assert out_path.read_bytes() == (ROOT / EIO_INBOX).read_bytes()
    with pytest.raises(SystemExit, match='Refusing to overwrite'):
        build_script.main()
    (tmp_path / 'outside.json').write_bytes((ROOT / EIO_RESULTS).read_bytes())
    monkeypatch.setattr(sys, 'argv', ['build_inbox.py', str(tmp_path / 'outside.json'), str(tmp_path / 'other.json')])
    with pytest.raises(SystemExit, match='inside the repository'):
        build_script.main()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['inbox.json', 'outside.json']
    assert {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched} == before
    # A tampered inbox fails the verifier with the difference named.
    tampered = json.loads((ROOT / EIO_INBOX).read_text())
    tampered['items'].pop()
    tampered['waiting'] = 4
    tampered['not_waiting']['CONSISTENT'] = 120
    tampered['inbox_sha256'] = inbox_digest(tampered)
    (tmp_path / 'tampered.json').write_text(json.dumps(tampered))
    monkeypatch.setattr(sys, 'argv', ['verify_inbox.py', str(tmp_path / 'tampered.json')])
    assert verify_inbox.main() == 1
    problems = json.loads(capsys.readouterr().out)['problems']
    assert any('row 173 waits under the policy but is not in the inbox' in p for p in problems)
    assert any('not_waiting differs' in p for p in problems) and any('waiting differs' in p for p in problems)


def test_no_em_dash_no_personal_shaped_content_no_allegation_words():
    for rel in ('code/inbox.py', 'scripts/build_inbox.py', 'scripts/verify_inbox.py', 'scripts/seal_inbox_policy.py',
                'tests/test_inbox.py', POLICY_FILE, EIO_INBOX, S53_INBOX):
        text = (ROOT / rel).read_text()
        assert chr(0x2014) not in text, rel
        assert not re.search(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}', text), rel
    for rel in (POLICY_FILE, EIO_INBOX, S53_INBOX):
        assert not re.search(r'fraud|corrupt|guilty|illegal|wrongdoing|suspicious', (ROOT / rel).read_text(), re.I), rel
