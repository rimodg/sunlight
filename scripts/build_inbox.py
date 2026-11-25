#!/usr/bin/env python3
"""Build the decision inbox for one results file and write it to a new file.

Reads the results file, the inbox policy and nothing else; refuses to
overwrite an existing output and writes only the output named. The results
file must be inside the repository: the inbox names it by repository
relative path and by the hash of its bytes, so a verifier reads the same
file. Rows whose state the policy names for the file's rule become items, in
results order; every other row is counted under its state. Nothing is
decided here (see code/inbox.py).

Usage: PYTHONPATH=code python scripts/build_inbox.py RESULTS OUT
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from inbox import POLICY_FILE, build_inbox, load_policy  # noqa: E402


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n'


def build(results_path: Path, root=ROOT) -> dict:
    resolved = results_path.resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise SystemExit('Results file must be inside the repository')
    raw = resolved.read_bytes()
    return build_inbox(json.loads(raw), results_file=str(resolved.relative_to(Path(root).resolve())), results_bytes=raw,
                       policy=load_policy(root, POLICY_FILE), root=root, policy_file=POLICY_FILE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit('Refusing to overwrite an existing output')
    out = build(args.results)
    args.out.write_text(canonical(out))
    print(json.dumps({k: out[k] for k in ('results_file', 'rule_id', 'rows', 'rule_did_not_run', 'not_waiting', 'waiting', 'inbox_sha256')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
