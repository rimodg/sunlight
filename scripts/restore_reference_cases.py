#!/usr/bin/env python3
"""Restore the ignored prosecution fixture from its last tracked Git blob.

Existing files are preserved. The database is a separate reference input.
"""
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BLOB = "b0043dca177daffb6bce8c05363efba617ce31d4"


def main():
    destination = ROOT / "prosecuted_cases.json"
    if destination.exists():
        raw = destination.read_bytes()
        state = "existing file preserved"
    else:
        raw = subprocess.check_output(["git", "cat-file", "blob", SOURCE_BLOB], cwd=ROOT)
        data = json.loads(raw)
        if not data.get("cases") or not all("case_id" in c and "markup_pct" in c for c in data["cases"]):
            raise ValueError("Historical blob does not have the required reference schema")
        with destination.open("xb") as stream:
            stream.write(raw)
        state = "restored from last tracked root fixture"
    print(json.dumps({"status": state, "source_git_blob": SOURCE_BLOB,
                      "file_sha256": hashlib.sha256(raw).hexdigest(),
                      "database": "separate input; not created or reconstructed"}, indent=2))


if __name__ == "__main__":
    main()
