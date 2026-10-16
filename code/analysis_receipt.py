"""Content-addressed receipts for inspection, not proof of source authenticity.

No scoring dependencies: this module only describes a completed analysis.
Runtime timings and the receipt itself are excluded from the result digest.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
import platform
from copy import deepcopy


def content_digest(value):
    """SHA-256 of UTF-8 JSON, sorted keys, compact separators, no NaN."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def source_manifest():
    root = Path(__file__).resolve().parent
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*.py"))
            if "__pycache__" not in path.parts}


def substantive_result(result):
    stable = deepcopy(result)
    stable.pop("processing_time_ms", None)
    stable.pop("analysis_receipt", None)
    stamp = (stable.get("structural_scoring") or {}).get("corpus_stamp")
    if isinstance(stamp, dict):
        stamp.pop("computed_at", None)
    return stable


def build_receipt(request, result, profile, global_parameters, manifest=None, submitted_request=None, submitted_digest=None):
    """Bind submitted input, calibration, source tree, and substantive output.

    This is an integrity receipt, not a signature, legal certification, or
    verification of the truth of supplied documents. Runtime dependencies
    must be retained separately to reproduce a run.
    """
    stable_result = substantive_result(result)
    manifest = source_manifest() if manifest is None else manifest
    dependencies = {}
    for name in ("fastapi", "pydantic", "numpy", "scipy", "networkx", "uvicorn", "httpx"):
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = "not installed"
    return {
        "schema_version": "sunlight.analysis-receipt.v1",
        "canonicalization": "UTF-8 JSON; sorted keys; compact separators; ensure_ascii=false; no NaN",
        "input_sha256": content_digest(request),
        "normalized_request": request,
        "submitted_request_sha256": submitted_digest or content_digest(request if submitted_request is None else submitted_request),
        "result_sha256": content_digest(stable_result),
        "result_excluded_paths": ["processing_time_ms", "analysis_receipt", "structural_scoring.corpus_stamp.computed_at"],
        "profile_sha256": content_digest(asdict(profile)),
        "global_parameters_sha256": content_digest(asdict(global_parameters)),
        "source_manifest_sha256": content_digest(manifest),
        "source_manifest": manifest,
        "runtime": {"python": platform.python_version(), "dependencies": dependencies},
        "scope": "Supplied procurement record; external facts were not authenticated by this receipt.",
        "authority": "Decision support. No payment, freeze, recovery, or enforcement authority.",
        "interpretation": "Risk indicators for review; neither a finding of wrongdoing nor a probability of corruption.",
        "reproduction": "Retain the submitted request, response, matching source files, Python version, and installed dependency versions.",
    }
