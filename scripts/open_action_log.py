#!/usr/bin/env python3
"""Open the action log for one decision inbox and write it to a new file.

Reads the inbox file, the action policy and nothing else; refuses to
overwrite an existing output and writes only the output named. The inbox
file must be inside the repository: the log names it by repository relative
path, by the hash of its bytes and by inbox_sha256, so a verifier reads the
same file. The log opens with no entries and every waiting item open. A
decision is recorded later with scripts/record_decision.py; nothing is
decided here (see code/actionlog.py).

Usage: PYTHONPATH=code python scripts/open_action_log.py INBOX OUT
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from actionlog import POLICY_FILE, load_policy, open_log  # noqa: E402
from inbox import load_inbox  # noqa: E402


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n'


def opened(inbox_path: Path, root=ROOT) -> dict:
    resolved = inbox_path.resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise SystemExit('Inbox file must be inside the repository')
    raw = resolved.read_bytes()
    return open_log(load_inbox(resolved), inbox_file=str(resolved.relative_to(Path(root).resolve())), inbox_bytes=raw,
                    policy=load_policy(root, POLICY_FILE), root=root, policy_file=POLICY_FILE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inbox', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit('Refusing to overwrite an existing output')
    out = opened(args.inbox)
    args.out.write_text(canonical(out))
    print(json.dumps({k: out[k] for k in ('inbox_file', 'rule_id', 'waiting', 'decided', 'open', 'recorded', 'log_sha256')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
