#!/usr/bin/env python3
"""Emit substantive API artifacts for a repeatable synthetic reference set.

This exercises actual single and batch endpoints. It is not the full-corpus
evaluation. Only declared volatile timing fields are omitted.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from fastapi.testclient import TestClient
from api import app
from analysis_receipt import substantive_result


def snapshot():
    client = TestClient(app)
    records = [
        {"ocid": "synthetic-sparse"},
        {"ocid": "synthetic-direct", "buyer": {"id": "example", "name": "Example authority"},
         "tender": {"procurementMethod": "direct", "value": {"amount": 1000000, "currency": "USD"}},
         "awards": [{"suppliers": [{"id": "example-supplier", "name": "Example supplier"}],
                     "value": {"amount": 1200000, "currency": "USD"}}]},
    ]
    singles = []
    for record in records:
        response = client.post("/analyze", json={"contract": record})
        response.raise_for_status()
        result = response.json()
        if result["errors"]:
            raise RuntimeError(result["errors"])
        singles.append({"reading": substantive_result(result), "receipt": result["analysis_receipt"]})
    response = client.post("/batch", json={"contracts": records, "capacity_budget": 1})
    response.raise_for_status()
    batch = response.json()
    if batch["total_errors"] or batch["total_processed"] != len(records):
        raise RuntimeError("Batch did not complete every reference record")
    return {"scope": "synthetic API reference set; not full-corpus evaluation",
            "single": singles,
            "batch": {"threshold_metadata": batch["threshold_metadata"],
                      "results": [{"reading": substantive_result(r), "receipt": r["analysis_receipt"]}
                                  for r in batch["results"]]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(snapshot(), sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
