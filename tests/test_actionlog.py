"""The action log: where a person's decision on an inbox item is recorded.
Constructed cases first (every missing, malformed or extra part of the policy
and of a log refused; the chain recomputes from the inbox hash and breaks at
any altered entry; the hash moves with every part; a decision on a row that
does not wait, or a decision or role off the policy, is refused; an item
without an entry stays open), then the committed policy and both committed
logs checked against the inboxes and the policy in this repository."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest
from actionlog import (ENTRY_KEYS, ITEM_KEYS, POLICY_FILE, POLICY_SCHEMA, SCHEMA, TOP_KEYS, check_log, entry_digest,
                       load_log, load_policy, log_digest, open_log, policy_digest, policy_reference, record, seal_policy)
from inbox import POLICY_FILE as INBOX_POLICY_FILE, check_inbox, load_inbox
from invariant_core import InvariantError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import open_action_log  # noqa: E402
import record_decision  # noqa: E402
import seal_action_policy  # noqa: E402
import verify_action_log  # noqa: E402

EIO_RESULTS = 'research/events_in_order_2026-11-18/results.json'
S53_RESULTS = 'research/section53_2026-11-13/adapter-run/results.json'
EIO_INBOX = 'research/events_in_order_2026-11-18/inbox.json'
S53_INBOX = 'research/section53_2026-11-13/adapter-run/inbox.json'
EIO_LOG = 'research/events_in_order_2026-11-18/action-log.json'
S53_LOG = 'research/section53_2026-11-13/adapter-run/action-log.json'
INBOX_FILES = (INBOX_POLICY_FILE, EIO_RESULTS, S53_RESULTS, EIO_INBOX, S53_INBOX,
               'config/roster.json', 'config/watchers/events-in-order.json', 'config/watchers/section53.json',
               'code/events_in_order.py', 'config/events-in-order-profile.json',
               'code/section53.py', 'config/section53-profile.json')
AT = '2026-11-24T20:00:00Z'


def copy_tree(tmp_path, *rels):
    for rel in rels:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((ROOT / rel).read_bytes())
    return tmp_path


def full_copy(tmp_path):
    return copy_tree(tmp_path, POLICY_FILE, EIO_LOG, S53_LOG, *INBOX_FILES)


def rewrite(root, rel, change):
    data = json.loads((root / rel).read_text())
    change(data)
    (root / rel).write_text(json.dumps(data, indent=2) + '\n')


def reseal(data):
    data['policy_sha256'] = policy_digest(data)


def opened(root, inbox_rel=EIO_INBOX):
    raw = (root / inbox_rel).read_bytes()
    return open_log(load_inbox(root / inbox_rel), inbox_file=inbox_rel, inbox_bytes=raw,
                    policy=load_policy(root, POLICY_FILE), root=root, policy_file=POLICY_FILE)


def decided(root=ROOT, **changes):
    """A log with one entry on row 19 (the first waiting item), constructed, never committed."""
    inbox = load_inbox(root / EIO_INBOX)
    args = dict(position=19, decision='NO_ACTION', role='reviewer', reason='constructed', decided_at=AT,
                policy=load_policy(root, POLICY_FILE))
    args.update(changes)
    return record(opened(root), inbox, **args)


def rehash(data):
    """Recompute every hash of a log after a change, as a careful tamperer would."""
    previous = data['inbox_sha256']
    for entry in data['entries']:
        if set(entry) == ENTRY_KEYS:
            entry['previous_sha256'] = previous
            entry['entry_sha256'] = entry_digest(entry)
            previous = entry['entry_sha256']
    data['head_sha256'] = previous
    data['log_sha256'] = log_digest(data)


def refused_policy(tmp_path, change, message, resealed=True):
    full_copy(tmp_path)
    rewrite(tmp_path, POLICY_FILE, lambda d: (change(d), reseal(d) if resealed else None))
    with pytest.raises(InvariantError, match=message):
        load_policy(tmp_path, POLICY_FILE)


def test_policy_is_typed_and_names_three_decisions_and_two_roles():
    policy = load_policy(ROOT, POLICY_FILE)
    assert policy['schema'] == POLICY_SCHEMA and set(policy) == {'schema', 'purpose', 'decisions', 'roles', 'policy_sha256'}
    assert [d['code'] for d in policy['decisions']] == ['NOTE_ON_RECORD', 'NO_ACTION', 'SEEK_CORRECTION']
    assert policy['roles'] == ['owner', 'reviewer']
    assert all(set(d) == {'code', 'meaning'} and d['meaning'].strip() for d in policy['decisions'])
    assert policy['policy_sha256'] == hashlib.sha256(json.dumps(
        {k: v for k, v in policy.items() if k != 'policy_sha256'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('purpose'), 'Typed action policy'),
    (lambda d: d.update(extra=1), 'Typed action policy'),
    (lambda d: d.update(schema='sunlight.action-policy.v0'), 'Typed action policy'),
    (lambda d: d.update(purpose=' '), 'purpose required'),
    (lambda d: d['decisions'].clear(), 'At least one policy decision'),
    (lambda d: d['decisions'][0].pop('meaning'), 'decision with code and meaning'),
    (lambda d: d['decisions'][0].update(weight=2), 'decision with code and meaning'),
    (lambda d: d['decisions'][0].update(code='no_action'), 'upper-case name'),
    (lambda d: d['decisions'][0].update(code='NO-ACTION'), 'upper-case name'),
    (lambda d: d['decisions'][0].update(meaning=''), 'meaning required'),
    (lambda d: d['decisions'].reverse(), 'ordered by code'),
    (lambda d: d['decisions'].append(dict(d['decisions'][0])), 'distinct and ordered'),
    (lambda d: d['roles'].clear(), 'At least one policy role'),
    (lambda d: d['roles'].append('Owner'), 'each a slug'),
    (lambda d: d.update(roles='owner'), 'At least one policy role'),
    (lambda d: d['roles'].reverse(), 'roles must be distinct and ordered'),
    (lambda d: d['roles'].append('owner'), 'roles must be distinct and ordered'),
])
def test_missing_malformed_or_extra_policy_parts_are_refused(tmp_path, change, message):
    refused_policy(tmp_path, change, message)


def test_a_policy_whose_hash_does_not_recompute_is_refused_and_seal_policy_repairs_nothing_else(tmp_path):
    refused_policy(tmp_path, lambda d: d['roles'].append('secretary'), 'does not recompute', resealed=False)
    refused_policy(tmp_path, lambda d: d.update(policy_sha256='ab' * 32), 'does not recompute', resealed=False)
    with pytest.raises(InvariantError, match='policy file required'):
        load_policy(tmp_path, 'config/no-policy.json')
    policy = load_policy(ROOT, POLICY_FILE)
    assert seal_policy({**policy, 'policy_sha256': 'ab' * 32}) == policy
    with pytest.raises(InvariantError, match='decision with code and meaning'):
        seal_policy({**policy, 'decisions': [{'code': 'X'}]})


def test_the_policy_hash_is_stable_across_locations_and_moves_with_every_part(tmp_path):
    base = load_policy(full_copy(tmp_path), POLICY_FILE)
    assert base == load_policy(ROOT, POLICY_FILE)
    for change in (lambda d: d.update(purpose=d['purpose'] + '.'),
                   lambda d: d['decisions'].pop(),
                   lambda d: d['decisions'][0].update(meaning='Other.'),
                   lambda d: d['roles'].append('secretary'),
                   lambda d: d['roles'].pop()):
        moved = copy.deepcopy(base)
        change(moved)
        assert policy_digest(moved) != base['policy_sha256']


def test_an_opened_log_lists_every_waiting_item_as_open_and_names_the_inbox_by_bytes_and_hash():
    inbox = load_inbox(ROOT / EIO_INBOX)
    log = opened(ROOT)
    assert set(log) == TOP_KEYS and log['schema'] == SCHEMA
    assert log['inbox_file'] == EIO_INBOX and log['inbox_sha256'] == inbox['inbox_sha256']
    assert log['inbox_file_sha256'] == hashlib.sha256((ROOT / EIO_INBOX).read_bytes()).hexdigest()
    assert (log['results_file'], log['results_file_sha256'], log['rule_id'], log['rule_version_sha256']) == \
        (inbox['results_file'], inbox['results_file_sha256'], inbox['rule_id'], inbox['rule_version_sha256'])
    assert log['policy'] == policy_reference(ROOT, load_policy(ROOT), POLICY_FILE)
    assert (log['waiting'], log['decided'], log['open'], log['recorded']) == (5, 0, 5, 0)
    assert log['entries'] == [] and log['head_sha256'] == inbox['inbox_sha256']
    assert [i['position'] for i in log['items']] == [19, 20, 23, 135, 173]
    for line, item in zip(log['items'], inbox['items']):
        assert set(line) == ITEM_KEYS and line['standing'] is None
        assert line['result_sha256'] == item['result_sha256'] and line['item_sha256'] == item['item_sha256']
    assert log['log_sha256'] == log_digest(log)
    with pytest.raises(InvariantError, match='relative path'):
        open_log(inbox, inbox_file='/tmp/inbox.json', inbox_bytes=b'x', policy=load_policy(ROOT), root=ROOT)


def test_the_section53_log_has_nothing_waiting_and_says_so():
    log = opened(ROOT, S53_INBOX)
    assert (log['waiting'], log['decided'], log['open'], log['recorded']) == (0, 0, 0, 0)
    assert log['items'] == [] and log['entries'] == [] and log['rule_id'] == 'section53'
    assert log['head_sha256'] == load_inbox(ROOT / S53_INBOX)['inbox_sha256']
    with pytest.raises(InvariantError, match='Row 0 does not wait'):
        record(log, load_inbox(ROOT / S53_INBOX), position=0, decision='NO_ACTION', role='owner', reason='x',
               decided_at=AT, policy=load_policy(ROOT))


def test_a_recorded_decision_is_one_entry_chained_to_the_inbox_and_the_item_is_decided():
    inbox = load_inbox(ROOT / EIO_INBOX)
    log = decided()
    assert (log['waiting'], log['decided'], log['open'], log['recorded']) == (5, 1, 4, 1)
    entry = log['entries'][0]
    assert set(entry) == ENTRY_KEYS and entry['seq'] == 1 and entry['position'] == 19
    assert entry['result_sha256'] == inbox['items'][0]['result_sha256'] and entry['item_sha256'] == inbox['items'][0]['item_sha256']
    assert entry['decision'] == 'NO_ACTION' and entry['reason'] == 'constructed'
    assert entry['decided_by'] == {'role': 'reviewer'} and entry['decided_at'] == AT
    assert entry['previous_sha256'] == inbox['inbox_sha256'] and entry['entry_sha256'] == entry_digest(entry)
    assert log['head_sha256'] == entry['entry_sha256']
    assert log['items'][0]['standing'] == {'seq': 1, 'decision': 'NO_ACTION'}
    assert all(i['standing'] is None for i in log['items'][1:])
    assert log['log_sha256'] == log_digest(log) and log['log_sha256'] != opened(ROOT)['log_sha256']
    # Everything but the entries, the counts, the items and the head is what the opened log carried.
    for key in TOP_KEYS - {'entries', 'decided', 'open', 'recorded', 'items', 'head_sha256', 'log_sha256'}:
        assert log[key] == opened(ROOT)[key], key


def test_a_second_decision_on_the_same_item_is_a_new_entry_after_the_first_never_a_replacement():
    inbox = load_inbox(ROOT / EIO_INBOX)
    first = decided()
    second = record(first, inbox, position=19, decision='SEEK_CORRECTION', role='owner', reason='constructed, again',
                    decided_at='2026-11-24T20:01:00Z', policy=load_policy(ROOT))
    assert second['recorded'] == 2 and second['decided'] == 1 and second['open'] == 4
    assert second['entries'][0] == first['entries'][0]
    assert second['entries'][1]['seq'] == 2 and second['entries'][1]['previous_sha256'] == first['entries'][0]['entry_sha256']
    assert second['items'][0]['standing'] == {'seq': 2, 'decision': 'SEEK_CORRECTION'}
    assert second['head_sha256'] == second['entries'][1]['entry_sha256']
    third = record(second, inbox, position=173, decision='NOTE_ON_RECORD', role='reviewer', reason='constructed, third',
                   decided_at='2026-11-24T20:02:00Z', policy=load_policy(ROOT))
    assert third['decided'] == 2 and third['open'] == 3 and third['recorded'] == 3
    assert [i['standing'] for i in third['items']] == [{'seq': 2, 'decision': 'SEEK_CORRECTION'}, None, None, None,
                                                        {'seq': 3, 'decision': 'NOTE_ON_RECORD'}]


@pytest.mark.parametrize('changes, message', [
    (dict(position=21), 'Row 21 does not wait'),
    (dict(position='19'), 'Item position required'),
    (dict(position=True), 'Item position required'),
    (dict(decision='IGNORE'), 'Decision is not on the action policy'),
    (dict(decision='no_action'), 'Decision is not on the action policy'),
    (dict(role='secretary'), 'Role is not on the action policy'),
    (dict(reason=''), 'reason required'),
    (dict(reason='  '), 'reason required'),
    (dict(reason='ask someone at name@example.org'), 'must not carry an address'),
    (dict(decided_at='2026-11-24T20:00:00'), 'UTC to the second'),
    (dict(decided_at='2026-11-24 20:00:00Z'), 'UTC to the second'),
    (dict(decided_at='2026-11-24T20:00:00+00:00'), 'UTC to the second'),
    (dict(decided_at='2026-13-24T20:00:00Z'), 'not a calendar time'),
    (dict(decided_at='2026-11-24T24:00:00Z'), 'not a calendar time'),
])
def test_a_decision_on_a_row_that_does_not_wait_or_off_the_policy_or_without_a_reason_or_time_is_refused(changes, message):
    with pytest.raises(InvariantError, match=message):
        decided(**changes)


def test_a_decision_is_refused_on_a_log_that_names_another_inbox_or_another_policy(tmp_path):
    full_copy(tmp_path)
    inbox = load_inbox(ROOT / EIO_INBOX)
    policy = load_policy(ROOT)
    log = opened(ROOT)
    with pytest.raises(InvariantError, match='Log does not name this inbox'):
        record(log, load_inbox(ROOT / S53_INBOX), position=19, decision='NO_ACTION', role='owner', reason='x', decided_at=AT, policy=policy)
    with pytest.raises(InvariantError, match='Inbox file bytes differ'):
        record(log, inbox, position=19, decision='NO_ACTION', role='owner', reason='x', decided_at=AT, policy=policy,
               inbox_bytes=(ROOT / EIO_INBOX).read_bytes() + b'\n')
    rewrite(tmp_path, POLICY_FILE, lambda d: (d['roles'].append('secretary'), reseal(d)))
    with pytest.raises(InvariantError, match='Log names another action policy'):
        record(log, inbox, position=19, decision='NO_ACTION', role='secretary', reason='x', decided_at=AT,
               policy=load_policy(tmp_path))


def test_the_log_hash_is_stable_across_locations_and_moves_with_every_part(tmp_path):
    base = opened(full_copy(tmp_path))
    assert base == opened(ROOT) == load_log(ROOT / EIO_LOG)
    with_entry = decided()
    for change in (lambda d: d['entries'][0].update(decision='SEEK_CORRECTION'),
                   lambda d: d['entries'][0].update(reason='other'),
                   lambda d: d['entries'][0].update(decided_at='2026-11-24T20:00:01Z'),
                   lambda d: d['entries'][0]['decided_by'].update(role='owner'),
                   lambda d: d['entries'][0].update(position=20),
                   lambda d: d['entries'].pop(),
                   lambda d: d['items'][1].update(standing={'seq': 1, 'decision': 'NO_ACTION'}),
                   lambda d: d.update(open=3),
                   lambda d: d['policy'].update(policy_sha256='ab' * 32),
                   lambda d: d.update(inbox_sha256='ab' * 32),
                   lambda d: d.update(inbox_file_sha256='ab' * 32),
                   lambda d: d.update(purpose=d['purpose'] + '.')):
        moved = copy.deepcopy(with_entry)
        change(moved)
        assert log_digest(moved) != with_entry['log_sha256']


def write_log(tmp_path, data, name='log.json'):
    (tmp_path / name).write_text(json.dumps(data))
    return tmp_path / name


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('purpose'), 'Typed action log'),
    (lambda d: d.update(decider='someone'), 'Typed action log'),
    (lambda d: d.update(schema='sunlight.action-log.v0'), 'Typed action log'),
    (lambda d: d.update(inbox_file='../inbox.json'), 'relative path'),
    (lambda d: d.update(inbox_sha256='abc'), 'inbox_sha256 required'),
    (lambda d: d.update(rule_id='Rule'), 'rule_id required as a slug'),
    (lambda d: d['policy'].pop('policy_file'), 'policy reference required'),
    (lambda d: d.update(waiting=-1), 'waiting required as a count'),
    (lambda d: d.update(entries={}), 'entries required as a list'),
    (lambda d: d['entries'][0].pop('reason'), 'entry with every part'),
    (lambda d: d['entries'][0].update(verdict='guilty'), 'entry with every part'),
    (lambda d: d['entries'][0].update(seq=2), 'numbered from 1 in order'),
    (lambda d: d['entries'][0].update(decision='no_action'), 'decision required as an upper-case name'),
    (lambda d: d['entries'][0].update(reason=''), 'entry reason required'),
    (lambda d: d['entries'][0].update(reason='mail name@example.org'), 'must not carry an address'),
    (lambda d: d['entries'][0].update(decided_by={'name': 'A Person'}), 'decided_by required as a role'),
    (lambda d: d['entries'][0].update(decided_by={'role': 'reviewer', 'name': 'A Person'}), 'decided_by required as a role'),
    (lambda d: d['entries'][0].update(decided_at='today'), 'UTC to the second'),
    (lambda d: d['entries'][0].update(position=21), 'which the log does not list as waiting'),
    (lambda d: d['entries'][0].update(item_sha256='ab' * 32), 'names other hashes than the item'),
    (lambda d: d['items'][0].pop('standing'), 'item with every part'),
    (lambda d: d['items'][0].update(standing={'seq': 1}), 'standing required as the latest entry or null'),
    (lambda d: d['items'][1].update(standing={'seq': 1, 'decision': 'NO_ACTION'}), 'items does not recompute'),
    (lambda d: d['items'][0].update(standing=None), 'items does not recompute'),
    (lambda d: d['items'].reverse(), 'in inbox order'),
    (lambda d: d['items'].pop(), 'one per waiting inbox item'),
    (lambda d: d.update(open=5), 'open does not recompute'),
    (lambda d: d.update(decided=0), 'decided does not recompute'),
    (lambda d: d.update(recorded=2), 'recorded does not recompute'),
])
def test_missing_malformed_or_extra_log_parts_are_refused_even_when_rehashed(tmp_path, change, message):
    data = decided()
    change(data)
    rehash(data)
    with pytest.raises(InvariantError, match=message):
        load_log(write_log(tmp_path, data))


def test_a_log_whose_chain_or_hashes_do_not_recompute_is_refused(tmp_path):
    inbox = load_inbox(ROOT / EIO_INBOX)
    two = record(decided(), inbox, position=20, decision='NO_ACTION', role='owner', reason='second', decided_at=AT,
                 policy=load_policy(ROOT))
    for change, message in ((lambda d: d['entries'][0].update(reason='edited'), 'entry 1 entry_sha256 does not recompute'),
                            (lambda d: d['entries'][0].update(previous_sha256='ab' * 32), 'entry 1 does not carry the hash'),
                            (lambda d: d['entries'][1].update(previous_sha256='ab' * 32), 'entry 2 does not carry the hash'),
                            (lambda d: d['entries'].pop(0), 'numbered from 1 in order'),
                            (lambda d: (d['entries'].pop(0), d['entries'][0].update(seq=1)), 'entry 1 does not carry the hash'),
                            (lambda d: d.update(head_sha256='ab' * 32), 'head_sha256 does not recompute'),
                            (lambda d: d.update(purpose=d['purpose'] + '.'), 'log_sha256 does not recompute'),
                            (lambda d: d.update(log_sha256='ab' * 32), 'log_sha256 does not recompute')):
        data = copy.deepcopy(two)
        change(data)
        with pytest.raises(InvariantError, match=message):
            load_log(write_log(tmp_path, data))
    # An entry edited and its own hash recomputed breaks the entry after it: the chain holds the order.
    data = copy.deepcopy(two)
    data['entries'][0]['reason'] = 'edited'
    data['entries'][0]['entry_sha256'] = entry_digest(data['entries'][0])
    with pytest.raises(InvariantError, match='entry 2 does not carry the hash of the entry before it'):
        load_log(write_log(tmp_path, data))
    # The last entry removed and the head and log hash recomputed loads: a chain proves order and content,
    # not that nothing was cut from its end. The committed history of the file is the record against that.
    data = copy.deepcopy(two)
    data['entries'].pop()
    data['items'][1]['standing'] = None
    data.update(decided=1, open=4, recorded=1)
    rehash(data)
    assert load_log(write_log(tmp_path, data))['recorded'] == 1
    with pytest.raises(InvariantError, match='Action log file required'):
        load_log(tmp_path / 'no-log.json')


def test_check_log_finds_every_difference_from_the_checkout(tmp_path):
    full_copy(tmp_path)
    log = load_log(tmp_path / EIO_LOG)
    assert check_log(log, tmp_path) == []
    with_entry = decided(tmp_path)
    assert check_log(with_entry, tmp_path) == []
    # A byte of the inbox file: its bytes hash moves, its content does not.
    (tmp_path / EIO_INBOX).write_bytes((ROOT / EIO_INBOX).read_bytes() + b'\n')
    assert check_log(log, tmp_path) == ['inbox file bytes differ from the ones the log names']
    # An inbox rebuilt under a narrower policy: the rows the log lists no longer wait.
    full_copy(tmp_path)
    rewrite(tmp_path, INBOX_POLICY_FILE, lambda d: (d['rules'][0]['waits'].clear(), d.update(
        policy_sha256=hashlib.sha256(json.dumps({k: v for k, v in d.items() if k != 'policy_sha256'}, sort_keys=True,
                                                 separators=(',', ':'), ensure_ascii=False).encode()).hexdigest())))
    raw = (tmp_path / EIO_RESULTS).read_bytes()
    from inbox import build_inbox, load_policy as load_inbox_policy
    narrowed = build_inbox(json.loads(raw), results_file=EIO_RESULTS, results_bytes=raw,
                           policy=load_inbox_policy(tmp_path), root=tmp_path)
    (tmp_path / EIO_INBOX).write_text(json.dumps(narrowed, sort_keys=True, indent=2) + '\n')
    problems = check_log(log, tmp_path)
    assert 'inbox file bytes differ from the ones the log names' in problems
    assert 'inbox_sha256 differs from the inbox in this checkout' in problems
    assert 'waiting differs from the inbox in this checkout' in problems
    assert [p for p in problems if 'does not wait in the inbox' in p] == [
        f"row {i['position']} is listed in the log but does not wait in the inbox" for i in log['items']]
    # An item line with other hashes than the inbox item; an item the log leaves out.
    full_copy(tmp_path)
    altered = copy.deepcopy(log)
    altered['items'][2]['item_sha256'] = 'ab' * 32
    assert check_log(altered, tmp_path) == ['row 23 carries other hashes in the log than in the inbox']
    altered = copy.deepcopy(log)
    altered['items'].pop(1)
    altered['waiting'] = 4
    assert check_log(altered, tmp_path) == ['waiting differs from the inbox in this checkout',
                                            'row 20 waits in the inbox but is not listed in the log']
    # A policy resealed with another role: the reference differs and an entry's role is off the table.
    full_copy(tmp_path)
    rewrite(tmp_path, POLICY_FILE, lambda d: (d['roles'].remove('reviewer'), reseal(d)))
    assert check_log(with_entry, tmp_path) == ['policy differs from the action policy in this checkout',
                                               'entry 1 records a role that is not on the action policy']
    rewrite(tmp_path, POLICY_FILE, lambda d: (d['decisions'].pop(1), d['roles'].append('reviewer'), reseal(d)))
    assert check_log(with_entry, tmp_path) == ['policy differs from the action policy in this checkout',
                                               'entry 1 records a decision that is not on the action policy']
    # An inbox file that is not in the checkout, an inbox that cannot be loaded, a policy that cannot be loaded.
    full_copy(tmp_path)
    assert check_log({**log, 'inbox_file': 'research/none.json'}, tmp_path) == ['inbox file the log names is not in this checkout']
    (tmp_path / EIO_INBOX).write_text('{}')
    assert check_log(log, tmp_path) == ['inbox file bytes differ from the ones the log names',
                                        'inbox the log names cannot be loaded (Typed inbox with every part required)']
    full_copy(tmp_path)
    (tmp_path / POLICY_FILE).write_text('{}')
    assert check_log(log, tmp_path) == ['action policy cannot be loaded from this checkout (Typed action policy with purpose, decisions, roles and policy_sha256 required)']


def test_committed_logs_are_what_this_checkout_opens_with_nothing_recorded_and_name_verified_inboxes():
    for log_rel, inbox_rel, waiting in ((EIO_LOG, EIO_INBOX, 5), (S53_LOG, S53_INBOX, 0)):
        log = load_log(ROOT / log_rel)
        assert log == opened(ROOT, inbox_rel)
        assert (log['waiting'], log['decided'], log['open'], log['recorded']) == (waiting, 0, waiting, 0)
        assert log['entries'] == [] and all(i['standing'] is None for i in log['items'])
        assert check_log(log, ROOT) == []
        inbox = load_inbox(ROOT / inbox_rel)
        assert check_inbox(inbox, ROOT) == [] and log['inbox_sha256'] == inbox['inbox_sha256']
        assert log['policy']['policy_file_sha256'] == hashlib.sha256((ROOT / POLICY_FILE).read_bytes()).hexdigest()
    assert load_log(ROOT / EIO_LOG)['inbox_sha256'] == 'dd1032bcc576e585efd90ef2f9f50c639e3b02e1de9f9e690c7410b4efd88d82'
    assert load_log(ROOT / S53_LOG)['inbox_sha256'] == 'b30b33df13c2821d2c18c1eb78d83628d842af8e3786f1ef6fff02c44d125b94'


def test_scripts_write_only_their_output_and_exit_zero_on_the_committed_files(tmp_path, capsys, monkeypatch):
    watched = [ROOT / p for p in (POLICY_FILE, INBOX_POLICY_FILE, EIO_INBOX, S53_INBOX, EIO_LOG, S53_LOG, EIO_RESULTS, S53_RESULTS)]
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched}
    monkeypatch.setattr(sys, 'argv', ['verify_action_log.py', str(ROOT / EIO_LOG), str(ROOT / S53_LOG)])
    assert verify_action_log.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out['problems'] == [] and [f['open'] for f in out['logs'].values()] == [5, 0]
    monkeypatch.setattr(sys, 'argv', ['seal_action_policy.py'])
    assert seal_action_policy.main() == 0
    assert json.loads(capsys.readouterr().out) == load_policy(ROOT)
    # The open script writes its output and nothing else, refuses an existing output and an inbox outside the repository.
    out_path = tmp_path / 'action-log.json'
    monkeypatch.setattr(sys, 'argv', ['open_action_log.py', str(ROOT / EIO_INBOX), str(out_path)])
    assert open_action_log.main() == 0
    assert json.loads(capsys.readouterr().out)['open'] == 5
    assert out_path.read_bytes() == (ROOT / EIO_LOG).read_bytes()
    with pytest.raises(SystemExit, match='Refusing to overwrite'):
        open_action_log.main()
    (tmp_path / 'outside.json').write_bytes((ROOT / EIO_INBOX).read_bytes())
    monkeypatch.setattr(sys, 'argv', ['open_action_log.py', str(tmp_path / 'outside.json'), str(tmp_path / 'other.json')])
    with pytest.raises(SystemExit, match='inside the repository'):
        open_action_log.main()
    # The record script refuses a log outside the repository, so it never writes there.
    monkeypatch.setattr(sys, 'argv', ['record_decision.py', str(out_path), '--item', '19', '--decision', 'NO_ACTION',
                                      '--role', 'owner', '--reason', 'constructed', '--at', AT])
    with pytest.raises(SystemExit, match='inside the repository'):
        record_decision.main()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['action-log.json', 'outside.json']
    assert {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched} == before
    # A tampered log fails the verifier with the difference named.
    tampered = decided()
    tampered['entries'][0]['decided_by'] = {'role': 'secretary'}
    rehash(tampered)
    monkeypatch.setattr(sys, 'argv', ['verify_action_log.py', str(write_log(tmp_path, tampered, 'tampered.json'))])
    assert verify_action_log.main() == 1
    problems = json.loads(capsys.readouterr().out)['problems']
    assert any('entry 1 records a role that is not on the action policy' in p for p in problems)


def test_record_script_appends_one_entry_to_a_log_inside_the_repository_and_writes_nothing_else(tmp_path, capsys, monkeypatch):
    scratch = ROOT / 'research' / 'events_in_order_2026-11-18' / f'scratch-{tmp_path.name}.json'
    scratch.write_bytes((ROOT / EIO_LOG).read_bytes())
    watched = [ROOT / p for p in (POLICY_FILE, EIO_INBOX, EIO_LOG, EIO_RESULTS)]
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched}
    try:
        monkeypatch.setattr(sys, 'argv', ['record_decision.py', str(scratch), '--item', '19', '--decision', 'NO_ACTION',
                                          '--role', 'owner', '--reason', 'constructed', '--at', AT])
        assert record_decision.main() == 0
        printed = json.loads(capsys.readouterr().out)
        log = load_log(scratch)
        assert log == decided(role='owner') and printed['entry'] == log['entries'][0]
        assert (printed['decided'], printed['open'], printed['recorded']) == (1, 4, 1)
        assert check_log(log, ROOT) == []
        # A second decision on the same item appends; a decision on a row that does not wait is refused and writes nothing.
        monkeypatch.setattr(sys, 'argv', ['record_decision.py', str(scratch), '--item', '19', '--decision', 'SEEK_CORRECTION',
                                          '--role', 'reviewer', '--reason', 'constructed, again', '--at', '2026-11-24T20:01:00Z'])
        assert record_decision.main() == 0
        capsys.readouterr()
        bytes_after_two = scratch.read_bytes()
        monkeypatch.setattr(sys, 'argv', ['record_decision.py', str(scratch), '--item', '21', '--decision', 'NO_ACTION',
                                          '--role', 'owner', '--reason', 'constructed', '--at', AT])
        with pytest.raises(SystemExit, match='Row 21 does not wait'):
            record_decision.main()
        assert scratch.read_bytes() == bytes_after_two
        log = load_log(scratch)
        assert log['recorded'] == 2 and log['items'][0]['standing'] == {'seq': 2, 'decision': 'SEEK_CORRECTION'}
        # Without --at the clock gives the time, in the required shape.
        monkeypatch.setattr(sys, 'argv', ['record_decision.py', str(scratch), '--item', '20', '--decision', 'NOTE_ON_RECORD',
                                          '--role', 'owner', '--reason', 'constructed'])
        assert record_decision.main() == 0
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', json.loads(capsys.readouterr().out)['entry']['decided_at'])
        assert load_log(scratch)['open'] == 3
    finally:
        scratch.unlink()
    assert {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in watched} == before


def test_no_em_dash_no_personal_shaped_content_no_allegation_words():
    for rel in ('code/actionlog.py', 'scripts/open_action_log.py', 'scripts/record_decision.py',
                'scripts/verify_action_log.py', 'scripts/seal_action_policy.py', 'tests/test_actionlog.py',
                POLICY_FILE, EIO_LOG, S53_LOG):
        text = (ROOT / rel).read_text()
        assert chr(0x2014) not in text, rel
    for rel in (POLICY_FILE, EIO_LOG, S53_LOG):
        text = (ROOT / rel).read_text()
        assert not re.search(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}', text), rel
        assert not re.search(r'fraud|corrupt|guilty|illegal|wrongdoing|suspicious', text, re.I), rel
    # The committed logs carry no name, no decider but a role, and no decision at all.
    for rel in (EIO_LOG, S53_LOG):
        log = json.loads((ROOT / rel).read_text())
        assert log['entries'] == [] and 'name' not in json.dumps(log)
