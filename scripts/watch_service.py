#!/usr/bin/env python3
"""Install the pinned watch LaunchAgent. No data deletion, system fallback or model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from watch_capture import policy
from watch_engine import build_identity, now
from watch_health import health
from watch_identity import canonical
from watch_journal import Journal

PIN = json.loads((ROOT / "config/watch-runtime.json").read_text())["python"]


def run(args, **kw):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True, **kw)


def external(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("Symlinked operational destination refused")
    path = path.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("Operational data and environment must be outside the repository")
    return path


def pinned(python, *, environment=None):
    code = "import sys,platform,json,importlib.metadata as m;print(json.dumps({'python':platform.python_version(),'prefix':sys.prefix,'packages':{d.metadata['Name'].lower().replace('_','-'):d.version for d in m.distributions()}}))"
    info = json.loads(run([python, "-I", "-c", code]).stdout)
    if info["python"] != PIN:
        raise ValueError("CPython " + PIN + " is required; no interpreter fallback")
    if environment:
        if Path(info["prefix"]).resolve() != Path(environment).resolve():
            raise ValueError("Configured virtual environment is not active")
        expected = dict(line.strip().split("==") for line in (ROOT / "requirements.lock").read_text().splitlines() if line.strip())
        installed = {k: v for k, v in info["packages"].items() if k not in {"pip", "setuptools", "wheel"}}
        if installed != {k.lower().replace("_", "-"): v for k, v in expected.items()}:
            raise ValueError("Environment does not exactly match requirements.lock; retained for diagnosis")
    return info


def write_if_changed(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Symlinked installation file refused")
    if path.exists() and path.read_bytes() == data:
        return False
    tmp = path.with_name(path.name + ".install-tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return True


def boot_epoch():
    text = run(["sysctl", "-n", "kern.boottime"]).stdout
    match = re.search(r"sec\s*=\s*(\d+)", text)
    if not match:
        raise ValueError("Cannot determine current Mac boot epoch")
    return int(match[1])


def loaded(label):
    result = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"], capture_output=True, text=True)
    return result.returncode == 0, result.stdout


def owned(plist, config):
    if not plist.exists():
        return
    if plist.is_symlink():
        raise ValueError("Symlinked LaunchAgent refused")
    value = plistlib.loads(plist.read_bytes())
    expected = [str(Path(config["environment"]) / "bin/python"), "-I", str(ROOT / "scripts/run_watch_service.py"),
                "--config", str(Path(config["data"]) / "service.json")]
    if value.get("ProgramArguments") != expected or value.get("Label") != config["label"] or value.get("WorkingDirectory") != str(ROOT):
        raise ValueError("Foreign LaunchAgent with this label; refusing replacement or removal")


def install(args):
    data = external(args.data_dir)
    environment = external(args.environment or data / "runtime")
    agents = Path(args.launch_agents_dir or Path.home() / "Library/LaunchAgents").expanduser().absolute()
    if agents.is_symlink():
        raise ValueError("Symlinked LaunchAgents directory refused")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.label) or args.interval < 1:
        raise ValueError("Invalid label or interval")
    if not args.policy:
        raise ValueError("An explicitly reviewed source policy is required")
    source_bytes = Path(args.policy).read_bytes()
    source_policy = policy(json.loads(source_bytes))
    for child in [data / "service.json", data / "source-policy.json", data / "install-receipt.json",
                  data / "logs", data / "journal.sqlite3", environment]:
        if child.is_symlink():
            raise ValueError("Symlinked operational file refused")
    config = {"schema": "sunlight.watch-service.v1", "root": str(ROOT), "data": str(data),
              "environment": str(environment), "label": args.label, "agents": str(agents),
              "interval_seconds": args.interval, "policy_sha256": hashlib.sha256(source_bytes).hexdigest(),
              "build": build_identity()}
    plist = agents / (args.label + ".plist")
    owned(plist, config)
    created = getattr(args, "_created", [])
    for folder in [data, data / "logs", agents]:
        if not folder.exists():
            folder.mkdir(parents=True, mode=0o700); created.append(str(folder))
    python = environment / "bin/python"
    if not environment.exists():
        run([sys.executable, "-I", "-m", "venv", environment])
        created.append(str(environment))
        pinned(python)
        # Only the owner executes this on a Mac with network access. No resolver
        # may relax the exact lock or fall back to a source build.
        run([python, "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-deps",
             "--only-binary=:all:", "-r", ROOT / "requirements.lock"])
    pinned(python, environment=environment)
    replacements = {"__LABEL__": args.label, "__PYTHON__": str(python), "__RUNNER__": str(ROOT / "scripts/run_watch_service.py"),
                    "__CONFIG__": str(data / "service.json"), "__ROOT__": str(ROOT),
                    "__STDOUT__": str(data / "logs/stdout.log"), "__STDERR__": str(data / "logs/stderr.log")}
    template = plistlib.loads((ROOT / "deploy/launchd/org.sunlight.watch.plist").read_bytes())
    def replace(value):
        if isinstance(value, str):
            return replacements.get(value, value)
        if isinstance(value, list):
            return [replace(v) for v in value]
        if isinstance(value, dict):
            return {k: replace(v) for k, v in value.items()}
        return value
    outputs = {data / "service.json": (canonical(config) + "\n").encode(), data / "source-policy.json": source_bytes,
               plist: plistlib.dumps(replace(template), sort_keys=True)}
    changed = [p for p, b in outputs.items() if not p.exists() or p.read_bytes() != b]
    is_loaded, _ = loaded(args.label)
    if is_loaded and not plist.exists():
        raise ValueError("Loaded label has no owned plist; refusing to replace a foreign service")
    if changed and is_loaded:
        run(["launchctl", "bootout", f"gui/{os.getuid()}", plist]); is_loaded = False
    for path, value in outputs.items():
        if write_if_changed(path, value):
            created.append(str(path))
    for log in [data / "logs/stdout.log", data / "logs/stderr.log"]:
        if log.is_symlink():
            raise ValueError("Symlinked log refused")
        if not log.exists():
            log.touch(mode=0o600); created.append(str(log))
    receipt = data / "install-receipt.json"
    if changed or not receipt.exists():
        write_if_changed(receipt, (canonical({"configuration": config, "installed_at": now(),
                                              "installed_boot": boot_epoch()}) + "\n").encode())
        created.append(str(receipt))
    if not is_loaded:
        run(["launchctl", "bootstrap", f"gui/{os.getuid()}", plist])
    is_loaded, _ = loaded(args.label)
    if not is_loaded:
        raise ValueError("LaunchAgent did not load; inspect retained operator logs")
    return {"loaded": True, "created_or_changed": created, "configuration": config,
            "sources_enabled": len(source_policy["sources"]), "native_reboot_verified": False}


def read_config(data):
    data = external(data)
    if (data / "service.json").is_symlink():
        raise ValueError("Symlinked service configuration refused")
    config = json.loads((data / "service.json").read_text())
    if config.get("schema") != "sunlight.watch-service.v1" or config["root"] != str(ROOT) or config["data"] != str(data):
        raise ValueError("Service configuration does not belong to this checkout and data path")
    return config


def uninstall(args):
    data = external(args.data_dir)
    if not (data / "service.json").exists():
        return {"removed": [], "data_retained": str(data)}
    config = read_config(data)
    plist = Path(config["agents"]) / (config["label"] + ".plist")
    owned(plist, config)
    is_loaded, _ = loaded(config["label"])
    if is_loaded:
        run(["launchctl", "bootout", f"gui/{os.getuid()}", plist])
    removed = []
    if plist.exists():
        plist.unlink(); removed.append(str(plist))
    return {"removed": removed, "data_retained": str(data)}


def verify(args):
    config = read_config(args.data_dir)
    pinned(Path(config["environment"]) / "bin/python", environment=config["environment"])
    if config["build"]["source_sha256"] != build_identity()["source_sha256"]:
        raise ValueError("Source changed since install; reinstall required")
    source_bytes = (Path(config["data"]) / "source-policy.json").read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != config["policy_sha256"]:
        raise ValueError("Source policy changed since install; reinstall required")
    is_loaded, text = loaded(config["label"])
    if not is_loaded or not re.search(r"state\s*=\s*running", text) or not re.search(r"pid\s*=\s*[1-9][0-9]*", text):
        raise ValueError("LaunchAgent is not confirmed running")
    journal = Journal(Path(config["data"]) / "journal.sqlite3", readonly=True)
    try:
        journal.verify()
        status = health(journal, now(), json.loads(source_bytes), config["interval_seconds"])
    finally:
        journal.close()
    h = status["scheduler"]
    if h["outcome"] != "completed" or h["overdue"] is not False or h["build"] != config["build"]:
        raise ValueError("A recent completed journal run from the installed build is required")
    current_boot = boot_epoch()
    from datetime import datetime
    if datetime.fromisoformat(h["last_started"]).timestamp() < current_boot:
        raise ValueError("No completed run after this boot")
    if args.after_reboot:
        receipt = json.loads((Path(config["data"]) / "install-receipt.json").read_text())
        if current_boot <= receipt["installed_boot"]:
            raise ValueError("Reboot after installation has not been demonstrated")
    return {"running": True, "after_reboot_verified": bool(args.after_reboot), "health": status}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "uninstall", "verify"])
    parser.add_argument("--data-dir", default=str(Path.home() / "Library/Application Support/SUNLIGHT"))
    parser.add_argument("--policy")
    parser.add_argument("--environment")
    parser.add_argument("--launch-agents-dir")
    parser.add_argument("--label", default="org.sunlight.watch")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--after-reboot", action="store_true")
    args = parser.parse_args()
    args._created = []
    os.umask(0o077)
    try:
        if sys.platform != "darwin":
            raise ValueError("macOS launchd is required; no installation attempted")
        if platform.python_implementation() != "CPython" or platform.python_version() != PIN:
            raise ValueError("CPython " + PIN + " is required; no interpreter fallback")
        result = {"install": install, "uninstall": uninstall, "verify": verify}[args.action](args)
        print(canonical(result))
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as exc:
        # Never dump subprocess output; it can contain registry/source credentials.
        reason = str(exc) if isinstance(exc, ValueError) else "Installation or verification command failed; state retained for diagnosis"
        print(canonical({"error": reason, "created_or_changed": args._created}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
