#!/usr/bin/env python3
"""Verify the chain of custody of a section 53 results file.

Recomputes, from this repository, the rule version every row claims and the
hash over every row; checks every row cites a page of the given capture file
and that the page's projection hash recomputes from that file. Reads only.
Exit 0 when every link holds, 1 otherwise.

Usage: PYTHONPATH=code python scripts/verify_section53_custody.py RESULTS CAPTURE
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
sys.path.insert(0, str(ROOT / 'scripts'))
from custody import check_capture_file, check_results  # noqa: E402
from measure_section53 import canonical, current_rule_version  # noqa: E402


def cited_path(capture: Path) -> str:
    resolved = capture.resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(capture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('capture', type=Path, help='the capture file the results cite')
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    capture = json.loads(args.capture.read_text())
    rule = current_rule_version()
    problems = check_results(results, rule=rule)
    problems += check_capture_file(results, capture, capture_file=cited_path(args.capture), projection_bytes=canonical)
    cited = {r['custody']['source']['page'] for r in results.get('results', []) if isinstance(r.get('custody'), dict)}
    print(json.dumps({'results': str(args.results), 'rows': len(results.get('results', [])),
                      'distinct_cited_pages': len(cited), 'capture_pages': len(capture.get('pages', [])),
                      'rule_id': rule['rule_id'], 'rule_version_sha256': rule['rule_version_sha256'],
                      'rule_module_sha256': rule['rule_module_sha256'], 'profile_sha256': rule['profile_sha256'],
                      'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
