"""Sealed watchers: a fixed lens, hashed, applied to every record.

A watcher is one rule plus the context it reads before applying that rule:
a fixed list of facts read from the record by path, each defined by a cited
source, and a selection table saying which facts select the rule. The watcher
file, the rule module, the rule profile and every cited source are hashed
together into one seal. Every result row then carries the facts that were
read, the selection row that matched and the seal, so anyone can prove which
lens was used on which record and why.

Reading a fact is reading a field. Nothing here infers, scores or judges:
when a fact is missing the row says so, and when no selection row matches the
record is NOT_SELECTED with the watcher's own reason. Missing is not zero.
A result is a risk indicator, never an allegation; whether a procurement
should have happened is a human judgement and stays one.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from custody import HEX64, cited_sources, digest, file_sha256, rule_version
from invariant_core import InvariantError

SCHEMA = 'sunlight.watcher.v1'
SEAL_SCHEMA = 'sunlight.watcher-seal.v1'
SLUG = re.compile(r'[a-z][a-z0-9_]{0,63}')
KINDS = {'code', 'classification', 'boolean', 'text'}
TOP_KEYS = {'schema', 'watcher_id', 'purpose', 'record', 'rule', 'facts', 'selection', 'otherwise'}
FACT_KEYS = {'fact', 'path', 'kind', 'codes', 'codes_source', 'classification_source', 'publisher', 'definition'}
ROW_KEYS = {'when', 'apply', 'note'}


def _text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise InvariantError(f'{what} required')
    return value


def _citation(value, what):
    if not isinstance(value, dict) or set(value) != {'source', 'locator', 'sha256'}:
        raise InvariantError(f'{what} citation with source, locator and sha256 required')
    _text(value['source'], what + ' source'), _text(value['locator'], what + ' locator')
    if not isinstance(value['sha256'], str) or not HEX64.fullmatch(value['sha256']):
        raise InvariantError(f'{what} citation without a sha256')
    return value


def _fact(value) -> dict:
    if not isinstance(value, dict) or not {'fact', 'path', 'kind', 'publisher', 'definition'} <= set(value) \
            or not set(value) <= FACT_KEYS:
        raise InvariantError('Fact with fact, path, kind, publisher and definition required')
    if not isinstance(value['fact'], str) or not SLUG.fullmatch(value['fact']):
        raise InvariantError('Fact name required as a slug')
    if not isinstance(value['path'], list) or not value['path'] or not all(isinstance(p, str) and p for p in value['path']):
        raise InvariantError('Fact path required as a list of field names')
    if value['kind'] not in KINDS:
        raise InvariantError('Fact kind required')
    _text(value['publisher'], 'Fact publisher')
    definition = value['definition']
    if not isinstance(definition, dict) or set(definition) != {'text', 'source'}:
        raise InvariantError('Fact definition with text and source required')
    _text(definition['text'], 'Fact definition text')
    _citation(definition['source'], 'Fact definition')
    if value['kind'] == 'code':
        codes = value.get('codes')
        if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c for c in codes) or len(set(codes)) != len(codes):
            raise InvariantError('Code fact requires a non-empty list of distinct codes')
        _citation(value.get('codes_source'), 'Code fact codelist')
    elif 'codes' in value or 'codes_source' in value:
        raise InvariantError('Only a code fact carries codes')
    if value['kind'] == 'classification':
        _citation(value.get('classification_source'), 'Classification fact')
    elif 'classification_source' in value:
        raise InvariantError('Only a classification fact carries a classification source')
    return value


def _spec(spec, fact: dict):
    if spec == 'missing':
        return spec
    if isinstance(spec, dict) and set(spec) == {'in'}:
        if fact['kind'] != 'code' or not isinstance(spec['in'], list) or not spec['in'] \
                or not all(c in fact['codes'] for c in spec['in']):
            raise InvariantError('"in" selects codes of a code fact only')
        return spec
    if isinstance(spec, dict) and set(spec) == {'equals'}:
        return spec
    raise InvariantError('Selection condition must be "missing", {"in": codes} or {"equals": value}')


def load_watcher(root, path) -> dict:
    """The watcher file, checked part by part. Any missing or extra part is refused."""
    root = Path(root)
    file = root / path
    if not file.is_file():
        raise InvariantError('Watcher file required')
    data = json.loads(file.read_text())
    if not isinstance(data, dict) or data.get('schema') != SCHEMA or not set(data) <= TOP_KEYS \
            or not {'schema', 'watcher_id', 'rule', 'facts', 'selection', 'otherwise'} <= set(data):
        raise InvariantError('Typed watcher with watcher_id, rule, facts, selection and otherwise required')
    if not isinstance(data['watcher_id'], str) or not SLUG.fullmatch(data['watcher_id']):
        raise InvariantError('watcher_id required as a slug')
    rule = data['rule']
    if not isinstance(rule, dict) or set(rule) != {'rule_id', 'module', 'profile'} \
            or not all(isinstance(rule[k], str) and rule[k] for k in rule):
        raise InvariantError('Rule with rule_id, module and profile required')
    facts = data['facts']
    if not isinstance(facts, list) or not facts:
        raise InvariantError('At least one fact required')
    by_name = {}
    for fact in facts:
        _fact(fact)
        if fact['fact'] in by_name:
            raise InvariantError('Fact names must be distinct')
        by_name[fact['fact']] = fact
    selection = data['selection']
    if not isinstance(selection, list) or not selection:
        raise InvariantError('At least one selection row required')
    for row in selection:
        if not isinstance(row, dict) or not {'when', 'apply'} <= set(row) or not set(row) <= ROW_KEYS:
            raise InvariantError('Selection row with when and apply required')
        if not isinstance(row['when'], dict) or not row['when']:
            raise InvariantError('Selection row must name at least one fact')
        for name, spec in row['when'].items():
            if name not in by_name:
                raise InvariantError('Selection row names a fact the watcher does not read')
            _spec(spec, by_name[name])
        if not isinstance(row['apply'], list) or any(r != rule['rule_id'] for r in row['apply']) \
                or len(row['apply']) != len(set(row['apply'])):
            raise InvariantError('Selection row may apply only the rule this watcher carries')
    otherwise = data['otherwise']
    if not isinstance(otherwise, dict) or set(otherwise) != {'outcome', 'reason'} or otherwise['outcome'] != 'NOT_SELECTED':
        raise InvariantError('otherwise with outcome NOT_SELECTED and a reason required')
    _text(otherwise['reason'], 'otherwise reason')
    return data


def seal(root, path) -> dict:
    """The seal: watcher file bytes, the exact rule version and every fact source, hashed together."""
    root = Path(root)
    watcher = load_watcher(root, path)
    rule = rule_version(rule_id=watcher['rule']['rule_id'], root=root,
                        module=watcher['rule']['module'], profile=watcher['rule']['profile'])
    sources = cited_sources(watcher['facts'])
    if not sources:
        raise InvariantError('Watcher facts cite no source')
    body = {'schema': SEAL_SCHEMA, 'watcher_id': watcher['watcher_id'], 'watcher_file': str(path),
            'watcher_sha256': file_sha256(root / path), 'rule_version': rule, 'fact_sources': sources}
    return {**body, 'watcher_seal_sha256': digest(body)}


def _read(record, path: list[str]):
    value = record
    for name in path:
        if not isinstance(value, dict) or name not in value:
            return None
        value = value[name]
    return value


def read_context(watcher: dict, record) -> dict:
    """Every fact read from the record by its path: a value, missing, or present but unreadable."""
    if not isinstance(record, dict):
        raise InvariantError('Record required')
    facts, missing, unreadable = {}, [], []
    for fact in watcher['facts']:
        raw = _read(record, fact['path'])
        kind, value = fact['kind'], None
        if raw is None:
            missing.append(fact['fact'])
        elif kind == 'code' and isinstance(raw, str) and raw:
            value = raw
        elif kind == 'classification' and isinstance(raw, dict) \
                and isinstance(raw.get('scheme'), str) and raw['scheme'] and isinstance(raw.get('id'), str) and raw['id']:
            value = {'scheme': raw['scheme'], 'id': raw['id']}
        elif kind == 'boolean' and isinstance(raw, bool):
            value = raw
        elif kind == 'text' and isinstance(raw, str) and raw.strip():
            value = raw
        else:
            unreadable.append(fact['fact'])
        facts[fact['fact']] = value
    return {'facts': facts, 'missing': missing, 'unreadable': unreadable}


def _holds(spec, name: str, context: dict) -> bool:
    if spec == 'missing':
        return name in context['missing']
    value = context['facts'].get(name)
    if value is None:
        return False
    if 'in' in spec:
        return value in spec['in']
    return value == spec['equals']


def select(watcher: dict, context: dict) -> dict:
    """The first selection row whose every condition holds, or the watcher's otherwise."""
    for index, row in enumerate(watcher['selection']):
        if all(_holds(spec, name, context) for name, spec in row['when'].items()):
            return {'outcome': 'SELECTED', 'row': index, 'apply': list(row['apply'])}
    return {'outcome': 'NOT_SELECTED', 'row': None, 'apply': [], 'reason': watcher['otherwise']['reason']}


def lens(watcher: dict, sealed: dict, record) -> dict:
    """The block a result row carries: which watcher, which seal, what was read, what was selected."""
    if sealed.get('schema') != SEAL_SCHEMA or sealed.get('watcher_id') != watcher['watcher_id'] \
            or not HEX64.fullmatch(sealed.get('watcher_seal_sha256', '')):
        raise InvariantError('Seal of this watcher required')
    context = read_context(watcher, record)
    return {'watcher_id': watcher['watcher_id'], 'watcher_seal_sha256': sealed['watcher_seal_sha256'],
            'context': context, 'selection': select(watcher, context)}


def check_lens(row: dict, *, watcher: dict, sealed: dict, record) -> list[str]:
    """Problems with one row's watcher block against the sealed watcher and the record it was read from."""
    block = row.get('watcher') if isinstance(row, dict) else None
    if not isinstance(block, dict):
        return ['watcher block missing']
    expected = lens(watcher, sealed, record)
    problems = []
    if block.get('watcher_id') != expected['watcher_id']:
        problems.append('watcher_id differs')
    if block.get('watcher_seal_sha256') != expected['watcher_seal_sha256']:
        problems.append('watcher_seal_sha256 differs from the seal recomputed from this repository')
    if block.get('context') != expected['context']:
        problems.append('context differs from the facts read from the record')
    if block.get('selection') != expected['selection']:
        problems.append('selection differs from the sealed selection table')
    if set(block) != set(expected):
        problems.append('watcher block carries parts that are not its own')
    return problems


def check_seal(results: dict, sealed: dict) -> list[str]:
    """Problems with a results file's file-level seal."""
    if results.get('watcher_seal') != sealed:
        return ['file-level watcher_seal differs from the seal recomputed from this repository']
    return []
