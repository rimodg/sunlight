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
- Section 53 results (`research/section53_2026-11-13/adapter-run/results.json`)
  carry the original response SHA-256 per row but not yet a rule version.
  Stamping them with `code/custody.py` is the next part of this step.
