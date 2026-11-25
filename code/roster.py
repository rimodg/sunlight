"""The roster: which watchers exist, each with its seal, as one hashed list.

A watcher is a sealed lens (see code/watcher.py). The roster is the list of
the watchers that may run, each named by its file, its watcher id, its rule
id, the hash of its file bytes, its rule version and its seal. The list is
hashed into roster_sha256. The measure scripts read the roster before they
run a watcher: a watcher that is not on the roster, or whose seal recomputed
from the checkout differs from the seal the roster pins, does not run. Every
results file names the roster it was produced under, so anyone can prove not
only which lens was used on each record but which lenses existed at all.

Nothing here infers, scores or judges. The roster is a list of files and
hashes, read and compared; a mismatch is refused, never repaired. Missing is
not zero: a watcher without a roster entry has no standing, and the roster
does not supply one.
"""
from __future__ import annotations

import json
from pathlib import Path

from custody import HEX64, digest, file_sha256
from invariant_core import InvariantError
from watcher import SLUG, seal

SCHEMA = 'sunlight.roster.v1'
ROSTER_FILE = 'config/roster.json'
WATCHERS_DIR = 'config/watchers'
TOP_KEYS = {'schema', 'purpose', 'watchers', 'roster_sha256'}
ENTRY_KEYS = ('watcher_id', 'file', 'rule_id', 'watcher_sha256', 'rule_version_sha256', 'watcher_seal_sha256')


def _entry(value) -> dict:
    if not isinstance(value, dict) or set(value) != set(ENTRY_KEYS):
        raise InvariantError('Roster entry with watcher_id, file, rule_id, watcher_sha256, rule_version_sha256 and watcher_seal_sha256 required')
    if not isinstance(value['watcher_id'], str) or not SLUG.fullmatch(value['watcher_id']):
        raise InvariantError('Roster entry watcher_id required as a slug')
    if not isinstance(value['rule_id'], str) or not SLUG.fullmatch(value['rule_id']):
        raise InvariantError('Roster entry rule_id required as a slug')
    file = value['file']
    if not isinstance(file, str) or not file.startswith(WATCHERS_DIR + '/') or not file.endswith('.json') \
            or '..' in file.split('/') or '\\' in file or file.count('/') != WATCHERS_DIR.count('/') + 1:
        raise InvariantError('Roster entry file required as a watcher file under config/watchers')
    for key in ('watcher_sha256', 'rule_version_sha256', 'watcher_seal_sha256'):
        if not isinstance(value[key], str) or not HEX64.fullmatch(value[key]):
            raise InvariantError(f'Roster entry {key} required')
    return value


def roster_digest(roster: dict) -> str:
    """The hash over everything in the roster but its own hash."""
    return digest({k: v for k, v in roster.items() if k != 'roster_sha256'})


def load_roster(root, path=ROSTER_FILE) -> dict:
    """The roster file, checked part by part. Any missing, malformed or extra part is refused.

    This reads the roster only. Whether each entry still matches the watcher
    sealed from the checkout is check_roster's question.
    """
    file = Path(root) / path
    if not file.is_file():
        raise InvariantError('Roster file required')
    data = json.loads(file.read_text())
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or set(data) != TOP_KEYS:
        raise InvariantError('Typed roster with purpose, watchers and roster_sha256 required')
    if not isinstance(data['purpose'], str) or not data['purpose'].strip():
        raise InvariantError('Roster purpose required')
    watchers = data['watchers']
    if not isinstance(watchers, list) or not watchers:
        raise InvariantError('At least one watcher on the roster required')
    for entry in watchers:
        _entry(entry)
    ids = [e['watcher_id'] for e in watchers]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise InvariantError('Roster entries must be distinct and ordered by watcher_id')
    if len({e['file'] for e in watchers}) != len(watchers):
        raise InvariantError('Roster entries must name distinct files')
    if data['roster_sha256'] != roster_digest(data):
        raise InvariantError('roster_sha256 does not recompute from the roster')
    return data


def entry_for(root, watcher_file: str) -> dict:
    """The roster entry a watcher file would carry, sealed from this checkout."""
    sealed = seal(root, watcher_file)
    return {'watcher_id': sealed['watcher_id'], 'file': watcher_file, 'rule_id': sealed['rule_version']['rule_id'],
            'watcher_sha256': sealed['watcher_sha256'],
            'rule_version_sha256': sealed['rule_version']['rule_version_sha256'],
            'watcher_seal_sha256': sealed['watcher_seal_sha256']}


def build_roster(root, purpose: str, files: list[str] | None = None) -> dict:
    """A roster over the given watcher files (default: every .json under config/watchers), sealed now.

    Builds in memory and returns; writes nothing. Refuses two files with one watcher id.
    """
    root = Path(root)
    if files is None:
        files = sorted(f'{WATCHERS_DIR}/{p.name}' for p in (root / WATCHERS_DIR).glob('*.json'))
    entries = sorted((entry_for(root, f) for f in files), key=lambda e: e['watcher_id'])
    if len({e['watcher_id'] for e in entries}) != len(entries):
        raise InvariantError('Two watcher files carry one watcher_id')
    body = {'schema': SCHEMA, 'purpose': purpose, 'watchers': entries}
    return {**body, 'roster_sha256': roster_digest(body)}


def check_roster(root, roster: dict) -> list[str]:
    """Problems with a loaded roster against the watchers sealed from this checkout.

    Every entry must recompute part by part, and every watcher file under
    config/watchers must be on the roster (a file off the roster does not run,
    and the roster says so rather than leaving it unseen).
    """
    root = Path(root)
    problems = []
    for entry in roster['watchers']:
        try:
            expected = entry_for(root, entry['file'])
        except InvariantError as exc:
            problems.append(f"{entry['file']}: watcher cannot be sealed from this checkout ({exc})")
            continue
        for key in ENTRY_KEYS:
            if entry[key] != expected[key]:
                problems.append(f"{entry['file']}: {key} differs from the watcher sealed from this checkout")
    on_roster = {e['file'] for e in roster['watchers']}
    for path in sorted((root / WATCHERS_DIR).glob('*.json')):
        rel = f'{WATCHERS_DIR}/{path.name}'
        if rel not in on_roster:
            problems.append(f'{rel}: watcher file is not on the roster')
    return problems


def enrol(roster: dict, sealed: dict, watcher_file: str) -> dict:
    """The roster entry for a sealed watcher, or a refusal. A watcher not on the roster does not run."""
    for entry in roster['watchers']:
        if entry['file'] == watcher_file:
            if entry['watcher_id'] != sealed.get('watcher_id') \
                    or entry['watcher_sha256'] != sealed.get('watcher_sha256') \
                    or entry['rule_id'] != sealed.get('rule_version', {}).get('rule_id') \
                    or entry['rule_version_sha256'] != sealed.get('rule_version', {}).get('rule_version_sha256') \
                    or entry['watcher_seal_sha256'] != sealed.get('watcher_seal_sha256'):
                raise InvariantError('Watcher differs from its roster entry; it does not run')
            return entry
    raise InvariantError('Watcher is not on the roster; it does not run')


def reference(root, roster: dict, path=ROSTER_FILE) -> dict:
    """The block a results file carries: which roster, by file bytes and by content."""
    return {'roster_file': str(path), 'roster_file_sha256': file_sha256(Path(root) / path),
            'roster_sha256': roster['roster_sha256'], 'watchers': len(roster['watchers'])}


def check_reference(results: dict, root, roster: dict, path=ROSTER_FILE) -> list[str]:
    """Problems with a results file's roster reference and the standing of the watcher it names."""
    problems = []
    if results.get('roster') != reference(root, roster, path):
        problems.append('file-level roster reference differs from the roster in this repository')
    sealed = results.get('watcher_seal')
    if not isinstance(sealed, dict):
        return problems + ['file-level watcher_seal missing']
    try:
        enrol(roster, sealed, sealed.get('watcher_file'))
    except InvariantError as exc:
        problems.append(str(exc))
    return problems
