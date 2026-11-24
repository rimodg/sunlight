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


def page_reference(capture_file, page, source_sha256, projection_sha256) -> dict:
    """A page of a committed capture file a result was computed from. Every part is required.

    `capture_file` is a relative path, recorded as given. `source_sha256` is
    the hash of the page's original response bytes (not retained; reported,
    not reverified). `projection_sha256` is the hash of the protected
    projection kept in the capture file, which a verifier recomputes.
    """
    if not isinstance(capture_file, str) or not capture_file or capture_file.startswith('/') \
            or '..' in capture_file.split('/') or '\\' in capture_file:
        raise InvariantError('Source capture file required as a relative path')
    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        raise InvariantError('Source capture page required')
    if not isinstance(source_sha256, str) or not HEX64.fullmatch(source_sha256):
        raise InvariantError('Source page hash required')
    if not isinstance(projection_sha256, str) or not HEX64.fullmatch(projection_sha256):
        raise InvariantError('Source projection hash required')
    return {'capture': 'file', 'capture_file': capture_file, 'page': page,
            'source_sha256': source_sha256, 'projection_sha256': projection_sha256}


def any_source_reference(source) -> dict:
    """A journal capture or a capture-file page, by the parts given. Nothing else."""
    if not isinstance(source, dict):
        raise InvariantError('Source reference required')
    if 'capture_seq' in source or 'capture_hash' in source:
        return source_reference(source.get('capture_seq'), source.get('capture_hash'))
    if 'capture_file' in source or 'page' in source:
        return page_reference(source.get('capture_file'), source.get('page'),
                              source.get('source_sha256'), source.get('projection_sha256'))
    raise InvariantError('Source reference required')


def stamp(row: dict, *, source: dict, rule: dict) -> dict:
    """Return the row with its custody block and a hash over everything in it."""
    if not isinstance(row, dict) or 'custody' in row or 'result_sha256' in row:
        raise InvariantError('Unstamped result row required')
    if not isinstance(rule, dict) or rule.get('schema') != SCHEMA or not HEX64.fullmatch(rule.get('rule_version_sha256', '')):
        raise InvariantError('Rule version required')
    custody = {'source': any_source_reference(source),
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
        if any_source_reference(custody.get('source')) != custody.get('source'):
            problems.append('source reference carries parts that are not its own')
    except InvariantError:
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

    With `pairs`, every row's cited capture must equal the capture the pair
    export cites for the same (ocid, award_id, award_date, tender_end_date).
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
    for index, row in enumerate(results.get('results', [])):
        for problem in check_row(row, rule=rule):
            problems.append(f'row {index}: {problem}')
        if expected is not None:
            key = (row.get('ocid'), row.get('award_id'), row.get('award_date'), row.get('tender_end_date'))
            cited = row.get('custody', {}).get('source', {})
            if expected.get(key) != (cited.get('capture_seq'), cited.get('capture_hash')):
                problems.append(f'row {index}: cited capture differs from the pair export')
    return problems


def check_journal(results: dict, journal_path) -> list[str]:
    """Problems linking cited captures to a watch journal, opened read-only.

    For each distinct cited capture, the journal row at that sequence must
    carry the same chain hash and be a capture. The capture's original
    response sha256 is the end of the chain; the original bytes are not
    retained, so that hash is reported, not reverified.
    """
    import sqlite3
    problems = []
    uri = Path(journal_path).resolve().as_uri() + '?mode=ro'
    db = sqlite3.connect(uri, uri=True)
    try:
        cited = sorted({(r['custody']['source']['capture_seq'], r['custody']['source']['capture_hash'])
                        for r in results.get('results', []) if isinstance(r.get('custody'), dict)})
        for seq, chain_hash in cited:
            row = db.execute('SELECT kind, hash, payload FROM watch_events WHERE seq=?', (seq,)).fetchone()
            if row is None:
                problems.append(f'capture seq {seq}: not in journal')
                continue
            kind, found_hash, payload = row
            if kind != 'capture':
                problems.append(f'capture seq {seq}: journal event is {kind}, not capture')
            if found_hash != chain_hash:
                problems.append(f'capture seq {seq}: journal hash differs from the cited capture hash')
            source_sha256 = json.loads(payload).get('sha256')
            if not isinstance(source_sha256, str) or not HEX64.fullmatch(source_sha256):
                problems.append(f'capture seq {seq}: capture carries no original response sha256')
    finally:
        db.close()
    return problems


def check_capture_file(results: dict, capture: dict, *, capture_file: str, projection_bytes) -> list[str]:
    """Problems linking rows that cite capture-file pages to the capture file itself.

    Every row must cite `capture_file`, a page that exists in `capture`, that
    page's `source_sha256` and `projection_sha256`, and the row's own
    `source_sha256`, `source_url` and `page` must agree with the citation.
    The projection hash is recomputed from the page's projection with
    `projection_bytes` (the same canonical form the capture used). The
    original response bytes are not retained, so `source_sha256` is the end
    of the chain: reported, not reverified.
    """
    problems = []
    pages = capture.get('pages') if isinstance(capture, dict) else None
    if not isinstance(pages, list):
        return ['capture file carries no pages']
    recomputed = {}
    for index, row in enumerate(results.get('results', [])):
        cited = row.get('custody', {}).get('source', {}) if isinstance(row, dict) else {}
        if cited.get('capture') != 'file':
            problems.append(f'row {index}: source is not a capture-file page')
            continue
        if cited.get('capture_file') != capture_file:
            problems.append(f'row {index}: cites another capture file')
        page = cited.get('page')
        if not isinstance(page, int) or page < 0 or page >= len(pages) or 'projection' not in pages[page]:
            problems.append(f'row {index}: cited page is not in the capture file')
            continue
        found = pages[page]
        if found.get('source_sha256') != cited.get('source_sha256'):
            problems.append(f'row {index}: capture page source_sha256 differs from the cited one')
        if page not in recomputed:
            recomputed[page] = hashlib.sha256(projection_bytes(found['projection'])).hexdigest()
        if found.get('projection_sha256') != cited.get('projection_sha256'):
            problems.append(f'row {index}: capture page projection_sha256 differs from the cited one')
        if recomputed[page] != cited.get('projection_sha256'):
            problems.append(f'row {index}: cited projection_sha256 does not recompute from the capture file')
        if row.get('source_sha256') != cited.get('source_sha256'):
            problems.append(f'row {index}: row source_sha256 differs from the cited page')
        if row.get('source_url') != found.get('url'):
            problems.append(f'row {index}: row source_url differs from the cited page')
        if row.get('page') != page:
            problems.append(f'row {index}: row page differs from the cited page')
    return problems
