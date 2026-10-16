#!/usr/bin/env python3
"""Verify content equality in a downloaded workspace packet, offline.

This checks hashes, not authorship. An attacker able to replace both a
packet and its hashes can produce a self-consistent replacement.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from analysis_receipt import content_digest, substantive_result


def verify(packet, code_root=None):
    response = packet["response"]
    results = response.get("results", [response])
    checks = []
    for index, result in enumerate(results):
        receipt = result["analysis_receipt"]
        if receipt["schema_version"] != "sunlight.analysis-receipt.v1":
            raise ValueError("Unsupported receipt schema")
        current = {
            "index": index, "ocid": result["ocid"],
            "submitted_request_matches": content_digest(packet["request"]) == receipt["submitted_request_sha256"],
            "input_matches": content_digest(receipt["normalized_request"]) == receipt["input_sha256"],
            "result_matches": content_digest(substantive_result(result)) == receipt["result_sha256"],
            "manifest_matches": content_digest(receipt["source_manifest"]) == receipt["source_manifest_sha256"],
        }
        if code_root is not None:
            root = Path(code_root).resolve()
            matches = True
            for name, digest in receipt["source_manifest"].items():
                target = (root / name).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    matches = False
                    break
                import hashlib
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    matches = False
                    break
            current["local_source_matches"] = matches
        checks.append(current)
    return {
        "verified_records": len(checks),
        "content_checks_passed": bool(checks) and all(
            all(v for k, v in check.items() if k.endswith("matches")) for check in checks),
        "checks": checks,
        "limit": "Content equality only. Not a signature, source authentication, legal certification, or independent validation of findings.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--code-root", type=Path, help="Also compare the receipt's source files with this directory")
    args = parser.parse_args()
    try:
        report = verify(json.loads(args.packet.read_text()), args.code_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"content_checks_passed": False, "error": str(exc)}))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["content_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
