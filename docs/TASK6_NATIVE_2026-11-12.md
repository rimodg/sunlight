# Task 6: running native service and pending full-day acceptance

Read the native installer, startup verifier, loop, health receipts, Docker build
manifest and version tests first. Install the tested build from a detached
worktree so later documentation commits cannot relabel or invalidate it; start
the acceptance clock only when this launchd process records a completed run.

## Version without Git

Executed the actual FastAPI `/version` route with TestClient in a separate
package containing application source and a generated build manifest, with no
`.git` directory. It returned HTTP 200 and `packaged_files_match`, not
`unversioned`, under the locked CPython 3.12.14 runtime. The existing rebuild
already implemented this behavior; no replacement implementation was needed.

The declared revision was `5a224c86a88408b7cb19564a2e6582bb425fb539`.
The packaged source digest was
`7fe26ae10d8e4a76c7d6c564f19cb0392882a6895ba5b035a4a857ab69711b71`.
This is a local no-Git API execution, not an executed Docker image or a deployed
Render verification. The manifest proves content equality, not authentication.
Evidence is `outputs/task6/no-git-version.json` in the chat workspace.

## Native installation

The installer exited 0 and launchctl reported the owned LaunchAgent loaded.
The detached source checkout is `sunlight-watch-service-5a224c8` in the chat
workspace, with the external locked environment `runtime-3.12.14`.
Data is in the user's `Library/Application Support/SUNLIGHT/watch-live-sources-20261112`.
The label is `org.sunlight.watch`. No deployed service was changed.

The reviewed policy enables a bounded Contracts Finder award window from
November 12 to November 14, 2026 and the nine-activity d-portal reporter
`GB-COH-1869600`. The scheduler polls every 300 seconds, at most one page per
source per poll, and waits 1,800 seconds after each completed source cycle.
This explicitly scoped acceptance feed is not all procurement or all aid.
The fixed date window must be reviewed before use beyond this acceptance run.

Installed build source SHA-256:
`324cd5431e2e86d5422a0bb3eb19c7c06192b4f0031f3a17f7163ac89ef325de`.
It differs from the API package fingerprint because the service has its own
explicit source-file inventory. Exact Python patch `3.12.14` is recorded in
`install-receipt.json` and verified with the package lock at startup.

## Observed blocker, 2026-11-12 14:36 UTC

macOS paused the Python process while requesting Documents-folder access.
The TCC system log reports `AUTHREQ_PROMPTING` for
`kTCCServiceSystemPolicyDocumentsFolder`, subject the uv CPython executable,
PID 3399. launchctl reported that PID as running, but the journal did not yet
exist and both service logs were empty. Loaded does not mean capturing.
The verification attempt failed with `sqlite3.OperationalError: unable to open
database file`; it did not return a healthy-service receipt.

The owner was asked to approve the actual macOS prompt. The assistant did not
change privacy settings or move execution to evade the permission request.
Until a completed scheduled run is verified, no 24-hour period, capture count,
source-silence measurement or genuine before/after change is claimed.
The post-approval acceptance report must include all of those; this document
is an installation/blocker record, not Task 6 closure.

The last complete backend result remains 2,078 passed, 13 skipped, 0 failed,
17 passing subtests. Subsequent changes are proof helpers and documentation;
the live identity helper and no-Git API route were executed separately.
Native reboot survival and the exact-database reference evaluators remain
unverified. No reboot was performed.

## Owner approval and first scheduled capture

The owner approved the macOS prompt. Native verification then exited 0 at
2026-11-12T14:38:24.427149+00:00, confirming the running launchd PID 3399
matches a recent completed journal run from the installed build.
The first run finished at `2026-11-12T14:38:16.817244+00:00` and admitted
72 Contracts Finder records and nine d-portal activity records, with no refusals.
Both sources were reached successfully. The receipt is
`outputs/task6/post-approval-verify.json`. The earlier permission blocker is
resolved; it is preserved above as observed installation history.

The earliest full-day completion is November 13 at 09:38:16 Eastern, after a
scheduled completion at or beyond that point. Elapsed wall time alone does not
prove uninterrupted uptime; any scheduler gaps and source silence must be
reported. No published before/after change has yet been demonstrated.

`scripts/report_watch_run.py` reports completed-run elapsed time, source capture
and admission occurrence counts, per-field refusal reasons, last reach and
maximum reach gaps, scheduler gaps/failures, and recorded build identities.
It retains before/after proof only across completed source cycles, for an
existing stable record key whose organizational projection and publication time
advance, with the new observation explicitly noticed in an examination.
Initial discovery, changed page positions and older versions disappearing do
not satisfy this gate. An update without an advancing publisher timestamp is
not automatically claimed by this conservative proof helper.

Run the report against the service journal and save it outside the checkout;
run the native verifier from the installed detached checkout separately for a
current process-liveness receipt. Do not substitute a manual tick for launchd.
The initial report is `outputs/task6/run-report.json`, with full_day_elapsed false
and zero published-change proofs.

The pre-journal verifier diagnostic was corrected on the development branch:
a missing/unopenable journal now raises a structured failure without creating
an empty journal or weakening the live-PID/completed-run checks. The installed
service remains on the immutable `5a224c8` build; this diagnostic-only change
was not deployed into the running acceptance period.

Complete backend after the reporter and diagnostic correction, November 12,
2026: **2,082 passed, 13 skipped, 0 failed**, 17 passing subtests, 18.37 seconds.
Evidence: `outputs/task6/backend-tests.log` and `backend-tests.xml`. Three new
reporter tests cover elapsed-day boundaries, exact refusal reasons, false page
movement, first-discovery exclusion and the requirement for a recorded change
notice. One new native-verifier test refuses a loaded agent without a journal.
The documented Docker, reference-database and non-Mac skip gates remain open.
