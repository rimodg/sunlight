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
