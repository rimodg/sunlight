# Tasks 2 and 3: organizational projection and retention

## Read first and design

Read both adapters, the journal writer, replay and packet paths, source-health
receipts, rule input-basis checks and existing watch tests. Read d-portal's
[query documentation](https://docs.d-portal.org/en/latest/d_query/) and its
linked [query reference](https://github.com/notshi/dquery/blob/master/readme.md),
then inspected the live q response and its generated dquery SQL.

Project a declared organizational field set before admission, retaining only
safe values and fixed refusal reasons. Replay the projection with the matching
adapter and rule build, while treating the original-byte digest as a source
fingerprint whose bytes are not retained.

The storage work in Task 3 was necessary in this same change: leaving the old
writer in place would retain the very contacts Task 2 excludes. No original body
is written to a journal, log, packet or fixture by the new capture path.

## Explicit projection contract

`watch_projection.py` declares these nested schemas; unspecified keys are never
copied into the admitted record:

- Contracts Finder: ocid and release ID; release date; buyer and supplier local
  IDs plus published identifier scheme/ID and additionalIdentifiers; tender and
  award amounts/currencies; procurement method; tenderer count; award ID and
  date/datePublished; tender and contract period start/end dates.
- Only the literal buyer, supplier and tenderer roles are retained to associate
  identifiers with the source's organizational roles. No arbitrary role text,
  organization name, person name, address, narrative, document or contact data
  is retained. Roles are structural selectors, not name-based identity.
- d-portal: aid, reporting_ref, and updated_at if supplied. The live reviewed
  query requests aid and reporting_ref; its missing updated_at remains a gap.
- Source and projection metadata: source URL, adapter version, original-response
  SHA-256, projection SHA-256, policy hash and capture time. Original bodies and
  rejected values are absent. A digest is not an authenticity certificate.

The first exploratory probe accidentally included tender.id, which is not in
the owner's declared field set. It refused 26 of 100 rows for that field's
identifier shape. tender.id was removed from the allowlist, not normalized or
admitted by weakening validation. The final proof below uses the corrected
field set. The earlier probe remains in local evidence as an exploratory result.

Allowed fields remain type-checked and admitted; personal-shaped or invalid
values refuse the record. Refusals contain the row index, a schema-derived field
path and a fixed reason, never a source value. Other valid records on the page
can be admitted. The scheduler and health view expose admitted counts and
refusals, so partial coverage is visible.

Every observation carries mapped fields, absent fields with reasons, declared
exclusions, publisher/service identity, adapter version, source version when
provided and the source contract it was written against. A missing field means
not supplied in this record or query, not that the publisher is incapable of
publishing it. Population completeness remains unknown after a single page.

Excluded review-body roles cannot become evidence of an absent review body:
PROC-003/004 are unassessable on these projections. Existing TCA rules and their
citations are unchanged. GB-CFS local identifiers are retained as GB-CFS and
remain unresolved by the registry resolver; they are never relabeled GB-COH.

## d-portal query verified from its response

The live q endpoint returned aid and reporting_ref, together with generated SQL
of this form:

```sql
SELECT aid, reporting_ref FROM act
WHERE reporting_ref LIKE 'GB-COH-%'
ORDER BY aid LIMIT 2 OFFSET 0
```

The final probe used limit=100, offset=0 and orderby=aid. A full page produces an
offset continuation; a returned full page is not mistaken for completion.
Offset traversal is not a frozen publisher snapshot and can drift if rows change
mid-traversal. Full-month/resume and rate-limit acceptance belong to Task 4.

## Observed live proof

Executed November 10, 2026 in America/New_York; the receipt timestamp is
2026-11-11T03:40:16.070964+00:00. Command:

```sh
python scripts/probe_watch_sources.py --policy /absolute/reviewed-probe-policy.json --data-dir /absolute/fresh-probe-directory
```

The script uses the real watch loop, real adapters, journal and full procurement
reader, then replays a portable projection packet. It writes only projections,
safe metadata and summaries outside the repository. No default service source
was enabled.

| Source scope | HTTP | Received | Admitted | Refused | Next page |
| --- | ---: | ---: | ---: | ---: | --- |
| Contracts Finder, 2026-10-01 through 2026-11-01, awards, limit 100 | 200 | 100 | 100 | 0 | pending |
| d-portal act, GB-COH reporters, aid/reporting_ref, limit 100 | 200 | 100 | 100 | 0 | pending |

Projection packet replay passed. This is one-page acceptance, not a population
run, a cross-source identity proof or unattended-change acceptance.

Source code fingerprint used:
`5b535e694f7211401b4cb375e2de88f56f8b8f14d1d5167089c7669286f0451b`.
The probe ran against uncommitted code based on 14594d9; the fingerprint, not that
base revision alone, identifies the tested code. The subsequent commit preserves
this implementation. Runtime was CPython 3.12.14 with the exact 35-package lock.

## Storage and reproducibility, Task 3

| One page | Original response bytes, counted in memory | Retained projection bytes | Full capture payload bytes |
| --- | ---: | ---: | ---: |
| Contracts Finder | 639571 | 261762 | 262312 |
| d-portal | 5533 | 71182 | 71697 |

The CF projection is about 59.1% smaller. The d-portal projection is about 12.9
times the minimal source response because every record carries coverage and
provenance metadata. These are canonical JSON byte counts, not claims of equal
SQLite-file savings: observations, examinations, indexes and journal overhead
consume additional space. No optimization claim is made for the entire journal.

Replay now means reproducing the same examination from the same retained
organizational projection, adapter version, policy and rule build. It does not
recreate original whitespace, excluded narrative, contacts or the source body.
The original digest can only be reverified if an original is independently
obtained. No extra raw field proved necessary for replay.

The capture route returns the projection with X-Content-SHA256 for those bytes
and X-Source-SHA256 for the original-response fingerprint. Packet schema v2
states the limit. Legacy body-bearing captures refuse replay pending explicit
migration; existing state is not deleted or silently rewritten.

## Verification and remaining gates

Focused privacy, coverage, journal, loop, packet and API tests passed, including
checks for excluded personal text in SQLite files and packet exports, allowed
field refusals, partial-page accounting, unknown versus zero, source locators,
internal scheme separation and no-network replay.

Complete backend: **2073 passed, 13 skipped, 0 failed**, two dependency warnings,
17 passing subtests, 18.73 seconds. Skips remain nine unavailable Docker tests,
three absent-production-database tests and one non-Mac-host test on this Mac.
The full command was `PYTHONPATH=code:tests python -m pytest tests/ -q -ra`
with a separate JUnit XML output path. Local outputs/task2 retains logs, XML,
safe live journal, packet, policy and summary.

Task 4 full-month capture/resume, Task 5 live identity and Task 6 unattended
acceptance remain open. No service was installed by this probe.
