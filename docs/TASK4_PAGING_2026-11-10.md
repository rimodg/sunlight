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

Live full-month and interrupted-resume evidence will be appended after the run;
this implementation record alone does not close those acceptance gates.
