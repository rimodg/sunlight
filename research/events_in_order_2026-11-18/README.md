# Events in order: distinct award/deadline date pairs

Measured export, November 18, 2026. This is a measurement, not a rule.
Every row is a risk indicator input, never an allegation. No organisation
is named or assessed here.

## How the export was made

- Source: the operator watch journal, opened read-only
  (`sqlite3` URI `mode=ro`). The running watch service, its config and its
  data directory were not touched.
- Repository revision at export: `2618c0b` (main). Runtime: CPython 3.12.14
  from the lock-exact sibling test environment. No code was changed.
- Every `capture` event was read in journal sequence order. For each
  retained OCDS record carrying at least one `awards[].date` and a
  `tender.tenderPeriod.endDate`, one pair was formed per dated award.
- Pairs were deduplicated on the exact tuple
  `(ocid, award id, award date, tender endDate)`. Each distinct tuple cites
  the journal `seq` and `hash` of the capture where it first appeared, plus
  that capture's source URL. Later repeat captures of the same tuple are
  counted in the appearance totals but not exported again.
- Both date values were parsed as ISO 8601 timestamps. All parsed; zero
  unparseable values. Ordering uses civil dates as published (see the
  midnight note below).
- The export was scanned for email-shaped content before writing; none.

## Journal head at export

- seq: `5436`
- hash: `098778b5d85bb3ed0d2ecf0912d0b651573898bcea4366e0886e6d0f47a0c6f8`
- kind: `scheduler_completed`, at `2026-11-18T19:49:11.190636+00:00`

The journal is live. Counts below are the export-time read.

## Counts

Export-time read (head seq 5436):

| Measurement | Result |
|---|---:|
| Total captured record appearances | 28,894 |
| Appearances with both date fields (all comparable) | 27,103 |
| Distinct (ocid, award id, award date, endDate) tuples | 193 |
| Distinct tuples with award date before deadline (civil) | 10 |
| Before-deadline appearances (civil) | 1,322 |
| Same-civil-day appearances, not counted as before | 6,657 |

An earlier read the same day, before the journal grew, measured 28,794
appearances, 27,003 with both fields, 1,315 before and 6,638 same-day.
The distinct set was identical: 193 tuples, 10 before. The difference is
new repeat captures arriving between the two reads, not new distinct
pairs. Missing is not zero; the aid-activity records in the journal carry
no OCDS date fields and are outside this population.

## Midnight note

Every award date in this population serializes as midnight (00:00:00),
while tender deadlines carry real times of day (for example 12:00, 17:00,
23:59). The award time of day is therefore not published information.
Ordering compares civil dates only: an award on the same civil day as the
deadline is not counted as before it. An instant-level comparison would
count 7,549 appearances as before at the earlier read, but that treats the
midnight placeholder as a real award time, so it was not used.

## Fields included (organisational only, when present)

`ocid`, `award_id`, `award_date` (`awards[].date`), `tender_end_date`
(`tender.tenderPeriod.endDate`), `procurement_method`
(`tender.procurementMethod`, a fixed enum: open, selective, limited,
direct; present in 168 of 193 pairs, absent means not supplied),
`publication_date` (release `date`), `award_date_published`
(`awards[].datePublished`), `source_url`, `capture_seq`, `capture_hash`.

In `results.json` (schema v2 since November 24, 2026) `capture_seq` and
`capture_hash` live inside each row's `custody.source` block, next to the
rule version that computed the row; see `docs/CHAIN_OF_CUSTODY_2026-11-24.md`.
Schema v3 (same day) adds a `watcher` block to each row: the procurement
method as read from the pair and the sealed selection row that held; see
`docs/SEALED_WATCHERS_2026-11-24.md`. Schema v4 adds a file-level `roster`
block naming the hashed list of watchers the file was produced under; no row
changed; see `docs/ROSTER_2026-11-24.md`. `inbox.json` beside this file is the
decision inbox built from `results.json`: the five INCONSISTENT rows, each with
what was read and what the rule said, waiting for a person; see
`docs/DECISION_INBOX_2026-11-24.md`.

## Fields left out, and why

- Requested but never retained by the projection:
  `tender.procurementMethodDetails` and any notice type or tag. The
  organizational projection does not store them, so they cannot be
  exported. Their absence here is not evidence they were absent at source.
- Party identifiers (`buyer`, `parties`, `awards[].suppliers`): excluded.
  They are organisational identifiers but were not requested, and party
  blocks are the likeliest place for personal-shaped content.
- Monetary values, tenderer counts, contract periods: not requested, not
  exported.
- Names of people, emails, free-text descriptions: none are retained by
  the projection at all. Contact fields are discarded in memory at
  capture, and personal-shaped content inside an allowed field refuses the
  record before persistence. Nothing of that kind is in this export.

Publication fields are carried exactly as published; no consistency
judgement is made about them (for example, an award's `datePublished` can
precede its `date` in the source data).