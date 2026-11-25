#!/usr/bin/env python3
"""Verify decision inbox files against the results files and the policy in this checkout.

For each inbox file given: every part is checked and inbox_sha256
recomputed; the results file it names is read from this checkout and its
bytes compared; the inbox is rebuilt from that file and config/inbox-policy.json
and compared part by part (a row that waits under the policy but is not
listed, a listed row that does not wait, and any item or count that differs
are each reported); the results file's roster reference is checked against
the roster in this checkout and the watcher it names. Reads only. Exit 0
when every link holds, 1 otherwise.

Usage: PYTHONPATH=code python scripts/verify_inbox.py INBOX [INBOX ...]
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from inbox import POLICY_FILE, check_inbox, load_inbox  # noqa: E402
from invariant_core import InvariantError  # noqa: E402
from roster import ROSTER_FILE, check_reference, load_roster  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inboxes', type=Path, nargs='+')
    args = parser.parse_args()
    roster = load_roster(ROOT, ROSTER_FILE)
    files, problems = {}, []
    for path in args.inboxes:
        summary = {'problems': []}
        try:
            inbox = load_inbox(path)
        except InvariantError as exc:
            summary['problems'].append(f'inbox cannot be loaded ({exc})')
        else:
            summary.update({k: inbox[k] for k in ('results_file', 'rule_id', 'watcher_id', 'rows', 'rule_did_not_run',
                                                   'not_waiting', 'waiting', 'inbox_sha256')})
            summary['items'] = [{k: i[k] for k in ('position', 'record', 'said', 'result_sha256')} for i in inbox['items']]
            summary['problems'].extend(check_inbox(inbox, ROOT, POLICY_FILE))
            results_path = ROOT / inbox['results_file']
            if results_path.is_file():
                summary['problems'].extend(check_reference(json.loads(results_path.read_text()), ROOT, roster, ROSTER_FILE))
        files[str(path)] = summary
        problems.extend(f'{path}: {p}' for p in summary['problems'])
    print(json.dumps({'policy_file': POLICY_FILE, 'roster_sha256': roster['roster_sha256'],
                      'inboxes': files, 'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
