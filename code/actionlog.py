"""The action log: where a person's decision on an inbox item is recorded.

The decision inbox (see code/inbox.py) lists the result rows that wait for
a person. The action log is the record of what people decided about them:
one entry per decision, in the order the decisions were recorded, each
naming the inbox item it answers (by position, result hash and item hash),
the decision taken from the action policy's table, the reason the person
gave, the role that decided and the time. Every entry carries the hash of
the entry before it, and the first entry carries the hash of the inbox, so
the log is a chain anchored to the inbox it answers. The whole log is hashed
into log_sha256.

Nothing here decides. A decision is recorded because a person recorded it;
the log never supplies one, never defaults one, and never judges one. A
waiting item without an entry is open and is reported as open, never as
settled. A later entry on the same item is a new decision, recorded after
the earlier one, which stays in the log; the standing decision on an item
is the latest recorded, and the earlier ones remain readable. No personal
data: the decider is a role named on the policy, never a person. A result
is a risk indicator, never an allegation; whether a procurement should have
happened stays with people, and the log records what they said follows.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from custody import HEX64, digest, file_sha256
from inbox import load_inbox
from invariant_core import InvariantError
from watcher import SLUG

SCHEMA = 'sunlight.action-log.v1'
POLICY_SCHEMA = 'sunlight.action-policy.v1'
POLICY_FILE = 'config/action-policy.json'
POLICY_KEYS = {'schema', 'purpose', 'decisions', 'roles', 'policy_sha256'}
DECISION_KEYS = {'code', 'meaning'}
TOP_KEYS = {'schema', 'purpose', 'inbox_file', 'inbox_file_sha256', 'inbox_sha256', 'results_file',
            'results_file_sha256', 'rule_id', 'rule_version_sha256', 'policy', 'waiting', 'decided', 'open',
            'recorded', 'items', 'entries', 'head_sha256', 'log_sha256'}
ENTRY_KEYS = {'seq', 'position', 'result_sha256', 'item_sha256', 'decision', 'reason', 'decided_by', 'decided_at',
              'previous_sha256', 'entry_sha256'}
ITEM_KEYS = {'position', 'result_sha256', 'item_sha256', 'standing'}
STANDING_KEYS = {'seq', 'decision'}
TIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')
EMAIL = re.compile(r'[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}')
PURPOSE = ('Decisions people recorded on the items of one decision inbox. Each entry is one decision on one '
           'item: the decision from the action policy, the reason given, the role that decided and the time, '
           'chained by hash to the entry before it and anchored to the inbox. The system never decides; a '
           'person does. An item without an entry is open, never settled.')


def _text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise InvariantError(f'{what} required')
    return value


def _count(value, what):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvariantError(f'{what} required as a count')
    return value


def _hex(value, what):
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise InvariantError(f'{what} required')
    return value


def _relative(path, what) -> str:
    if not isinstance(path, str) or not path or path.startswith('/') or '..' in path.split('/') or '\\' in path:
        raise InvariantError(f'{what} required as a relative path')
    return path


def _decision(value) -> dict:
    if not isinstance(value, dict) or set(value) != DECISION_KEYS:
        raise InvariantError('Policy decision with code and meaning required')
    code = value['code']
    if not isinstance(code, str) or not code or not code.isupper() or not code.replace('_', '').isalpha():
        raise InvariantError('Policy decision code required as an upper-case name')
    _text(value['meaning'], 'Policy decision meaning')
    return value


def policy_digest(policy: dict) -> str:
    """The hash over everything in the policy but its own hash."""
    return digest({k: v for k, v in policy.items() if k != 'policy_sha256'})


def _policy(data) -> dict:
    """Every part of a policy but its hash, checked. Any missing, malformed or extra part is refused."""
    if not isinstance(data, dict) or data.get('schema') != POLICY_SCHEMA or set(data) != POLICY_KEYS:
        raise InvariantError('Typed action policy with purpose, decisions, roles and policy_sha256 required')
    _text(data['purpose'], 'Policy purpose')
    decisions = data['decisions']
    if not isinstance(decisions, list) or not decisions:
        raise InvariantError('At least one policy decision required')
    for decision in decisions:
        _decision(decision)
    codes = [d['code'] for d in decisions]
    if codes != sorted(codes) or len(set(codes)) != len(codes):
        raise InvariantError('Policy decisions must be distinct and ordered by code')
    roles = data['roles']
    if not isinstance(roles, list) or not roles or not all(isinstance(r, str) and SLUG.fullmatch(r) for r in roles):
        raise InvariantError('At least one policy role required, each a slug')
    if roles != sorted(roles) or len(set(roles)) != len(roles):
        raise InvariantError('Policy roles must be distinct and ordered')
    return data


def seal_policy(data) -> dict:
    """The policy with policy_sha256 recomputed from its other parts, which must all hold. Writes nothing."""
    checked = _policy(data)
    return {**{k: v for k, v in checked.items() if k != 'policy_sha256'}, 'policy_sha256': policy_digest(checked)}


def load_policy(root, path=POLICY_FILE) -> dict:
    """The policy file, checked part by part, its hash recomputed. Nothing is repaired."""
    file = Path(root) / path
    if not file.is_file():
        raise InvariantError('Action policy file required')
    data = _policy(json.loads(file.read_text()))
    if data['policy_sha256'] != policy_digest(data):
        raise InvariantError('policy_sha256 does not recompute from the policy')
    return data


def policy_reference(root, policy: dict, path=POLICY_FILE) -> dict:
    """The block a log carries: which policy, by file bytes and by content."""
    return {'policy_file': str(path), 'policy_file_sha256': file_sha256(Path(root) / path),
            'policy_sha256': policy['policy_sha256']}


def entry_digest(entry: dict) -> str:
    return digest({k: v for k, v in entry.items() if k != 'entry_sha256'})


def log_digest(log: dict) -> str:
    """The hash over everything in the log but its own hash."""
    return digest({k: v for k, v in log.items() if k != 'log_sha256'})


def _items(inbox: dict, entries: list[dict]) -> list[dict]:
    """One line per waiting item of the inbox, in inbox order, with the latest entry on it or null."""
    standing = {}
    for entry in entries:
        standing[entry['position']] = {'seq': entry['seq'], 'decision': entry['decision']}
    return [{'position': i['position'], 'result_sha256': i['result_sha256'], 'item_sha256': i['item_sha256'],
             'standing': standing.get(i['position'])} for i in inbox['items']]


def _assemble(log: dict, inbox: dict, entries: list[dict]) -> dict:
    """The log with its entries, its derived parts recomputed and its hash. Nothing else moves."""
    items = _items(inbox, entries)
    decided = sum(1 for i in items if i['standing'] is not None)
    body = {**{k: v for k, v in log.items() if k not in ('items', 'entries', 'head_sha256', 'log_sha256',
                                                          'decided', 'open', 'recorded')},
            'decided': decided, 'open': len(items) - decided, 'recorded': len(entries),
            'items': items, 'entries': entries,
            'head_sha256': entries[-1]['entry_sha256'] if entries else inbox['inbox_sha256']}
    body = {k: body[k] for k in ('schema', 'purpose', 'inbox_file', 'inbox_file_sha256', 'inbox_sha256', 'results_file',
                                 'results_file_sha256', 'rule_id', 'rule_version_sha256', 'policy', 'waiting', 'decided',
                                 'open', 'recorded', 'items', 'entries', 'head_sha256')}
    return {**body, 'log_sha256': log_digest(body)}


def open_log(inbox: dict, *, inbox_file: str, inbox_bytes: bytes, policy: dict, root, policy_file=POLICY_FILE) -> dict:
    """A log with no entries for one inbox under one policy. Builds in memory and returns; writes nothing.

    Every waiting item of the inbox is listed as open. The log names the
    inbox by relative path, by the hash of its bytes and by inbox_sha256,
    and copies the results file, rule id and rule version the inbox names.
    """
    body = {'schema': SCHEMA, 'purpose': PURPOSE,
            'inbox_file': _relative(inbox_file, 'Inbox file'), 'inbox_file_sha256': digest_bytes(inbox_bytes),
            'inbox_sha256': inbox['inbox_sha256'],
            'results_file': inbox['results_file'], 'results_file_sha256': inbox['results_file_sha256'],
            'rule_id': inbox['rule_id'], 'rule_version_sha256': inbox['rule_version_sha256'],
            'policy': policy_reference(root, policy, policy_file), 'waiting': inbox['waiting']}
    return _assemble(body, inbox, [])


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _same_inbox(log: dict, inbox: dict, inbox_bytes: bytes | None) -> None:
    if log['inbox_sha256'] != inbox['inbox_sha256'] or log['waiting'] != inbox['waiting']:
        raise InvariantError('Log does not name this inbox')
    if inbox_bytes is not None and log['inbox_file_sha256'] != digest_bytes(inbox_bytes):
        raise InvariantError('Inbox file bytes differ from the ones the log names')


def record(log: dict, inbox: dict, *, position: int, decision: str, role: str, reason: str, decided_at: str,
           policy: dict, inbox_bytes: bytes | None = None) -> dict:
    """The log with one more entry: a person's decision on one waiting item. Returns a new log; writes nothing.

    The item must wait in the inbox the log names; the decision and the role
    must be on the policy the log names; the reason must be given; the time
    is recorded as given, in UTC to the second. A decision on an item that
    already has one is a new entry after the old one, never a replacement.
    """
    _same_inbox(log, inbox, inbox_bytes)
    if log['policy']['policy_sha256'] != policy['policy_sha256']:
        raise InvariantError('Log names another action policy')
    if not isinstance(position, int) or isinstance(position, bool):
        raise InvariantError('Item position required')
    item = next((i for i in inbox['items'] if i['position'] == position), None)
    if item is None:
        raise InvariantError(f'Row {position} does not wait in this inbox; nothing can be decided on it')
    if not isinstance(decision, str) or decision not in {d['code'] for d in policy['decisions']}:
        raise InvariantError('Decision is not on the action policy')
    if not isinstance(role, str) or role not in policy['roles']:
        raise InvariantError('Role is not on the action policy')
    _text(reason, 'Decision reason')
    if EMAIL.search(reason):
        raise InvariantError('Decision reason must not carry an address')
    _time(decided_at)
    entries = list(log['entries'])
    body = {'seq': len(entries) + 1, 'position': position, 'result_sha256': item['result_sha256'],
            'item_sha256': item['item_sha256'], 'decision': decision, 'reason': reason,
            'decided_by': {'role': role}, 'decided_at': decided_at, 'previous_sha256': log['head_sha256']}
    entries.append({**body, 'entry_sha256': entry_digest(body)})
    return _assemble(log, inbox, entries)


def _time(value) -> str:
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise InvariantError('Decision time required as UTC to the second, like 2026-11-24T20:00:00Z')
    try:
        datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError as exc:
        raise InvariantError('Decision time is not a calendar time') from exc
    return value


def _entry(value, seq: int, previous: str) -> dict:
    if not isinstance(value, dict) or set(value) != ENTRY_KEYS:
        raise InvariantError('Log entry with every part required')
    if value['seq'] != seq:
        raise InvariantError('Log entries must be numbered from 1 in order')
    _count(value['position'], 'Log entry position')
    _hex(value['result_sha256'], 'Log entry result_sha256')
    _hex(value['item_sha256'], 'Log entry item_sha256')
    code = value['decision']
    if not isinstance(code, str) or not code or not code.isupper() or not code.replace('_', '').isalpha():
        raise InvariantError('Log entry decision required as an upper-case name')
    _text(value['reason'], 'Log entry reason')
    if EMAIL.search(value['reason']):
        raise InvariantError('Log entry reason must not carry an address')
    by = value['decided_by']
    if not isinstance(by, dict) or set(by) != {'role'} or not isinstance(by['role'], str) or not SLUG.fullmatch(by['role']):
        raise InvariantError('Log entry decided_by required as a role')
    _time(value['decided_at'])
    if value['previous_sha256'] != previous:
        raise InvariantError(f'Log entry {seq} does not carry the hash of the entry before it')
    if value['entry_sha256'] != entry_digest(value):
        raise InvariantError(f'Log entry {seq} entry_sha256 does not recompute')
    return value


def load_log(path) -> dict:
    """A log file, checked part by part. Any missing, malformed or extra part is refused.

    The chain is recomputed entry by entry from the inbox hash; the items
    list, the counts and head_sha256 are recomputed from the entries and
    compared. This reads the log only. Whether it names the inbox and the
    policy in a checkout, and whether every entry answers an item that
    inbox lists, is check_log's question.
    """
    file = Path(path)
    if not file.is_file():
        raise InvariantError('Action log file required')
    data = json.loads(file.read_text())
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or set(data) != TOP_KEYS:
        raise InvariantError('Typed action log with every part required')
    _text(data['purpose'], 'Log purpose')
    _relative(data['inbox_file'], 'Inbox file')
    _relative(data['results_file'], 'Results file')
    for key in ('inbox_file_sha256', 'inbox_sha256', 'results_file_sha256', 'rule_version_sha256', 'head_sha256'):
        _hex(data[key], f'Log {key}')
    if not isinstance(data['rule_id'], str) or not SLUG.fullmatch(data['rule_id']):
        raise InvariantError('Log rule_id required as a slug')
    policy = data['policy']
    if not isinstance(policy, dict) or set(policy) != {'policy_file', 'policy_file_sha256', 'policy_sha256'} \
            or not all(isinstance(policy[k], str) and HEX64.fullmatch(policy[k]) for k in ('policy_file_sha256', 'policy_sha256')):
        raise InvariantError('Log policy reference required')
    _relative(policy['policy_file'], 'Policy file')
    for key in ('waiting', 'decided', 'open', 'recorded'):
        _count(data[key], f'Log {key}')
    entries = data['entries']
    if not isinstance(entries, list):
        raise InvariantError('Log entries required as a list')
    previous = data['inbox_sha256']
    for seq, entry in enumerate(entries, start=1):
        _entry(entry, seq, previous)
        previous = entry['entry_sha256']
    items = data['items']
    if not isinstance(items, list) or len(items) != data['waiting']:
        raise InvariantError('Log items required, one per waiting inbox item')
    positions = []
    for item in items:
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            raise InvariantError('Log item with every part required')
        _count(item['position'], 'Log item position')
        _hex(item['result_sha256'], 'Log item result_sha256')
        _hex(item['item_sha256'], 'Log item item_sha256')
        if item['standing'] is not None and (not isinstance(item['standing'], dict) or set(item['standing']) != STANDING_KEYS):
            raise InvariantError('Log item standing required as the latest entry or null')
        positions.append(item['position'])
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise InvariantError('Log items must be distinct and in inbox order')
    listed = {i['position']: i for i in items}
    for entry in entries:
        item = listed.get(entry['position'])
        if item is None:
            raise InvariantError(f"Log entry {entry['seq']} answers row {entry['position']}, which the log does not list as waiting")
        if item['result_sha256'] != entry['result_sha256'] or item['item_sha256'] != entry['item_sha256']:
            raise InvariantError(f"Log entry {entry['seq']} names other hashes than the item it answers")
    expected = _assemble(data, {'items': items, 'inbox_sha256': data['inbox_sha256']}, entries)
    for key in ('items', 'decided', 'open', 'recorded', 'head_sha256'):
        if data[key] != expected[key]:
            raise InvariantError(f'Log {key} does not recompute from the entries')
    if data['log_sha256'] != log_digest(data):
        raise InvariantError('log_sha256 does not recompute from the log')
    return data


def check_log(log: dict, root, policy_file=POLICY_FILE) -> list[str]:
    """Problems with a loaded log against the inbox and the policy in this checkout.

    The inbox file the log names is read from the checkout, its bytes
    compared and its parts loaded; every item line and every entry is
    compared with the inbox item at that position; the policy reference is
    compared with the checkout's policy and every entry's decision and role
    with its tables. Empty means every link holds. Whether the inbox itself
    is what the checkout builds is check_inbox's question, asked by the
    verifier beside this one.
    """
    root = Path(root)
    problems = []
    inbox_path = root / log['inbox_file']
    if not inbox_path.is_file():
        return ['inbox file the log names is not in this checkout']
    inbox_bytes = inbox_path.read_bytes()
    if log['inbox_file_sha256'] != digest_bytes(inbox_bytes):
        problems.append('inbox file bytes differ from the ones the log names')
    try:
        inbox = load_inbox(inbox_path)
    except InvariantError as exc:
        return problems + [f'inbox the log names cannot be loaded ({exc})']
    if log['inbox_sha256'] != inbox['inbox_sha256']:
        problems.append('inbox_sha256 differs from the inbox in this checkout')
    for key in ('results_file', 'results_file_sha256', 'rule_id', 'rule_version_sha256', 'waiting'):
        if log[key] != inbox[key]:
            problems.append(f'{key} differs from the inbox in this checkout')
    expected = {i['position']: i for i in inbox['items']}
    for item in log['items']:
        found = expected.get(item['position'])
        if found is None:
            problems.append(f"row {item['position']} is listed in the log but does not wait in the inbox")
        elif found['result_sha256'] != item['result_sha256'] or found['item_sha256'] != item['item_sha256']:
            problems.append(f"row {item['position']} carries other hashes in the log than in the inbox")
    listed = {i['position'] for i in log['items']}
    for position in sorted(expected):
        if position not in listed:
            problems.append(f'row {position} waits in the inbox but is not listed in the log')
    try:
        policy = load_policy(root, policy_file)
    except InvariantError as exc:
        return problems + [f'action policy cannot be loaded from this checkout ({exc})']
    if log['policy'] != policy_reference(root, policy, policy_file):
        problems.append('policy differs from the action policy in this checkout')
    codes = {d['code'] for d in policy['decisions']}
    for entry in log['entries']:
        if entry['decision'] not in codes:
            problems.append(f"entry {entry['seq']} records a decision that is not on the action policy")
        if entry['decided_by']['role'] not in policy['roles']:
            problems.append(f"entry {entry['seq']} records a role that is not on the action policy")
    return problems
