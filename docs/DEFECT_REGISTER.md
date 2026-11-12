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

- Recorded: 2026-11-10. Status: closed for the test path-comparison defect.
- Observed on CPython 3.12.14, macOS arm64, source c2ba06a:
  `test_failed_environment_creation_is_preserved_without_loading_agent` and
  `test_install_idempotent_and_uninstall_keeps_every_data_file` fail in
  `tests/test_watch_service.py` at lines 163 and 70 respectively.
- The installer resolves external paths. The assertions compare their original
  `/var/folders/...` strings with resolved `/private/var/folders/...` strings.
  This is evidence of a test portability mismatch, not evidence that launchd
  installation, restart or reboot persistence has been validated.
- Correction authorized by the owner: apply `Path.resolve()` to both actual
  and expected paths. The stderr assertion now compares the exact resolved
  log-file path rather than accepting a textual prefix. Environment-preservation
  assertions still require the expected resolved path in the created-path list.
  No runtime code or path protection changed.
- Verification: complete rebuild suite on 2026-11-10, CPython 3.12.14:
  2056 passed, 13 skipped, 0 failed, 17 passing subtests, 17.63 seconds.
  Skips and native service limitations remain explicitly open.
- Full measured results and exclusions: [Task 1 report](TASK1_RUNTIME_2026-11-10.md).

## RUNTIME-003: Pre-journal native verification lacks a structured failure

- Recorded: 2026-11-12. Status: closed on the development branch; the installed
  acceptance build remains unchanged. The owner approved the OS permission.
- Native launchd loaded the service, but macOS paused Python on its Documents
  access prompt before the journal was created. The verify command raised an
  uncaught `sqlite3.OperationalError: unable to open database file` instead of
  a structured not-started receipt.
- Evidence: Task 6 native installation record, TCC AUTHREQ_PROMPTING and absent
  journal at the first verification attempt. No healthy receipt was returned.
- Correction: catch the journal-open failure and report a safe
  not-started/unavailable state while still requiring an actual completed run
  from the live launchd PID for successful verification. OS permission must
  still be handled by the owner. This is diagnostic handling, not permission
  to treat a loaded process as healthy.
- Verification: the loaded-agent/no-journal test refuses without creating an
  empty journal. Complete backend: 2082 passed, 13 skipped, 0 failed on
  November 12, 2026. No process-liveness or completed-run assertion was removed.

## EVAL-001: stale reference sampling and incomplete historical provenance

- Recorded: 2026-11-12. Status: partially resolved, not fully closed.
- Cause established: c515bd8 wrote both numerical report versions with SQLite
  ORDER BY RANDOM(), outside the CLI seed's control. Commit 99991fa later
  introduced deterministic sampling. The docs/ copy was refreshed afterward;
  the reports/ copies retained the earlier measurements.
- Executed proof: the old general evaluator, given its archived 200 sample IDs
  and the current verified corpus, exactly reproduces all case details, metrics,
  confusion matrix, confidence intervals, PR curve and threshold sweep.
- DOJ limit: all ten positive case-detail records reproduce exactly, but the
  archived negative sample IDs and original execution receipt were not saved.
  That full historical result cannot be independently reconstructed. No finding
  that the report was fabricated or never run is supported.
- Public correction: both JSON and Markdown artifacts have dated stale notices
  and current measured figures beside the untouched historical contents.
  COR-001 records the stale-result and reproducibility correction.
- Remaining closure gate: recover the original DOJ negative draw with execution
  evidence or obtain an explicit author correction. Do not substitute a newly
  selected random draw or claim a proved original execution.
- Evidence: [history audit](EVAL001_HISTORY_2026-11-12.md) and the committed
  historical-code audit harness/receipt. No scoring or threshold change.
