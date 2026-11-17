# SUNLIGHT measured scoreboard

Recorded November 13, 2026. Counts below describe their stated populations,
not field accuracy or continuous uptime. Evidence in draft PR #18 is linked
at its immutable commit because that work is not yet on main.

## Regime and notice coverage: FINDING #19

Frozen cohort: 96 award appearances, 94 distinct award IDs, 93 procurement
OCIDs; original query window November 12-14, 2026, journal sequence 868,
head `e00b1082eaab91ef7263ec5a3ff171bd8552b5cf034af37fd0496fd9bce2ed2d`.
Measured November 13, 2026.

| Measurement | Result |
|---|---:|
| PCR 2015 supported after cited primary-source enrichment | 9 / 96 |
| Procurement Act 2023 confirmed | 0 / 96 |
| Regime undetermined | 87 / 96 |
| Regime established from retained portal projection alone | 0 / 96 |
| Identifier links to parent framework/DPS notices | 6 / 96 (6.25%) |
| Corresponding award-notice matches in the measured search | 0 / 96 |
| Assessable under either proposed publication-order norm | 0 / 96 |

**Finding:** published award data on this portal does not establish which law
governs a record. The retained projection establishes none; identifier-linked
primary-source enrichment supports PCR for nine. The other 87 remain
undetermined, not presumed to fall under either regime. Six parent links do
not establish the corresponding award-publication event. Zero assessable is
a coverage finding, not evidence of non-compliance or all-time notice absence.

[Per-record evidence and search limits](https://github.com/rimodg/sunlight/blob/d04d18a6eb72f601abe2fa8842d406b7ca8c8e50/docs/NOTICE_REGIME_MEASUREMENT_2026-11-13.md)
and [task #19](https://github.com/rimodg/sunlight/issues/19).
The number did not move to an assessable rule because the legal scope and
required event pair are not established. [Task #20](https://github.com/rimodg/sunlight/issues/20)
measures a native central-platform contract-details rule next.

## Operational and verification baseline

| Measurement | Date and population | Result / limit |
|---|---|---|
| Records admitted | First elapsed day, Nov 12 09:38:16.817 to Nov 13 09:42:36.631 Eastern | CF 3,344; d-portal 297 appearances, including repeated captures |
| Explicit record refusals | Same first-day window | 0 for both sources; not proof all upstream records were observed |
| Failed source attempts | Same first-day window | CF 20; d-portal 21; 21 failed scheduler runs |
| Longest source reach gap | Same first-day window | Approximately 5h 13m 11s for both sources |
| Publication-to-detection latency | Nov 13 scoreboard baseline | Not yet aggregated; one new-publication proof exists, not a latency distribution |
| Backend tests, main baseline | Nov 12, 2026 | 2,090 passed, 10 skipped |
| Backend tests, invariant-core | Nov 13, 2026; draft PR #18 | 2,144 passed, 10 skipped, 0 failed; 17 subtests passed |

[First-day report and linked native receipts](https://github.com/rimodg/sunlight/blob/d04d18a6eb72f601abe2fa8842d406b7ca8c8e50/docs/WATCH_FIRST_DAY_2026-11-13.md).
No backend tests were rerun for this documentation-only scoreboard. The
invariant-core count is its recorded run, not a claim about current main.
Failure cause remains open in [WATCH-OPS-001, #21](https://github.com/rimodg/sunlight/issues/21).
No source migration is authorized by these counts; that is [proposal #22](https://github.com/rimodg/sunlight/issues/22).

## Section 53 coverage and implementation, November 13, 2026

[Issue #20](https://github.com/rimodg/sunlight/issues/20),
[draft implementation PR #24](https://github.com/rimodg/sunlight/pull/24).
The completed FTS update-window scan for November 12 00:00 through November 13
00:00 admitted 430 release rows and refused zero. Among 126 contract-details
releases, 150 contract/notice rows have both signature and publication dates:
45 flagged above threshold, 105 below threshold.

| Measurement | Result |
|---|---:|
| Contract/notice rows with both published date fields | 150 / 150 |
| Rows with admitted explicit contract-entry evidence | 0 / 150 |
| Legally assessable under the approved conservative scope | 0 / 150 |
| UNASSESSABLE | 150 / 150 |
| Full backend on rule-section53, Nov 13 | 2,193 passed, 10 skipped, 0 failed; 17 subtests passed |

**Why assessability did not move:** the signature field does not establish the
contract-entry event from which the law counts. The owner expressly prohibited
substitution. Signature-to-publication gaps range from 0 to 447 civil days;
these are plain measurements, not legal assessments. No live HOLDS or BREAKS
is claimed, and this does not close PR #18's first-assessable-real-rule gate.

[Source note, per-record results and verification at the measured commit](https://github.com/rimodg/sunlight/blob/75b02e0/docs/SECTION53_2026-11-13.md).
The adapter is implemented and tested but not deployed; the existing watch
source policy and service data were not changed.
