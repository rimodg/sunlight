"""Chain of custody for results.

Every stamped result names the source it was computed from (the journal
capture it cites) and the exact rule that computed it (the rule module bytes,
the profile bytes and the sources the profile cites). A result hash binds the
three together. Anyone with the repository and the journal can recompute every
hash; nothing here needs trust.

Hashes prove content equality, not publisher authenticity. A matching hash
says the same bytes were used, never that a source is genuine or a result is
an allegation. Missing is not zero: a result without a cited source is refused,
never stamped with a placeholder.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from invariant_core import InvariantError

SCHEMA = 'sunlight.custody.v1'
HEX64 = re.compile(r'[0-9a-f]{64}')


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cited_sources(value) -> list[dict]:
    """Every {source, locator, sha256} citation inside a profile, deduplicated and sorted."""
    found = {}
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if {'source', 'locator', 'sha256'} <= set(item) and isinstance(item['sha256'], str):
                key = (item['source'], item['locator'], item['sha256'])
                found[key] = {'source': item['source'], 'locator': item['locator'], 'sha256': item['sha256']}
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return [found[k] for k in sorted(found)]


def rule_version(*, rule_id: str, root, module: str, profile: str) -> dict:
    """The exact rule: module bytes, profile bytes and the sources the profile cites.

    `module` and `profile` are repository-relative paths; they are recorded as
    given so a verifier recomputes from the same files. Any change to the rule
    code, its profile or a cited source changes rule_version_sha256.
    """
    root = Path(root)
    module_path, profile_path = root / module, root / profile
    if not module_path.is_file() or not profile_path.is_file():
        raise InvariantError('Rule module and profile files required')
    profile_data = json.loads(profile_path.read_text())
    if not isinstance(profile_data, dict) or not isinstance(profile_data.get('schema'), str):
        raise InvariantError('Typed profile required')
    sources = cited_sources(profile_data)
    if not sources:
        raise InvariantError('Profile cites no source')
    for citation in sources:
        if not HEX64.fullmatch(citation['sha256']):
            raise InvariantError('Cited source without a sha256')
    version = {'schema': SCHEMA, 'rule_id': rule_id,
               'rule_module': module, 'rule_module_sha256': file_sha256(module_path),
               'profile': profile, 'profile_schema': profile_data['schema'],
               'profile_sha256': file_sha256(profile_path),
               'cited_sources': sources}
    return {**version, 'rule_version_sha256': digest(version)}


def source_reference(capture_seq, capture_hash) -> dict:
    """The journal capture a result was computed from. Both parts are required."""
    if not isinstance(capture_seq, int) or isinstance(capture_seq, bool) or capture_seq < 1:
        raise InvariantError('Source capture sequence required')
    if not isinstance(capture_hash, str) or not HEX64.fullmatch(capture_hash):
        raise InvariantError('Source capture hash required')
    return {'journal': 'watch', 'capture_seq': capture_seq, 'capture_hash': capture_hash}


def stamp(row: dict, *, source: dict, rule: dict) -> dict:
    """Return the row with its custody block and a hash over everything in it."""
    if not isinstance(row, dict) or 'custody' in row or 'result_sha256' in row:
        raise InvariantError('Unstamped result row required')
    if not isinstance(rule, dict) or rule.get('schema') != SCHEMA or not HEX64.fullmatch(rule.get('rule_version_sha256', '')):
        raise InvariantError('Rule version required')
    custody = {'source': source_reference(source['capture_seq'], source['capture_hash']),
               'rule_id': rule['rule_id'], 'rule_version_sha256': rule['rule_version_sha256']}
    stamped = {**row, 'custody': custody}
    return {**stamped, 'result_sha256': digest(stamped)}


def check_row(row: dict, *, rule: dict) -> list[str]:
    """Problems with one stamped row; empty means the row recomputes exactly."""
    problems = []
    custody = row.get('custody') if isinstance(row, dict) else None
    if not isinstance(custody, dict):
        return ['custody block missing']
    try:
        source_reference(custody.get('source', {}).get('capture_seq'), custody.get('source', {}).get('capture_hash'))
    except (InvariantError, AttributeError):
        problems.append('source reference missing or malformed')
    if custody.get('rule_id') != rule.get('rule_id'):
        problems.append('rule_id differs')
    if custody.get('rule_version_sha256') != rule.get('rule_version_sha256'):
        problems.append('rule_version_sha256 differs from the rule in this repository')
    body = {k: v for k, v in row.items() if k != 'result_sha256'}
    if row.get('result_sha256') != digest(body):
        problems.append('result_sha256 does not recompute')
    return problems


def check_results(results: dict, *, rule: dict, pairs: dict | None = None, pairs_bytes: bytes | None = None) -> list[str]:
    """Problems with a results file as a whole. Empty means every link holds.

    With `pairs`, every distinct exported pair (ocid, award_id, award_date,
    tender_end_date) must appear as exactly one row, and that row's cited
    capture must equal the capture the pair export cites for it. A pair
    with no row, or a pair with two rows, is a problem: a duplicated row
    standing in for a dropped one keeps the count and is still refused.
    With `pairs_bytes`, the file-level input_sha256 must match those bytes.
    """
    problems = []
    if results.get('rule_version') != rule:
        problems.append('file-level rule_version differs from the rule in this repository')
    if pairs_bytes is not None and results.get('input_sha256') != hashlib.sha256(pairs_bytes).hexdigest():
        problems.append('input_sha256 does not match the pair export bytes')
    expected = None
    if pairs is not None:
        expected = {(p['ocid'], p['award_id'], p['award_date'], p['tender_end_date']):
                    (p.get('capture_seq'), p.get('capture_hash')) for p in pairs['pairs']}
        if len(expected) != len(results.get('results', [])):
            problems.append('row count differs from the number of distinct pairs')
    seen = {}
    for index, row in enumerate(results.get('results', [])):
        for problem in check_row(row, rule=rule):
            problems.append(f'row {index}: {problem}')
        if expected is not None:
            key = (row.get('ocid'), row.get('award_id'), row.get('award_date'), row.get('tender_end_date'))
            cited = row.get('custody', {}).get('source', {})
            if expected.get(key) != (cited.get('capture_seq'), cited.get('capture_hash')):
                problems.append(f'row {index}: cited capture differs from the pair export')
            if key in seen:
                problems.append(f'row {index}: duplicates row {seen[key]} (same pair)')
            else:
                seen[key] = index
    if expected is not None:
        for key in expected:
            if key not in seen:
                problems.append(f'pair {list(key)}: no row')
    return problems


def check_journal(results: dict, journal_path) -> list[str]:
    """Problems linking cited captures to a watch journal, opened read-only.

    For each distinct cited capture, the journal row at that sequence must
    be a capture, must carry the same chain hash, and that hash must
    recompute from the row's own parts the way code/watch_journal.py writes
    them: event id = digest({kind, at, payload}) and chain hash =
    digest({id, previous}). So a payload changed under an unchanged stored
    hash is refused here, not only by the journal's own full verify. The
    capture's original response sha256 is the end of the chain; the
    original bytes are not retained, so that hash is reported, not
    reverified.
    """
    import sqlite3
    problems = []
    uri = Path(journal_path).resolve().as_uri() + '?mode=ro'
    db = sqlite3.connect(uri, uri=True)
    try:
        cited = sorted({(r['custody']['source']['capture_seq'], r['custody']['source']['capture_hash'])
                        for r in results.get('results', []) if isinstance(r.get('custody'), dict)})
        for seq, chain_hash in cited:
            row = db.execute('SELECT id, kind, at, payload, previous, hash FROM watch_events WHERE seq=?',
                             (seq,)).fetchone()
            if row is None:
                problems.append(f'capture seq {seq}: not in journal')
                continue
            event_id, kind, at, payload, previous, found_hash = row
            if kind != 'capture':
                problems.append(f'capture seq {seq}: journal event is {kind}, not capture')
            if found_hash != chain_hash:
                problems.append(f'capture seq {seq}: journal hash differs from the cited capture hash')
            try:
                loaded = json.loads(payload)
            except (TypeError, ValueError):
                loaded = None
            if not isinstance(loaded, dict):
                problems.append(f'capture seq {seq}: capture payload is not a JSON object')
                continue
            expected_id = digest({'kind': kind, 'at': at, 'payload': loaded})
            if event_id != expected_id or found_hash != digest({'id': expected_id, 'previous': previous}):
                problems.append(f'capture seq {seq}: journal hash does not recompute from the event (payload, time or kind changed)')
            source_sha256 = loaded.get('sha256')
            if not isinstance(source_sha256, str) or not HEX64.fullmatch(source_sha256):
                problems.append(f'capture seq {seq}: capture carries no original response sha256')
    finally:
        db.close()
    return problems
