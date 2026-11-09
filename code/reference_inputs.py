"""Read-only admission of exact reference files, without constructing a corpus."""
import hashlib
from pathlib import Path
import re


def verify_reference_inputs(manifest, *, database=None, cases=None):
    if manifest.get("schema") != "sunlight.reference-inputs.v1" or set(manifest.get("artifacts", {})) != {"database", "cases"}:
        raise ValueError("Invalid reference-input manifest")
    rows = {}
    for name, supplied in [("database", database), ("cases", cases)]:
        spec = manifest["artifacts"][name]
        expected = spec.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("A SHA-256 digest is required for each reference artifact")
        row = {"expected_sha256": expected, "state": "not_configured", "observed_sha256": None,
               "observed_size_bytes": None, "storage_locator_registered": bool(spec.get("locator"))}
        if supplied:
            path = Path(supplied).expanduser()
            row["path"] = str(path.absolute())
            if not path.exists():
                row["state"] = "missing"
            elif not path.is_file():
                row["state"] = "not_a_file"
            else:
                value, size = hashlib.sha256(), 0
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        value.update(chunk); size += len(chunk)
                row["observed_sha256"], row["observed_size_bytes"] = value.hexdigest(), size
                row["state"] = "verified" if value.hexdigest() == expected else "hash_mismatch"
        rows[name] = row
    ready = all(r["state"] == "verified" for r in rows.values())
    return {"schema": "sunlight.reference-admission.v1", "artifacts": rows,
            "ready_to_run_reference_protocols": ready, "reference_protocols_executed": False,
            "qualification": "Artifact identity only. No evaluation numbers recomputed and no field-accuracy claim."}
