"""The decision inbox: where a result that needs a person's judgement waits.

A results file is the rule's answer on every record. Some of those answers
are risk indicators that a person must look at; the rule has said what it
read and what it found, and what follows is a human decision. The inbox is
the list of those rows, built from a results file and the inbox policy: for
each rule, the policy names the states that wait and the question put to the
person. Every item carries the record's own keys, what the watcher read, what
the rule said, the row itself with its custody stamp, and a hash. The inbox
names the results file (by bytes), the policy (by bytes and by content) and
the roster the results were produced under, and is hashed into inbox_sha256.

Nothing here decides. A row is listed because its state is on the policy,
not because anything here weighed it; a row not listed is counted under its
state, never dropped and never called clean. Missing is not zero: a row the
rule did not run on cannot wait, and the inbox says how many such rows there
are. A result is a risk indicator, never an allegation; whether a procurement
should have happened stays with people.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from custody import HEX64, digest, file_sha256
from invariant_core import InvariantError
from watcher import SLUG

SCHEMA = 'sunlight.inbox.v1'
POLICY_SCHEMA = 'sunlight.inbox-policy.v1'
POLICY_FILE = 'config/inbox-policy.json'
POLICY_KEYS = {'schema', 'purpose', 'rules', 'policy_sha256'}
RULE_KEYS = {'rule_id', 'record', 'state_path', 'reason_path', 'waits'}
WAIT_KEYS = {'state', 'question'}
TOP_KEYS = {'schema', 'purpose', 'results_file', 'results_file_sha256', 'results_schema', 'rule_id',
            'rule_version_sha256', 'watcher_id', 'watcher_seal_sha256', 'roster', 'policy',
            'rows', 'rule_did_not_run', 'not_waiting', 'waiting', 'items', 'inbox_sha256'}
ITEM_KEYS = {'position', 'result_sha256', 'record', 'read', 'said', 'question', 'row', 'item_sha256'}
PURPOSE = ('Results that wait for a person. Each item is one result row whose state the inbox policy names, '
           'with the record it concerns, what the watcher read, what the rule said and the row itself. '
           'The system never decides; a person does. A row not listed is counted under its state, never dropped.')


def _text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise InvariantError(f'{what} required')
    return value


def _path(value, what):
    if not isinstance(value, list) or not value or not all(isinstance(p, str) and p for p in value) \
            or len(set(value)) != len(value):
        raise InvariantError(f'{what} required as a list of distinct field names')
    return value


def _rule(value) -> dict:
    if not isinstance(value, dict) or set(value) != RULE_KEYS:
        raise InvariantError('Policy rule with rule_id, record, state_path, reason_path and waits required')
    if not isinstance(value['rule_id'], str) or not SLUG.fullmatch(value['rule_id']):
        raise InvariantError('Policy rule_id required as a slug')
    _path(value['record'], 'Policy record fields')
    _path(value['state_path'], 'Policy state_path')
    _path(value['reason_path'], 'Policy reason_path')
    waits = value['waits']
    if not isinstance(waits, list):
        raise InvariantError('Policy waits required as a list')
    for wait in waits:
        if not isinstance(wait, dict) or set(wait) != WAIT_KEYS:
            raise InvariantError('Policy wait with state and question required')
        if not isinstance(wait['state'], str) or not wait['state'].isupper() or not wait['state'].replace('_', '').isalpha():
            raise InvariantError('Policy wait state required as an upper-case state name')
        _text(wait['question'], 'Policy wait question')
    states = [w['state'] for w in waits]
    if len(set(states)) != len(states):
        raise InvariantError('Policy wait states must be distinct')
    return value


def policy_digest(policy: dict) -> str:
    """The hash over everything in the policy but its own hash."""
    return digest({k: v for k, v in policy.items() if k != 'policy_sha256'})


def _policy(data) -> dict:
    """Every part of a policy but its hash, checked. Any missing, malformed or extra part is refused."""
    if not isinstance(data, dict) or data.get('schema') != POLICY_SCHEMA or set(data) != POLICY_KEYS:
        raise InvariantError('Typed inbox policy with purpose, rules and policy_sha256 required')
    _text(data['purpose'], 'Policy purpose')
    rules = data['rules']
    if not isinstance(rules, list) or not rules:
        raise InvariantError('At least one policy rule required')
    for rule in rules:
        _rule(rule)
    ids = [r['rule_id'] for r in rules]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise InvariantError('Policy rules must be distinct and ordered by rule_id')
    return data


def seal_policy(data) -> dict:
    """The policy with policy_sha256 recomputed from its other parts, which must all hold. Writes nothing."""
    checked = _policy(data)
    return {**{k: v for k, v in checked.items() if k != 'policy_sha256'}, 'policy_sha256': policy_digest(checked)}


def load_policy(root, path=POLICY_FILE) -> dict:
    """The policy file, checked part by part, its hash recomputed. Nothing is repaired."""
    file = Path(root) / path
    if not file.is_file():
        raise InvariantError('Inbox policy file required')
    data = _policy(json.loads(file.read_text()))
    if data['policy_sha256'] != policy_digest(data):
        raise InvariantError('policy_sha256 does not recompute from the policy')
    return data


def policy_for(policy: dict, rule_id: str) -> dict:
    """The policy rule for a rule id, or a refusal. A rule without a policy has no inbox."""
    for rule in policy['rules']:
        if rule['rule_id'] == rule_id:
            return rule
    raise InvariantError('Rule is not on the inbox policy; no inbox can be built for it')


def policy_reference(root, policy: dict, path=POLICY_FILE) -> dict:
    """The block an inbox carries: which policy, by file bytes and by content."""
    return {'policy_file': str(path), 'policy_file_sha256': file_sha256(Path(root) / path),
            'policy_sha256': policy['policy_sha256']}


def _read(record, path: list[str]):
    value = record
    for name in path:
        if not isinstance(value, dict) or name not in value:
            return None
        value = value[name]
    return value


def _relative(path, what) -> str:
    if not isinstance(path, str) or not path or path.startswith('/') or '..' in path.split('/') or '\\' in path:
        raise InvariantError(f'{what} required as a relative path')
    return path


def _results(results: dict) -> tuple[str, str, str, str, str]:
    """The parts of a results file an inbox names: schema, rule, watcher. Each is required."""
    if not isinstance(results, dict) or not isinstance(results.get('schema'), str) or not results['schema']:
        raise InvariantError('Typed results file required')
    rule = results.get('rule_version')
    if not isinstance(rule, dict) or not isinstance(rule.get('rule_id'), str) \
            or not HEX64.fullmatch(rule.get('rule_version_sha256', '') or ''):
        raise InvariantError('Results file without a rule version')
    sealed = results.get('watcher_seal')
    if not isinstance(sealed, dict) or not isinstance(sealed.get('watcher_id'), str) \
            or not HEX64.fullmatch(sealed.get('watcher_seal_sha256', '') or ''):
        raise InvariantError('Results file without a watcher seal')
    roster = results.get('roster')
    if not isinstance(roster, dict) or set(roster) != {'roster_file', 'roster_file_sha256', 'roster_sha256', 'watchers'}:
        raise InvariantError('Results file without a roster reference')
    if not isinstance(results.get('results'), list):
        raise InvariantError('Results file without result rows')
    return results['schema'], rule['rule_id'], rule['rule_version_sha256'], sealed['watcher_id'], sealed['watcher_seal_sha256']


def item_digest(item: dict) -> str:
    return digest({k: v for k, v in item.items() if k != 'item_sha256'})


def inbox_digest(inbox: dict) -> str:
    """The hash over everything in the inbox but its own hash."""
    return digest({k: v for k, v in inbox.items() if k != 'inbox_sha256'})


def _row_state(row, position: int, rule: dict) -> tuple[bool, str | None, str | None]:
    """Whether the rule ran on this row and, if so, its state and reason, read by the policy's paths."""
    if not isinstance(row, dict):
        raise InvariantError(f'row {position}: result row required')
    body = {k: v for k, v in row.items() if k != 'result_sha256'}
    if not HEX64.fullmatch(row.get('result_sha256', '') or '') or row['result_sha256'] != digest(body) \
            or not isinstance(row.get('custody'), dict) or not isinstance(row.get('watcher'), dict):
        raise InvariantError(f'row {position}: stamped result row with its watcher block required')
    if row['custody'].get('rule_id') != rule['rule_id']:
        raise InvariantError(f'row {position}: row was computed by another rule')
    selection = row['watcher'].get('selection')
    if not isinstance(selection, dict) or selection.get('outcome') not in ('SELECTED', 'NOT_SELECTED'):
        raise InvariantError(f'row {position}: watcher selection required')
    if selection['outcome'] != 'SELECTED':
        return False, None, None
    state = _read(row, rule['state_path'])
    if not isinstance(state, str) or not state:
        raise InvariantError(f'row {position}: rule state required at the policy path')
    reason = _read(row, rule['reason_path'])
    if not isinstance(reason, str) or not reason:
        raise InvariantError(f'row {position}: rule reason required at the policy path')
    return True, state, reason


def _item(row: dict, position: int, state: str, reason: str, rule: dict, question: str) -> dict:
    record = {}
    for name in rule['record']:
        if name not in row:
            raise InvariantError(f'row {position}: record field {name} required')
        record[name] = row[name]
    body = {'position': position, 'result_sha256': row['result_sha256'], 'record': record,
            'read': row['watcher'], 'said': {'state': state, 'reason': reason}, 'question': question, 'row': row}
    return {**body, 'item_sha256': item_digest(body)}


def build_inbox(results: dict, *, results_file: str, results_bytes: bytes, policy: dict, root, policy_file=POLICY_FILE) -> dict:
    """The inbox for one results file under one policy. Builds in memory and returns; writes nothing.

    Rows are walked in the order the results file carries them. A row whose
    stamp does not recompute, whose rule differs from the file's, or whose
    state cannot be read at the policy path is refused: the inbox never lists
    a row it cannot vouch for, and never guesses a state.
    """
    schema, rule_id, rule_version_sha256, watcher_id, watcher_seal_sha256 = _results(results)
    rule = policy_for(policy, rule_id)
    questions = {w['state']: w['question'] for w in rule['waits']}
    items, not_waiting, did_not_run = [], {}, 0
    for position, row in enumerate(results['results']):
        ran, state, reason = _row_state(row, position, rule)
        if not ran:
            did_not_run += 1
        elif state in questions:
            items.append(_item(row, position, state, reason, rule, questions[state]))
        else:
            not_waiting[state] = not_waiting.get(state, 0) + 1
    body = {'schema': SCHEMA, 'purpose': PURPOSE,
            'results_file': _relative(results_file, 'Results file'),
            'results_file_sha256': hashlib.sha256(results_bytes).hexdigest(),
            'results_schema': schema, 'rule_id': rule_id, 'rule_version_sha256': rule_version_sha256,
            'watcher_id': watcher_id, 'watcher_seal_sha256': watcher_seal_sha256,
            'roster': results['roster'], 'policy': policy_reference(root, policy, policy_file),
            'rows': len(results['results']), 'rule_did_not_run': did_not_run,
            'not_waiting': {k: not_waiting[k] for k in sorted(not_waiting)},
            'waiting': len(items), 'items': items}
    return {**body, 'inbox_sha256': inbox_digest(body)}


def load_inbox(path) -> dict:
    """An inbox file, checked part by part. Any missing, malformed or extra part is refused.

    This reads the inbox only. Whether it is what the results file and the
    policy in a checkout build is check_inbox's question.
    """
    file = Path(path)
    if not file.is_file():
        raise InvariantError('Inbox file required')
    data = json.loads(file.read_text())
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or set(data) != TOP_KEYS:
        raise InvariantError('Typed inbox with every part required')
    _text(data['purpose'], 'Inbox purpose')
    _relative(data['results_file'], 'Results file')
    for key in ('results_file_sha256', 'rule_version_sha256', 'watcher_seal_sha256'):
        if not isinstance(data[key], str) or not HEX64.fullmatch(data[key]):
            raise InvariantError(f'Inbox {key} required')
    _text(data['results_schema'], 'Inbox results_schema')
    for key in ('rule_id', 'watcher_id'):
        if not isinstance(data[key], str) or not SLUG.fullmatch(data[key]):
            raise InvariantError(f'Inbox {key} required as a slug')
    if not isinstance(data['roster'], dict) or set(data['roster']) != {'roster_file', 'roster_file_sha256', 'roster_sha256', 'watchers'}:
        raise InvariantError('Inbox roster reference required')
    policy = data['policy']
    if not isinstance(policy, dict) or set(policy) != {'policy_file', 'policy_file_sha256', 'policy_sha256'} \
            or not all(isinstance(policy[k], str) and HEX64.fullmatch(policy[k]) for k in ('policy_file_sha256', 'policy_sha256')):
        raise InvariantError('Inbox policy reference required')
    _relative(policy['policy_file'], 'Policy file')
    for key in ('rows', 'rule_did_not_run', 'waiting'):
        if not isinstance(data[key], int) or isinstance(data[key], bool) or data[key] < 0:
            raise InvariantError(f'Inbox {key} required as a count')
    if not isinstance(data['not_waiting'], dict) \
            or any(not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool) or v < 1 for k, v in data['not_waiting'].items()) \
            or list(data['not_waiting']) != sorted(data['not_waiting']):
        raise InvariantError('Inbox not_waiting required as counts by state, ordered by state')
    items = data['items']
    if not isinstance(items, list) or len(items) != data['waiting']:
        raise InvariantError('Inbox items required, one per waiting result')
    if data['waiting'] + data['rule_did_not_run'] + sum(data['not_waiting'].values()) != data['rows']:
        raise InvariantError('Inbox counts do not add up to the rows')
    positions = []
    for item in items:
        if not isinstance(item, dict) or set(item) != ITEM_KEYS:
            raise InvariantError('Inbox item with every part required')
        if not isinstance(item['position'], int) or isinstance(item['position'], bool) or item['position'] < 0:
            raise InvariantError('Inbox item position required')
        if not isinstance(item['result_sha256'], str) or not HEX64.fullmatch(item['result_sha256']):
            raise InvariantError('Inbox item result_sha256 required')
        if not isinstance(item['record'], dict) or not item['record']:
            raise InvariantError('Inbox item record required')
        if not isinstance(item['said'], dict) or set(item['said']) != {'state', 'reason'}:
            raise InvariantError('Inbox item said with state and reason required')
        _text(item['question'], 'Inbox item question')
        if not isinstance(item['row'], dict) or item['row'].get('result_sha256') != item['result_sha256'] \
                or item['row'].get('watcher') != item['read']:
            raise InvariantError('Inbox item row must carry the result_sha256 and watcher block the item names')
        if item['item_sha256'] != item_digest(item):
            raise InvariantError('Inbox item_sha256 does not recompute')
        positions.append(item['position'])
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise InvariantError('Inbox items must be distinct and in results order')
    if data['inbox_sha256'] != inbox_digest(data):
        raise InvariantError('inbox_sha256 does not recompute from the inbox')
    return data


def check_inbox(inbox: dict, root, policy_file=POLICY_FILE) -> list[str]:
    """Problems with a loaded inbox against the results file and the policy in this checkout.

    The results file the inbox names is read from the checkout and its bytes
    compared; the inbox is rebuilt from that file and the checkout's policy
    and compared part by part. Empty means the inbox is exactly what this
    checkout builds.
    """
    root = Path(root)
    problems = []
    results_path = root / inbox['results_file']
    if not results_path.is_file():
        return ['results file the inbox names is not in this checkout']
    results_bytes = results_path.read_bytes()
    try:
        policy = load_policy(root, policy_file)
    except InvariantError as exc:
        return [f'inbox policy cannot be loaded from this checkout ({exc})']
    try:
        expected = build_inbox(json.loads(results_bytes), results_file=inbox['results_file'], results_bytes=results_bytes,
                               policy=policy, root=root, policy_file=policy_file)
    except InvariantError as exc:
        return [f'inbox cannot be built from this checkout ({exc})']
    for key in sorted(TOP_KEYS - {'items', 'inbox_sha256'}):
        if inbox[key] != expected[key]:
            problems.append(f'{key} differs from the inbox built from this checkout')
    found = {i['position']: i for i in inbox['items']}
    for item in expected['items']:
        if item['position'] not in found:
            problems.append(f"row {item['position']} waits under the policy but is not in the inbox")
        elif found[item['position']] != item:
            problems.append(f"item at row {item['position']} differs from the one built from this checkout")
    built = {i['position'] for i in expected['items']}
    for position in sorted(found):
        if position not in built:
            problems.append(f'item at row {position} does not wait under the policy')
    if inbox['inbox_sha256'] != expected['inbox_sha256']:
        problems.append('inbox_sha256 differs from the inbox built from this checkout')
    return problems
