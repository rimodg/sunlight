# Chain of custody for results

Written November 24, 2026. Build step 4: every result carries the hash of its
source and the version of the rule that produced it.

## What a result now carries

Each row of `research/events_in_order_2026-11-18/results.json` (schema
`sunlight.events-in-order-results.v2`) carries:

- `custody.source`: the watch journal capture the row was computed from, as
  `capture_seq` and `capture_hash` (the journal's chain hash for that event).
  The capture event in the journal carries the SHA-256 of the original
  response bytes. That is the end of the chain; original bytes are not
  retained.
- `custody.rule_id` and `custody.rule_version_sha256`: the exact rule. The
  rule version is the SHA-256 over a typed block (`sunlight.custody.v1`)
  naming the rule module file and its SHA-256, the profile file, its schema
  and its SHA-256, and every source the profile cites with its locator and
  SHA-256. Any change to the rule code, the profile or a cited source changes
  the rule version.
- `result_sha256`: SHA-256 over the whole row, custody included. A changed
  state, reason, date or citation no longer recomputes.

The file carries the full `rule_version` block and `input_sha256` of the
pair export it replayed.

A result without a cited capture is refused, never stamped with a
placeholder. Missing is not zero.

## How to verify

From a checkout of the repository, reads only:

    PYTHONPATH=code python scripts/verify_custody.py \
      research/events_in_order_2026-11-18/results.json \
      research/events_in_order_2026-11-18/pairs.json

This recomputes the rule version from the files in the checkout, recomputes
every `result_sha256`, and checks that every distinct exported pair
(ocid, award id, award date, deadline) appears as exactly one row citing
the same capture as the pair export cites for it. A pair with no row, or
a duplicated row standing in for a dropped one, is a problem even though
the count still matches. Exit 0 means every link holds; the output lists
any problem by row.

With the watch journal, opened read-only (`sqlite3` URI `mode=ro`), the
check continues into the journal:

    PYTHONPATH=code python scripts/verify_custody.py RESULTS PAIRS --journal JOURNAL.sqlite3

For each of the 25 distinct cited captures the journal row at that sequence
must be a capture with the same chain hash, that hash must recompute
from the row's own parts the way the journal writes them (event id over
kind, time and payload; chain hash over id and previous), and the payload
must carry an original response SHA-256. A payload rewritten under an
unchanged stored hash is therefore refused. Work on a copy of the journal
if in doubt; the check never writes.

The rule version a results file carries names the profile the replay used.
`scripts/measure_events_in_order.py` builds it from the profile path given
on the command line, which must be inside the repository, so a run with
another profile cannot claim the committed rule's version; `replay()`
called without a rule version refuses any profile but the default one.

`tests/test_custody.py` (19 tests) covers the module and checks the
committed results against the rule in the checkout on every test run, so a
change to `code/events_in_order.py` or the profile without a regenerated
results file fails the suite.

Schema v3 of both files, later the same day, adds a `watcher` block to
every row before the custody stamp; see
[SEALED_WATCHERS_2026-11-24.md](SEALED_WATCHERS_2026-11-24.md). The custody
block and `result_sha256` rules above are unchanged.

## What did not change

The 193 outcomes are identical to the schema v1 file (commit 8cb4d46):
119 CONSISTENT, 5 INCONSISTENT, 60 UNASSESSABLE, 9 NOT_APPLICABLE, same
reasons, same day gaps. `tests/test_custody.py` pins the SHA-256 of the
outcome tuples. The rule itself, `code/events_in_order.py`, is untouched by
this step.

## Limits

- A matching hash proves the same bytes were used. It does not authenticate
  a publisher, prove a source claim, or turn an indicator into an allegation.
- The rule version names repository files. A verifier needs the same
  repository state; the file-level `rule_version` block records which.
- The watch's own examinations already carry their chain (build identity,
  capture SHA-256, projection SHA-256, result SHA-256, packet replay in
  `code/watch_packet.py`). This step does not change them.
- Section 53 results cite a capture file, not the watch journal, because the
  measurement of November 13 was an isolated capture (see below). The chain
  ends at the same place as the journal chain: the SHA-256 of the original
  response bytes, which are not retained.

## Section 53 results, stamped November 24

Each row of `research/section53_2026-11-13/adapter-run/results.json` (schema
`sunlight.section53-results.v2`, 150 rows) now carries the same custody block
with a different source kind:

- `custody.source`: the page of the committed capture file the row was
  computed from, as `capture_file` (`research/section53_2026-11-13/adapter-run/capture.json`),
  `page`, the page's `source_sha256` (original response bytes) and
  `projection_sha256` (the protected projection kept in the capture file).
  A verifier recomputes the projection hash from the capture file; the
  original bytes are not retained, so `source_sha256` is reported, not
  reverified.
- `custody.rule_id` `section53` and `custody.rule_version_sha256` over
  `code/section53.py`, `config/section53-profile.json` and the two sources
  the profile cites (section 53 of the Procurement Act 2023 and the
  commencement regulations, each with its SHA-256).
- `result_sha256` over the whole row, custody included.

The file carries the full `rule_version` block. The 150 outcomes are
identical to the schema v1 file (commit 39d1f48): 150 UNASSESSABLE, same
findings, same day gaps. `tests/test_section53_custody.py` pins the SHA-256
of the rows without their custody. `code/section53.py` and the profile are
untouched by this step.

To verify, reads only:

    PYTHONPATH=code python scripts/verify_section53_custody.py \
      research/section53_2026-11-13/adapter-run/results.json \
      research/section53_2026-11-13/adapter-run/capture.json

This recomputes the rule version and every `result_sha256`, and checks every
row cites a page that exists in the capture file with the same page hash and
a projection hash that recomputes. Exit 0 means every link holds.
`scripts/verify_section53_evidence.py` still replays the capture and
compares it to the committed results, custody included.

A source reference is one kind or the other, with every part present. A
reference carrying parts of both kinds, or any extra part, is refused.
