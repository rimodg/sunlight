# Events in order: first answers on real records

Measured November 18, 2026. Rule class: **record consistency**. This is not
a legal rule. No result here says a law was kept or broken, and every result
is a risk indicator, never an allegation. No organisation is named.

## Result

Population: 193 distinct award and tender-deadline date pairs exported from
the watch journal (PR #25, journal head seq 5436).

| State | Records |
|---|---:|
| CONSISTENT | 119 |
| INCONSISTENT | 5 |
| UNASSESSABLE | 60 |
| NOT_APPLICABLE | 9 |
| Answered (CONSISTENT + INCONSISTENT) | 124 / 193 |

This is the first time SUNLIGHT has given a determinate answer on real
records. It is not the first legal HOLDS or BREAKS: the legal states stay
unused here on purpose, and that gate stays open.

## The rule

In a record whose procurement method invites tenders, the award date is not
earlier than the closing date for tender submissions.

Both fields are defined by the data standard the source publishes in:

- `tender.tenderPeriod.endDate`: "The end date is the closing date for
  tender submissions."
- `awards[].date`: "The date of the contract award. This is usually the date
  on which a decision to award was made."

Source: Open Contracting Data Standard 1.1.5 release schema, pinned at commit
`af0d0d41c64be26d8bbd57dcca8b474937e5851c`, sha256
`fac192e1ccfb061f5164bdb2d64c29e517c0f81661996b97de40cebc55a2c1bc`.
Method definitions: the `method.csv` codelist at the same commit, sha256
`8a956d41ead70abe583c6d0121729ec8a0ffb4f1c9aa18017d587ff794d8a589`.
Citations and applicability live in `config/events-in-order-profile.json`,
not in code.

## Why a separate class

The invariant core answers HOLDS or BREAKS only against a binding norm with a
cited commencement. A data standard is not binding law, so this rule does not
use the core's `evaluate` and does not use its legal states. It has its own
states, CONSISTENT and INCONSISTENT, so the two kinds of result cannot be
mixed. A test asserts the two vocabularies never overlap.

## Related published methodology

The Open Contracting Partnership's 2024 guide "Red Flags in Public
Procurement" lists indicator R061, "Decision period extremely short", computed
from the same two fields (award date minus tender period end date) against a
threshold. An award dated before the deadline is the extreme case of that
interval. The guide does not name "award before deadline" as its own flag;
this rule applies the same interval at its limit and says so.
https://open-contracting.org/wp-content/uploads/2024/12/OCP2024-RedFlagProcurement-1.pdf

The guide's file could not be fetched from the build machine, so no hash is
recorded and it is not a citation inside any result. It is context only.

## Refusals

| Case | State | Records |
|---|---|---:|
| Both dates on the same civil day (award time of day is not published) | UNASSESSABLE | 32 |
| Procurement method absent from the record | UNASSESSABLE | 25 |
| Method `limited`: the codelist does not establish a submission period | UNASSESSABLE | 3 |
| Method `direct`: awarded without competition by definition | NOT_APPLICABLE | 9 |

Also refused, with tests: a date without an explicit offset, an unreadable
date, and any pair in different offsets where the order is not established:
one civil day apart, or the whole award day does not lie on one side of the
deadline instant. The second case was found in review of PR #26 and fixed
November 19, 2026; it did not occur in the measured population. Review of that
fix found it raised an error on a year-9999 date; fixed November 23, 2026,
with calendar-edge tests. The rule answers or refuses and never raises.

## The five INCONSISTENT records

All five are method `selective`. The award is dated 4, 6, 11, 12 and 23 days
before the deadline. In three of the five, the deadline is also later than
the day the award notice itself was published. That second fact is reported
on each result and does not change the state.

What this does not establish: why. The retained projection keeps neither
`procurementMethodDetails` nor the notice type, so a call-off under a
framework, a correction, or a data entry error cannot be told apart from
anything else. A person has to read the notice.

## Limits

- One source, one short window: awards published November 12 to 14, 2026 on
  UK Contracts Finder. Not a census and not a rate for any wider population.
- 191 distinct procurements. The journal repeats records; pairs are
  deduplicated before assessment and results do not depend on input order.
- 69 of 193 records get no answer. Missing is not zero.

## Verification

`tests/test_events_in_order.py`: 36 tests. The replay test recomputes
`research/events_in_order_2026-11-18/results.json` from `pairs.json` and
requires a byte-identical match.

Since November 24, 2026 the results file is schema
`sunlight.events-in-order-results.v2`: every row carries a `custody` block
naming the journal capture it cites and the exact rule version that computed
it, and a `result_sha256` over the whole row. The 193 outcomes did not move;
`tests/test_custody.py` pins their digest. See
[CHAIN_OF_CUSTODY_2026-11-24.md](CHAIN_OF_CUSTODY_2026-11-24.md).
Schema v3, later the same day: every row also carries the sealed watcher's
lens (the procurement method read from the pair and the selection row that
held); see [SEALED_WATCHERS_2026-11-24.md](SEALED_WATCHERS_2026-11-24.md).
Schema v4: the file names the roster its watcher is on; no row changed; see
[ROSTER_2026-11-24.md](ROSTER_2026-11-24.md). The decision inbox built from
the file (`inbox.json` in the same folder) lists the five INCONSISTENT rows
as waiting for a person; see [DECISION_INBOX_2026-11-24.md](DECISION_INBOX_2026-11-24.md).

Reproduce:

    PYTHONPATH=code python scripts/measure_events_in_order.py \
      research/events_in_order_2026-11-18/pairs.json \
      config/events-in-order-profile.json OUT.json

Verify the chain of custody of the committed results:

    PYTHONPATH=code python scripts/verify_custody.py \
      research/events_in_order_2026-11-18/results.json \
      research/events_in_order_2026-11-18/pairs.json
