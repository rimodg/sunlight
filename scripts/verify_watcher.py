#!/usr/bin/env python3
"""Verify the sealed watcher's lens on every row of a results file.

Recomputes, from this repository, the seal of the watcher the file names
(watcher file bytes, rule version, every cited fact source); then, for every
row, finds the record it was read from in the input file, reads the facts
again, runs the sealed selection table again, and compares with what the row
carries. Also recomputes every row's custody hash. Reads only. Exit 0 when
every link holds, 1 otherwise.

Usage: PYTHONPATH=code python scripts/verify_watcher.py WATCHER RESULTS INPUT
  WATCHER  config/watchers/events-in-order.json or config/watchers/section53.json
  INPUT    the pair export (events in order) or the capture file (section 53)
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from custody import check_row  # noqa: E402
from watcher import check_lens, check_seal, load_watcher, seal  # noqa: E402


def pair_records(pairs: dict):
    """The exported pair each row was read from, by its four-part key."""
    by_key = {(p['ocid'], p['award_id'], p['award_date'], p['tender_end_date']): p for p in pairs['pairs']}
    return lambda row: by_key.get((row.get('ocid'), row.get('award_id'), row.get('award_date'), row.get('tender_end_date')))


def release_records(capture: dict):
    """The admitted release each row was read from, by cited page and locator."""
    def find(row):
        page, locator = row.get('page'), row.get('locator', '')
        pages = capture.get('pages', [])
        if not isinstance(page, int) or page < 0 or page >= len(pages) or 'projection' not in pages[page]:
            return None
        parts = locator.split('/')
        if len(parts) < 3 or parts[1] != 'releases' or not parts[2].isdigit():
            return None
        index = int(parts[2])
        for item in pages[page]['projection'].get('records', []):
            if item.get('index') == index:
                return item.get('record')
        return None
    return find


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('watcher', type=Path)
    parser.add_argument('results', type=Path)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    watcher_file = str(args.watcher.resolve().relative_to(ROOT)) if args.watcher.resolve().is_relative_to(ROOT) else str(args.watcher)
    watcher = load_watcher(ROOT, watcher_file)
    sealed = seal(ROOT, watcher_file)
    results = json.loads(args.results.read_text())
    data = json.loads(args.input.read_text())
    find = pair_records(data) if 'pairs' in data else release_records(data)
    rule = sealed['rule_version']
    problems = check_seal(results, sealed)
    outcomes = {'SELECTED': 0, 'NOT_SELECTED': 0}
    for index, row in enumerate(results.get('results', [])):
        record = find(row)
        if record is None:
            problems.append(f'row {index}: record not found in the input file')
            continue
        for problem in check_lens(row, watcher=watcher, sealed=sealed, record=record) + check_row(row, rule=rule):
            problems.append(f'row {index}: {problem}')
        outcome = row.get('watcher', {}).get('selection', {}).get('outcome')
        if outcome in outcomes:
            outcomes[outcome] += 1
    print(json.dumps({'watcher_id': watcher['watcher_id'], 'watcher_file': watcher_file,
                      'watcher_sha256': sealed['watcher_sha256'], 'watcher_seal_sha256': sealed['watcher_seal_sha256'],
                      'rule_version_sha256': rule['rule_version_sha256'], 'fact_sources': len(sealed['fact_sources']),
                      'rows': len(results.get('results', [])), 'outcomes': outcomes, 'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
