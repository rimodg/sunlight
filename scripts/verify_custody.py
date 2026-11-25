#!/usr/bin/env python3
"""Verify the chain of custody of an events-in-order results file.

Recomputes, from this repository, the rule version every row claims and the
hash over every row; checks every row cites the same capture as the pair
export; optionally checks every cited capture against a watch journal opened
read-only. Reads only. Exit 0 when every link holds, 1 otherwise.

Usage: PYTHONPATH=code python scripts/verify_custody.py RESULTS PAIRS [--journal JOURNAL]
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
sys.path.insert(0, str(ROOT / 'scripts'))
from custody import check_journal, check_results  # noqa: E402
from measure_events_in_order import current_rule_version  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('pairs', type=Path)
    parser.add_argument('--journal', type=Path, default=None, help='watch journal sqlite file, opened read-only')
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    pairs_bytes = args.pairs.read_bytes()
    rule = current_rule_version()
    problems = check_results(results, rule=rule, pairs=json.loads(pairs_bytes), pairs_bytes=pairs_bytes)
    journal_checked = False
    if args.journal is not None:
        problems += check_journal(results, args.journal)
        journal_checked = True
    cited = {r['custody']['source']['capture_seq'] for r in results.get('results', []) if isinstance(r.get('custody'), dict)}
    print(json.dumps({'results': str(args.results), 'rows': len(results.get('results', [])),
                      'distinct_cited_captures': len(cited),
                      'rule_id': rule['rule_id'], 'rule_version_sha256': rule['rule_version_sha256'],
                      'rule_module_sha256': rule['rule_module_sha256'], 'profile_sha256': rule['profile_sha256'],
                      'journal_checked': journal_checked, 'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
