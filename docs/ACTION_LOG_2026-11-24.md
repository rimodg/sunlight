# The action log

Written November 24, 2026. Build step 5, fourth and last part: where a
person's decision on a decision inbox item is recorded, with its reason and
its time, chained by hash to the inbox it answers, so that every decision is
traceable and none is the system's.

## What the log is

The decision inbox ([DECISION_INBOX_2026-11-24.md](DECISION_INBOX_2026-11-24.md))
lists the result rows that wait for a person. The action log is the record
of what people decided about them. It is one file per inbox (schema
`sunlight.action-log.v1`), opened with no entries, to which one entry is
appended each time a person records a decision. The log never replaces an
entry: a later decision on the same item is a new entry after the earlier
one, which stays readable, and the standing decision on an item is the
latest recorded.

`config/action-policy.json` (schema `sunlight.action-policy.v1`) is the
owner's table of the words the record uses:

- `decisions`: the codes a person may record, each with its meaning, ordered
  by code. As committed they are the three answers to the question the inbox
  policy puts: `NOTE_ON_RECORD`, `NO_ACTION`, `SEEK_CORRECTION`.
- `roles`: the capacities in which a person decides, ordered. As committed:
  `owner`, `reviewer`. A decision is recorded under a role, never a name.

`policy_sha256` is the SHA-256 over everything else. `code/actionlog.py`
reads the policy part by part and refuses any missing, malformed or extra
part, unordered or duplicated codes or roles, a lower-case code, or a hash
that does not recompute. Widening the table (another decision, another
role) is one edited line, resealed with `scripts/seal_action_policy.py`;
the logs then name the new policy when they are next written.

## What a log carries

- `inbox_file` (repository-relative path), `inbox_file_sha256` (the bytes)
  and `inbox_sha256` (the content), and the results file, its bytes hash,
  the rule id and rule version the inbox names, copied.
- `policy`: the action policy file, the SHA-256 of its bytes and
  `policy_sha256`.
- `waiting` (from the inbox), `decided` (items with at least one entry),
  `open` (items with none) and `recorded` (entries). `decided` and `open`
  add up to `waiting`; a log whose counts do not recompute from its entries
  is refused.
- `items`: one line per waiting inbox item, in inbox order, with its
  `position`, `result_sha256`, `item_sha256` and `standing`: the `seq` and
  `decision` of the latest entry on it, or `null` while it is open.
- `entries`, in the order recorded: `seq` (from 1), `position`,
  `result_sha256` and `item_sha256` of the item answered, `decision` (a code
  on the policy), `reason` (the person's words, required), `decided_by`
  (`{"role": ...}`, a role on the policy), `decided_at` (UTC to the second,
  `2026-11-24T20:00:00Z`), `previous_sha256` and `entry_sha256` over the
  rest.
- `head_sha256`: the last entry's hash, or the inbox hash when there is no
  entry; `log_sha256` over everything else.

The chain: the first entry carries `inbox_sha256` as `previous_sha256`,
every later entry carries the hash of the entry before it, and
`entry_sha256` covers that link. Editing an entry breaks the hash of every
entry after it; reordering breaks the numbering and the chain; an entry on
a row the inbox does not list as waiting, or carrying other hashes than the
item, is refused. What a chain does not prove is that nothing was cut from
its end: a log with its last entry removed and its head and counts
recomputed still loads. The committed history of the file is the record
against that, which is why the log lives in the repository beside the inbox
and every change to it is a commit.

Nothing in `code/actionlog.py` decides. An entry exists because a person
recorded it; the log never supplies, defaults, scores or judges a decision,
and an item without an entry is reported as open, never as settled. No
personal data: the decider is a role, the reason is refused if it carries
an address, and no field for a name exists. A result is a risk indicator,
never an allegation; whether a procurement should have happened stays with
people, and the log records what they said follows.

## The two logs as committed

`research/events_in_order_2026-11-18/action-log.json`: opened on the
events-in-order inbox (`inbox_sha256`
`dd1032bcc576e585efd90ef2f9f50c639e3b02e1de9f9e690c7410b4efd88d82`): 5
waiting, 0 decided, 5 open, 0 recorded. No decision has been recorded,
because none has been taken; the five INCONSISTENT rows (positions 19, 20,
23, 135, 173) wait for the owner. `head_sha256` is the inbox hash.

`research/section53_2026-11-13/adapter-run/action-log.json`: opened on the
section 53 inbox (`inbox_sha256`
`b30b33df13c2821d2c18c1eb78d83628d842af8e3786f1ef6fff02c44d125b94`): 0
waiting, 0 open, 0 recorded. Nothing waits, so nothing can be recorded, and
the log says so.

`policy_sha256` of the action policy is
`5c3f1437d5aa36d3a9cd3a7b39fa4986f4534cf71462591c53bd3c1c3c585ff3`. Both
inboxes, both results files and the inbox policy are unchanged;
`tests/test_actionlog.py` pins both inbox hashes again.

## How to record, open and verify

Record one decision (reads the log, the inbox it names and the policy;
writes the log back and nothing else; the log must be inside the
repository; the time is taken from the clock unless `--at` gives it):

    PYTHONPATH=code python scripts/record_decision.py \
      research/events_in_order_2026-11-18/action-log.json \
      --item 19 --decision NO_ACTION --role owner \
      --reason "the words of the person deciding" --at 2026-11-24T20:00:00Z

Then commit the log with the decision it records. A decision on a row that
does not wait, a decision or a role off the policy, an empty reason, a
reason carrying an address, or a malformed time is refused and the log is
not written.

Open a log for an inbox (writes only the output named, refuses an existing
one, requires the inbox to be inside the repository):

    PYTHONPATH=code python scripts/open_action_log.py \
      research/events_in_order_2026-11-18/inbox.json OUT.json

Verify, reads only:

    PYTHONPATH=code python scripts/verify_action_log.py \
      research/events_in_order_2026-11-18/action-log.json \
      research/section53_2026-11-13/adapter-run/action-log.json

For each log this checks every part; recomputes the chain entry by entry
from the inbox hash, the items, the counts, the head and `log_sha256`;
reads the inbox the log names from the checkout and compares its bytes,
its hash and every item line and entry with the inbox item at that
position; compares the policy reference with `config/action-policy.json`
and every entry's decision and role with its tables; and checks the inbox
itself against the results file and the inbox policy in the checkout
(`check_inbox`), so a log only verifies on an inbox that does. Exit 0
means every link holds.

To reseal the policy after editing it (prints, writes nothing):

    PYTHONPATH=code python scripts/seal_action_policy.py > config/action-policy.json

`tests/test_actionlog.py` (75 tests): every missing, malformed or extra part
of the policy and of a log is refused, even when every hash is recomputed
around the change; both hashes are stable across locations and move with
every part; an opened log lists every waiting item as open; a recorded
decision is one entry chained to the inbox, a second decision on the same
item is a new entry after the first; a decision on a row that does not
wait, off the policy, without a reason, with an address, or with a
malformed time is refused; an edited entry breaks every entry after it;
`check_log` finds a changed inbox byte, an inbox rebuilt under a narrower
policy, an altered item line, a missing item, a policy resealed without the
role or the decision an entry records, a missing inbox and a broken policy;
both committed logs are what this checkout opens, with nothing recorded,
on inboxes that verify; the scripts write only their output and exit 0 on
the committed files and 1 on a tampered one; the record script appends
inside the repository and writes nothing on a refusal; no em dash, no
personal-shaped content, no allegation words, no name anywhere in a log.

## What did not change

`code/inbox.py`, `config/inbox-policy.json`, both inboxes, `code/watcher.py`,
`code/roster.py`, `code/custody.py`, both watcher files, both rule modules,
both profiles, `config/roster.json`, both measure scripts, both results
files, `capture.json`, `pairs.json`, and every verifier and test already in
the repository. No rule, threshold or scoring code changed.

## Step 5 is complete

Sealed watchers, roster, decision inbox, action log. Every result names the
lens it was read through and the roster that lens was on; every result
that waits for a person is listed with what was read and what the rule
said; every decision a person takes is recorded under a role, with its
reason and its time, chained to the inbox. The next build step is 6:
separating the standard from the software.
