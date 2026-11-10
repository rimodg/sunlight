# Defect register

## RUNTIME-001: Interpreter patch pin couples installation to a download catalogue

- Recorded: 2026-11-10, by owner instruction following the capability audit.
- Status: installation unblocked; installer policy correction remains open.
- Defect: requiring one CPython patch release was a mistake. The package lock
  pins the application dependencies. Requiring a particular interpreter patch
  also makes installation depend on the available toolchain download catalogue.
- Evidence: uv 0.9.18 refused `uv python install 3.12.14` with
  `No download found for request: cpython-3.12.14-macos-aarch64-none`.
  After `uv self update` installed uv 0.13.7, the same request installed
  CPython 3.12.14 successfully. All 35 requirements.lock pins then installed
  with `--no-deps --only-binary=:all:` on this Mac.
- Owner's standing rule: "pin the minor version, verify the patch, never require it."
  Record the selected exact patch in the service receipt and verify it at every
  start. A different installed patch must not silently replace the recorded
  runtime. Locked packages and backend tests must validate the selected runtime;
  a package lock alone is not proof of identical behavior across interpreters.
- Current decision: use the successfully installed CPython 3.12.14 and leave
  the existing installer pin unchanged, as explicitly instructed for this
  outcome. This resolves today's catalogue blocker, not the policy defect.
- Closure: a separately validated installer change accepts CPython 3.12.x,
  records the exact selected patch, verifies it at every service start, and
  demonstrates lock installation and backend acceptance on that runtime.

## RUNTIME-002: Native Mac service tests compare unresolved and resolved paths

- Recorded: 2026-11-10. Status: open; blocks a green rebuild backend suite.
- Observed on CPython 3.12.14, macOS arm64, source c2ba06a:
  `test_failed_environment_creation_is_preserved_without_loading_agent` and
  `test_install_idempotent_and_uninstall_keeps_every_data_file` fail in
  `tests/test_watch_service.py` at lines 163 and 70 respectively.
- The installer resolves external paths. The assertions compare their original
  `/var/folders/...` strings with resolved `/private/var/folders/...` strings.
  This is evidence of a test portability mismatch, not evidence that launchd
  installation, restart or reboot persistence has been validated.
- No test, runtime code or path protection was changed to hide the failures.
  Resolve the path expectations without weakening the path checks, then rerun
  the service tests and complete backend suite. Later assertions may expose
  further mismatches once these first failures are corrected.
- Full measured results and exclusions: [Task 1 report](TASK1_RUNTIME_2026-11-10.md).
