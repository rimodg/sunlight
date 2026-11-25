#!/usr/bin/env python3
"""Record one person's decision on one inbox item, as one more entry in an action log.

Reads the log, the inbox it names (from this checkout, bytes compared) and
the action policy; appends one entry chained to the entry before it and
writes the log back. It writes the log named and nothing else. The item
must wait in the inbox; the decision and the role must be on the policy;
the reason is required and must not carry an address; the time is UTC to
the second, taken from the clock unless --at gives it. A decision on an
item that already has one is a new entry after the old one, never a
replacement. Nothing is decided here: the person who runs this decided
(see code/actionlog.py).

Usage: PYTHONPATH=code python scripts/record_decision.py LOG --item POSITION \\
         --decision CODE --role ROLE --reason TEXT [--at 2026-11-24T20:00:00Z]
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from actionlog import POLICY_FILE, load_log, load_policy, record  # noqa: E402
from inbox import load_inbox  # noqa: E402
from invariant_core import InvariantError  # noqa: E402


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n'


def recorded(log_path: Path, *, position: int, decision: str, role: str, reason: str, at: str, root=ROOT) -> dict:
    resolved = log_path.resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise SystemExit('Action log must be inside the repository')
    log = load_log(resolved)
    inbox_path = Path(root) / log['inbox_file']
    if not inbox_path.is_file():
        raise SystemExit('Inbox file the log names is not in this checkout')
    return record(log, load_inbox(inbox_path), position=position, decision=decision, role=role, reason=reason,
                  decided_at=at, policy=load_policy(root, POLICY_FILE), inbox_bytes=inbox_path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('log', type=Path)
    parser.add_argument('--item', type=int, required=True, help='position of the item in the inbox')
    parser.add_argument('--decision', required=True, help='a decision code from config/action-policy.json')
    parser.add_argument('--role', required=True, help='a role from config/action-policy.json')
    parser.add_argument('--reason', required=True, help='the reason, in the words of the person deciding')
    parser.add_argument('--at', default=None, help='UTC time to the second; the clock when omitted')
    args = parser.parse_args()
    at = args.at or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    try:
        out = recorded(args.log, position=args.item, decision=args.decision, role=args.role, reason=args.reason, at=at)
    except InvariantError as exc:
        raise SystemExit(f'Refused: {exc}') from exc
    args.log.write_text(canonical(out))
    entry = out['entries'][-1]
    print(json.dumps({'log': str(args.log), 'entry': entry, 'decided': out['decided'], 'open': out['open'],
                      'recorded': out['recorded'], 'log_sha256': out['log_sha256']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
