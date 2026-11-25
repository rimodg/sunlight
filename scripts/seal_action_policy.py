#!/usr/bin/env python3
"""Print the action policy with its hash recomputed from its own content.

Reads only and prints to standard output; it never writes a file. To record
a changed policy, redirect the output into config/action-policy.json and
commit it with the change it answers to. The output is the policy as it
would be loaded: schema, purpose, decisions ordered by code, roles ordered,
and policy_sha256 over the rest. A policy with a missing, malformed or
extra part is refused, not repaired.

Usage: PYTHONPATH=code python scripts/seal_action_policy.py > config/action-policy.json
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from actionlog import POLICY_FILE, seal_policy  # noqa: E402


def main():
    print(json.dumps(seal_policy(json.loads((ROOT / POLICY_FILE).read_text())), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
