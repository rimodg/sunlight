#!/usr/bin/env python3
"""Print the roster of every watcher under config/watchers, sealed from this checkout.

Reads only and prints to standard output; it never writes a file. To record
a new roster, redirect the output into config/roster.json and commit it with
the watcher change it answers to. The output is the roster as it would be
loaded: schema, purpose, one entry per watcher file ordered by watcher_id,
and roster_sha256 over the rest.

Usage: PYTHONPATH=code python scripts/seal_roster.py > config/roster.json
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from roster import ROSTER_FILE, build_roster, load_roster  # noqa: E402

PURPOSE = ('The watchers that may run, each with the hash of its file, its rule version and its seal. '
           'A watcher not on this list, or whose seal recomputed from the checkout differs, does not run. '
           'Every results file names this roster.')


def main():
    try:
        purpose = load_roster(ROOT, ROSTER_FILE)['purpose']
    except Exception:
        purpose = PURPOSE
    print(json.dumps(build_roster(ROOT, purpose), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
