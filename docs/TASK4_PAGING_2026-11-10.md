# Task 4: resumable source traversal

Read the source-policy checks, capture loop, journal state and replay tests,
d-portal's documented query semantics and the live response's generated SQL.
The Contracts Finder API documentation page returned HTTP 403 through the web
reader, so no undocumented rate allowance is claimed. Live pages supply their
own same-endpoint links.next cursor and enforce the 100-record page size.

Use the same capture and checkpoint code for the service and a bounded
historical import, retaining each page before moving its cursor. Backoff is
exponential and never shorter than a valid Retry-After, whether integer seconds
or an HTTP-date; a long server-directed delay is not capped to an earlier retry.

The source cursor, attempted URL, delay, failure count and receipts survive
process restarts. A failed request retains its cursor. Pagination cannot change
the source filters, endpoint path or origin. The d-portal query uses aid ordering
and explicit limit/offset; a full page always has a continuation, and mutable
offset results are not represented as a publisher-consistent snapshot.

`scripts/capture_watch_population.py` captures one reviewed cycle at a declared
pace. `--stop-after-pages` pauses only after the page checkpoint is committed;
restarting the command reuses that checkpoint. This is a controlled process
interruption, not a claim of survival through a crash during a SQLite commit.
The script records capture-only scheduler runs and does not produce analytical
findings or repeated full-population examinations during import. Normal service
ticks still examine the captured evidence. Persistent source/adapter failures
stop the import with its checkpoint intact rather than fabricating completeness.

Synthetic verification covers closed/reopened journals, a 429 between pages,
preserving the pending cursor, refusing early retry, HTTP-date parsing, repeated
offset continuation and explicit completion on an empty terminal page.
Focused paging and loop tests: 26 passed. Complete backend after this change:
2076 passed, 13 skipped, 0 failed, 17 subtests passed in 17.56s, November 10, 2026
in America/New_York. Skips remain the documented Docker/database/non-Mac gates.

## Observed full-month completion

The fixed October 1 to November 1, 2026 award query finished at
2026-11-11T03:52:23.767728+00:00 (November 10 in America/New_York).
It captured 28 pages, received and admitted 2,799 releases, and refused none.
All 28 HTTP receipts were 200. This run encountered no 429; the backoff proof
is the synthetic failure test, not an invented live rate-limit event.

The first process stopped after two committed pages. A second process began
at the exact saved continuation URL and completed the remaining 26 pages.
The completion receipt and checkpoint are retained in the external journal;
verification on November 12 confirmed its hash-chain head:
`1b9550e83d03391fc1d7024e38ab345286c7d3522dbf84ba29de3e4283bbfdac`.

Evidence is under the chat workspace's `outputs/task4/october-population/`,
with `first-process.log`, `resumed-process.log` and `month-policy.json` in
`outputs/task4/`. The aggregate report is `outputs/task5/october-population.json`.
This proves one completed traversal and a deliberate restart, not a consistent
snapshot guaranteed by the publisher or survival through a power loss.
