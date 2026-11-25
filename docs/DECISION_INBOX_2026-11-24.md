# The decision inbox

Written November 24, 2026. Build step 5, third part: where a result that
needs a person's judgement waits, with what was read and what the rule said,
so people decide and the system never does.

## What the inbox is

A results file is the rule's answer on every record. Some answers are risk
indicators a person must look at. The rule has already said what it read and
what it found; what follows is a human decision. The inbox is the list of
those rows, built from one results file and the inbox policy.

`config/inbox-policy.json` (schema `sunlight.inbox-policy.v1`) says, per
rule:

- `record`: the fields of a result row that name the record (for
  `events_in_order`: `ocid`, `award_id`; for `section53`: `ocid`,
  `release_id`, `contract_id`).
- `state_path` and `reason_path`: where the rule's state and reason are read
  from a row (`state` and `reason` for events-in-order;
  `assessment.finding.state` and `assessment.finding.reason` for section 53).
- `waits`: the states that wait for a person, each with the question put to
  the person. As committed: `INCONSISTENT` for `events_in_order` and `BREAKS`
  for `section53`. Both questions ask what, if anything, follows: a
  correction to seek from the publisher, a note on the record, or no action.

Rules are ordered by `rule_id` and `policy_sha256` is the SHA-256 over
everything else. `code/inbox.py` reads the policy part by part and refuses
any missing, malformed or extra part, unordered rules, duplicated states, or
a hash that does not recompute. A state not on the policy does not wait; it
is counted, never dropped. The policy is the owner's table, not the code's
opinion: widening it (for example, to make `UNASSESSABLE` wait) is one
edited line, resealed with `scripts/seal_inbox_policy.py`, and the inboxes
are rebuilt so they name the new policy.

## What an inbox carries

`build_inbox` walks the rows of a results file in the order the file carries
them. For each row it checks the custody stamp recomputes, that the row was
computed by the file's rule, and that the watcher's selection is present. A
row the watcher did not select is counted under `rule_did_not_run`: the rule
gave no answer, so nothing can wait. A row whose state the policy names
becomes an item; any other state is counted under `not_waiting`. The inbox
(schema `sunlight.inbox.v1`) carries:

- `results_file` (repository-relative path) and `results_file_sha256`, the
  results schema, the rule id and rule version, the watcher id and seal, and
  the file's `roster` block, copied, so an inbox names the same roster its
  results file does.
- `policy`: the policy file, the SHA-256 of its bytes and `policy_sha256`.
- `rows`, `rule_did_not_run`, `not_waiting` (counts by state, ordered) and
  `waiting`. The four add up to `rows`; an inbox whose counts do not is
  refused.
- `items`, one per waiting row, in results order: `position` (the row's
  index in the results file), `result_sha256`, `record` (the keys the policy
  names), `read` (the row's watcher block: every fact read, which were
  missing or unreadable, and the selection row that held), `said` (state and
  reason), `question`, the `row` itself with its custody stamp and
  `result_sha256`, and `item_sha256` over the rest.
- `inbox_sha256` over everything else.

Nothing in `code/inbox.py` decides. A row is listed because its state is on
the policy, never because anything weighed it. An item carries the row
verbatim, so every custody, lens and roster check that holds for the results
file holds for the item. Missing is not zero: the inbox says how many rows
the rule did not run on and how many are in each state that does not wait,
and an empty inbox says so with those counts beside it rather than silence.
A result is a risk indicator, never an allegation; whether a procurement
should have happened stays with people, and the inbox holds no decision
field at all. Recording decisions is the action log, the next step.

## The two inboxes as committed

`research/events_in_order_2026-11-18/inbox.json`: 193 rows, 0 the rule did
not run on, not waiting: 119 CONSISTENT, 9 NOT_APPLICABLE, 60 UNASSESSABLE;
5 waiting, the five INCONSISTENT rows (positions 19, 20, 23, 135, 173 of the
results file). `inbox_sha256`
`dd1032bcc576e585efd90ef2f9f50c639e3b02e1de9f9e690c7410b4efd88d82`.

`research/section53_2026-11-13/adapter-run/inbox.json`: 150 rows, 0 the
rule did not run on, not waiting: 150 UNASSESSABLE; 0 waiting. No row
reached HOLDS or BREAKS, so nothing waits, and the inbox says so with the
150 counted beside it. `inbox_sha256`
`b30b33df13c2821d2c18c1eb78d83628d842af8e3786f1ef6fff02c44d125b94`.

`policy_sha256` is
`0a4b923f60ee7a616f213f4c87131d15db7a4ffe4b8f56149776b2479f41bbeb`.
Both results files are unchanged: every row, custody stamp and
`result_sha256` included, is what the schema v4 files carried;
`tests/test_inbox.py` pins the digests of both row lists again.

## How to build and verify

Build, from a checkout (writes only the output named, refuses an existing
one, and requires the results file to be inside the repository so the inbox
can name it by relative path):

    PYTHONPATH=code python scripts/build_inbox.py \
      research/events_in_order_2026-11-18/results.json OUT.json

Verify, reads only:

    PYTHONPATH=code python scripts/verify_inbox.py \
      research/events_in_order_2026-11-18/inbox.json \
      research/section53_2026-11-13/adapter-run/inbox.json

For each inbox this checks every part and recomputes `inbox_sha256` and
every `item_sha256`; reads the results file the inbox names from the
checkout and compares its bytes; rebuilds the inbox from that file and the
checkout's policy and compares part by part, naming any row that waits under
the policy but is not listed, any listed row that does not wait, and any
item or count that differs; and checks the results file's roster reference
against the roster in the checkout and the watcher it names. Exit 0 means
every link holds.

To reseal the policy after editing it (prints, writes nothing):

    PYTHONPATH=code python scripts/seal_inbox_policy.py > config/inbox-policy.json

`tests/test_inbox.py` (48 tests): every missing, malformed or extra part of
the policy and of an inbox is refused; both hashes are stable across
locations and move with every part; the built inbox lists exactly the rows
whose state waits, in results order, with the record keys, the lens and the
row verbatim; a row the rule did not run on never waits; a row whose stamp
does not recompute, computed by another rule, or without a state at the
policy path is refused; a results file without a roster reference or for a
rule off the policy is refused; `check_inbox` finds a changed results byte,
a narrowed or widened policy, an altered item, a missing results file and a
broken policy; both committed inboxes are what this checkout builds and name
the committed roster; the scripts write only their output and exit 0 on the
committed files and 1 on a tampered one; no em dash, no personal-shaped
content, no allegation words.

## What did not change

`code/watcher.py`, `code/roster.py`, `code/custody.py`, both watcher files,
both rule modules, both profiles, `config/roster.json`, both measure
scripts, both results files, `capture.json`, `pairs.json`, and every
verifier and test already in the repository. No rule, threshold or scoring
code changed.

## Still to build in step 5

The action log: where a person's decision on an inbox item is recorded
with its reason and its time, so that every decision is traceable and none
is the system's.
