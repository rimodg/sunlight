"""Content identity for packaged builds, including images without Git metadata.

Matching a manifest proves content equality, not publisher authenticity. An
injected revision is explicitly a declared build input, never a signature.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess

SCHEMA = "sunlight.build-identity.v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def source_files(root):
    root = Path(root).resolve()
    paths = []
    for pattern in ["code/*.py", "code/*.json", "research/corpus/*.json",
                    "data/cpd_profiles/*.json", "data/evidence_maps/*.json",
                    "config/*.json", "deploy/launchd/*.plist", "sunlight-dashboard/dist/**/*"]:
        paths.extend(p for p in root.glob(pattern) if p.is_file())
    paths.extend(root / name for name in ["requirements.lock", "requirements.txt", "Dockerfile",
                 "scripts/watch_service.py", "scripts/run_watch_service.py", "scripts/watch-service",
                 "scripts/install-watch", "scripts/uninstall-watch"] if (root / name).is_file())
    result = {}
    for path in sorted(set(paths)):
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError("Build source symlink refused")
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not any(p.startswith("code/") for p in result):
        raise ValueError("No application source to identify")
    return result


def environment():
    # Paths, usernames and credentials are deliberately absent.
    packages = sorted((d.metadata["Name"].lower().replace("_", "-"), d.version)
                      for d in importlib.metadata.distributions() if d.metadata["Name"])
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "packages_sha256": digest(packages)}


def git_state(root):
    root = Path(root).resolve()
    if not (root / ".git").exists():
        return {"git_commit": None, "git_commit_basis": "not_available", "dirty": None}
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                         stderr=subprocess.DEVNULL, text=True, timeout=2).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"],
                                            stderr=subprocess.DEVNULL, text=True, timeout=2).strip())
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise ValueError("Invalid Git revision")
        return {"git_commit": commit, "git_commit_basis": "local_git_head", "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": None, "git_commit_basis": "not_available", "dirty": None}


def write_manifest(root, *, commit=None):
    root = Path(root).resolve()
    local = git_state(root)
    if commit:
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise ValueError("A full Git revision is required, not a tag or shortened hash")
        if local["git_commit"] and local["git_commit"] != commit:
            raise ValueError("Declared revision disagrees with local Git HEAD")
        if not local["git_commit"]:
            local = {"git_commit": commit, "git_commit_basis": "declared_build_input", "dirty": None}
    files = source_files(root)
    payload = {"schema": SCHEMA, **local, "source_sha256": digest(files),
               "source_files": files, "environment": environment()}
    manifest = {"payload": payload, "sha256": digest(payload)}
    path = root / "build_identity.json"
    if path.is_symlink():
        raise ValueError("Build manifest symlink refused")
    path.write_text(canonical(manifest) + "\n")
    return manifest


def runtime_identity(root=None):
    """Call once at process startup. Do not relabel a running process on requests."""
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    path = root / "build_identity.json"
    files = source_files(root)
    actual_environment = environment()
    if path.exists():
        if path.is_symlink():
            raise ValueError("Build manifest symlink refused")
        manifest = json.loads(path.read_text())
        payload = manifest["payload"]
        if manifest["sha256"] != digest(payload) or payload["schema"] != SCHEMA:
            raise ValueError("Build manifest digest or schema mismatch")
        if payload["source_files"] != files or payload["source_sha256"] != digest(files):
            raise ValueError("Packaged source differs from build manifest")
        if payload["environment"] != actual_environment:
            raise ValueError("Runtime environment differs from build manifest")
        state = "packaged_files_match"
        identity_sha = manifest["sha256"]
    else:
        payload = {"schema": SCHEMA, **git_state(root), "source_sha256": digest(files),
                   "source_files": files, "environment": actual_environment}
        state = "working_tree" if payload["git_commit"] else "source_fingerprint_only"
        identity_sha = digest(payload)
    return {"schema": SCHEMA, "state": state, "identity_sha256": identity_sha,
            "source_sha256": payload["source_sha256"], "git_commit": payload["git_commit"],
            "git_commit_basis": payload["git_commit_basis"], "dirty": payload["dirty"],
            "python": actual_environment["python"], "implementation": actual_environment["implementation"],
            "packages_sha256": actual_environment["packages_sha256"],
            "qualification": "Content equality is not publisher authentication or a signed attestation."}


def version_label(identity):
    label = (identity["git_commit"] or "src." + identity["source_sha256"][:12])
    if identity["dirty"]:
        label += ".dirty." + identity["source_sha256"][:12]
    return "4.0.0+" + label


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["write", "verify"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--commit")
    args = parser.parse_args()
    if args.action == "write":
        supplied = [v for v in [args.commit, os.environ.get("SUNLIGHT_BUILD_COMMIT"),
                                os.environ.get("RENDER_GIT_COMMIT")] if v]
        if len(set(supplied)) > 1:
            raise ValueError("Conflicting build revision inputs")
        write_manifest(args.root, commit=supplied[0] if supplied else None)
    print(canonical(runtime_identity(args.root)))


if __name__ == "__main__":
    main()
