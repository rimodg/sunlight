#!/usr/bin/env python3
"""Verify action log files against the inboxes and the action policy in this checkout.

For each log file given: every part is checked, the chain recomputed entry
by entry from the inbox hash, the items, counts and head recomputed from
the entries and log_sha256 recomputed; the inbox it names is read from this
checkout, its bytes compared and its parts loaded, and every item line and
every entry compared with the inbox item at that position; the policy
reference is compared with config/action-policy.json and every entry's
decision and role with its tables; the inbox itself is checked against the
results file and the inbox policy in this checkout (check_inbox), so a log
only verifies on an inbox that does. Reads only. Exit 0 when every link
holds, 1 otherwise.

Usage: PYTHONPATH=code python scripts/verify_action_log.py LOG [LOG ...]
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from actionlog import POLICY_FILE, check_log, load_log  # noqa: E402
from inbox import POLICY_FILE as INBOX_POLICY_FILE, check_inbox, load_inbox  # noqa: E402
from invariant_core import InvariantError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', type=Path, nargs='+')
    args = parser.parse_args()
    files, problems = {}, []
    for path in args.logs:
        summary = {'problems': []}
        try:
            log = load_log(path)
        except InvariantError as exc:
            summary['problems'].append(f'log cannot be loaded ({exc})')
        else:
            summary.update({k: log[k] for k in ('inbox_file', 'rule_id', 'waiting', 'decided', 'open', 'recorded',
                                                 'head_sha256', 'log_sha256')})
            summary['items'] = log['items']
            summary['entries'] = [{k: e[k] for k in ('seq', 'position', 'decision', 'decided_by', 'decided_at')} for e in log['entries']]
            summary['problems'].extend(check_log(log, ROOT, POLICY_FILE))
            inbox_path = ROOT / log['inbox_file']
            if inbox_path.is_file():
                try:
                    summary['problems'].extend(f'inbox: {p}' for p in check_inbox(load_inbox(inbox_path), ROOT, INBOX_POLICY_FILE))
                except InvariantError as exc:
                    summary['problems'].append(f'inbox cannot be loaded ({exc})')
        files[str(path)] = summary
        problems.extend(f'{path}: {p}' for p in summary['problems'])
    print(json.dumps({'policy_file': POLICY_FILE, 'logs': files, 'problems': problems}, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
