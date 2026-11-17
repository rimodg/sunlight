# Watch operational report: first full day, November 13, 2026

**The elapsed-day measurement is complete; uninterrupted successful capture
is not demonstrated.** There were 21 failed scheduler runs and a longest
observed source reach gap of about 5 hours 13 minutes. Both sources later
recovered. The service and its configuration were not changed during this
measurement, and no manual tick or restart was used.

All readable local times below use America/New_York (Eastern, UTC-05:00).
Exact UTC instants and journal heads are retained in the linked receipts.

## First full-day window

The initial completed run was **November 12 at 09:38:16.817 Eastern**.
Twenty-four hours elapsed at November 13 at 09:38:16.817. The first subsequent
completed run was **November 13 at 09:42:36.631**, so this report covers
**24 hours, 4 minutes, 19.814 seconds**. Receipts include the initial run's
source requests. An earlier measurement at 00:17 Eastern was an interim
report; it was not represented as a completed day.

[First-day summary](../reports/native-2026-11-13/first-day-summary.json):
journal sequence 1422, head
`acb935d41f559ae309fa425902cde1f6ad63055d042add871949675d14ddce9f`.

| Measurement | Result |
|---|---:|
| Completed scheduler runs | 241 |
| Failed scheduler runs | 21 |
| Failure reason recorded | source_failure, all 21 |
| Maximum scheduler-start gap | 416.979 seconds (6m 56.979s) |
| CF successful page captures | 40 |
| CF unavailable attempts | 20 |
| CF admitted record appearances | 3,344 |
| d-portal successful page captures | 33 |
| d-portal unavailable attempts | 21 |
| d-portal admitted record appearances | 297 |
| Explicit record refusals | 0 for both sources |
| Existing-record revision proofs | 0 |

Capture counts are pages; appearance counts include repeated observations.
A completed scheduler run can perform an examination without reaching a
source that is not yet due. Neither number is an uptime percentage or a count
of distinct contracts/activities.

## Failures and silence

The unavailable receipts record no HTTP status or successful reach time. They
establish failure to reach/capture in this service, not that the upstream
websites were down. The journal does not retain the underlying network
exception, so these receipts do not establish the transport failure's root
cause. There were 41 unavailable source attempts across the 21 failed runs.
Backoff reached 7,680 seconds (128 minutes); later completed scheduler runs
must not conceal the absence of fresh source observations during that wait.

The longest closed reach gap was:

- CF: **November 12, 20:05:45.361 to November 13, 01:18:56.384 Eastern**,
  18,791.022 seconds, approximately **5h 13m 11s**.
- d-portal: **November 12, 20:05:46.381 to November 13, 01:18:57.654 Eastern**,
  18,791.273 seconds, also approximately **5h 13m 11s**.

The complete failed receipts and the bracketing successful receipts are in
`outputs/notice-measurement-2026-11-13/watch-failure-detail.json`, outside Git.
Their absolute location, size and hash are in the
[artifact manifest](../research/notice_measurement_2026-11-13/external-artifacts.json).
This measures time between observed reaches, not continuous knowledge of
source availability or proof that no publication occurred during the gap.

At the first-day cutoff, CF was last reached at **09:35:37.056**, giving
**419.575 seconds** of silence; d-portal was last reached at **09:29:35.262**,
giving **781.368 seconds**. These are cutoff-specific values, not current ages.
The later successful reaches do not erase the overnight gap.

## Reboot and interruption

The owner-authorized actual reboot remains independently established by the
[November 12 receipt](../reports/native-2026-11-12/reboot-verification.json).
Boot time advanced to **14:13:39 Eastern**. The old service PID was 3399 and
the automatically started post-login service PID was 1155.

The [recorded interruption window](../reports/native-2026-11-13/reboot-window.json)
shows:

- Last pre-reboot completion: **14:09:52.789 Eastern**.
- First post-reboot scheduler start: **14:16:41.401 Eastern**.
- First post-reboot completion: **14:16:56.171 Eastern**.
- Gap between those completions: **423.381 seconds (7m 3.381s)**.
- Boot to first completed service run: **197.171 seconds (3m 17.171s)**.

Shutdown and login timestamps were not recorded, so exact service downtime
cannot be derived from these receipts. The 7m 3s completion gap brackets the
interruption; it is not an exact downtime assertion. This proves the observed
start-at-login event, not pre-login daemon service or guaranteed future boots.

## Later cutoff and current native check

The [later summary](../reports/native-2026-11-13/latest-summary.json) through
**12:02:24.705 Eastern** spans 26h 24m 7.888s: 264 completed runs, the same
21 failed runs, 48 CF captures/20 unavailable attempts, and 38 d-portal
captures/21 unavailable attempts. Both sources were reached at about
**12:01:38 Eastern**. No failed attempt has been relabelled as successful.

Two native verification attempts rejected the recent-completed-run guard.
Those attempts are retained in the
[verification-attempt record](../reports/native-2026-11-13/verification-attempts.json).
A subsequent check after a naturally scheduled completion exited 0 at
**12:09:51.211 Eastern** and reported `running: true`,
`after_reboot_verified: true`, PID **1155**, and the matching installed build.
The [successful native receipt](../reports/native-2026-11-13/native-verification.json)
shows a completion at 12:08:40.363, with neither source marked overdue.
This later pass does not erase the failed checks or prove continuous liveness.

Installed identity throughout the recorded period:

```text
git:    5a224c86a88408b7cb19564a2e6582bb425fb539
Python: 3.12.14
source: 324cd5431e2e86d5422a0bb3eb19c7c06192b4f0031f3a17f7163ac89ef325de
lock:   2b7343dce9882b86f1da44576cde46863ebaa1114f44e1818e533b406662827b
```

## Publication detection and acceptance statement

The previously established newly-published-notice proof is preserved in the
[publication receipt](../reports/native-2026-11-12/publication-verification.json).
It is a newly published notice detected between completed source cycles,
not an edit to an existing notice. The reporter's stricter
`published_change_proofs` field counts existing-record revisions and remains
zero. The two proof types have not been conflated.

Task 6 now has its requested full-day operational report, alongside its actual
reboot/login and new-publication evidence. The elapsed-day reporting gate is
complete. Reliability concerns remain open as WATCH-OPS-001: the long reach
gap, failed source attempts and intermittent native verification rejections
require diagnosis before claiming dependable continuous coverage. This turn
measured them and made no runtime, source-policy or service change.
