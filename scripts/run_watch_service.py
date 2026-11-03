#!/usr/bin/env python3
"""Refuse drift before importing or running the watch loop."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from watch_service import PIN, external, pinned, read_config


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "--config":
        raise ValueError("Explicit service configuration required")
    target = Path(sys.argv[2])
    if target.name != "service.json":
        raise ValueError("Unexpected service configuration path")
    config = read_config(target.parent)
    pinned(sys.executable, environment=config["environment"])
    from watch_engine import build_identity, main as watch_main
    if build_identity() != config["build"]:
        raise ValueError("Source or runtime changed after installation; verified reinstall required")
    data = external(config["data"])
    for p in [data / "journal.sqlite3", data / "source-policy.json"]:
        if p.is_symlink():
            raise ValueError("Symlinked runtime file refused")
    pol = data / "source-policy.json"
    if hashlib.sha256(pol.read_bytes()).hexdigest() != config["policy_sha256"]:
        raise ValueError("Source policy changed after installation")
    os.umask(0o077)
    sys.argv = [sys.argv[0], "--data-dir", str(data), "--policy", str(pol), "--interval", str(config["interval_seconds"])]
    watch_main()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("SUNLIGHT watch startup refused; verify pinned environment, source and operator configuration", file=sys.stderr)
        raise SystemExit(2)
