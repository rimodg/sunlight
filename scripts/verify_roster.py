#!/usr/bin/env python3
"""Verify the roster against the watchers sealed from this checkout, and results files against the roster.

Loads config/roster.json (every part checked, roster_sha256 recomputed), then
seals every watcher it names from this checkout and compares each entry part
by part; a watcher file under config/watchers that the roster does not name
is reported. For each results file given, checks that the file names this
roster (by file bytes and by content) and that the watcher whose seal the
file carries is on the roster with that seal. Reads only. Exit 0 when every
link holds, 1 otherwise.

Usage: PYTHONPATH=code python scripts/verify_roster.py [RESULTS ...]
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from roster import ROSTER_FILE, check_reference, check_roster, load_roster  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path, nargs='*')
    args = parser.parse_args()
    roster = load_roster(ROOT, ROSTER_FILE)
    problems = check_roster(ROOT, roster)
    files = {}
    for path in args.results:
        results = json.loads(path.read_text())
        found = check_reference(results, ROOT, roster, ROSTER_FILE)
        files[str(path)] = {'watcher_id': results.get('watcher_seal', {}).get('watcher_id'), 'problems': found}
        problems.extend(f'{path}: {p}' for p in found)
    print(json.dumps({'roster_file': ROSTER_FILE, 'roster_sha256': roster['roster_sha256'],
                      'watchers': [{k: e[k] for k in ('watcher_id', 'file', 'watcher_seal_sha256')} for e in roster['watchers']],
                      'results_files': files, 'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
