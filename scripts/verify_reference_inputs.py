#!/usr/bin/env python3
"""Verify exact operator-local reference inputs. Never download or create them."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from reference_inputs import verify_reference_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "config/reference-inputs.json")
    parser.add_argument("--db", default=os.environ.get("SUNLIGHT_REFERENCE_DB"))
    parser.add_argument("--cases", default=os.environ.get("SUNLIGHT_REFERENCE_CASES"))
    args = parser.parse_args()
    result = verify_reference_inputs(json.loads(args.manifest.read_text()), database=args.db, cases=args.cases)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready_to_run_reference_protocols"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
