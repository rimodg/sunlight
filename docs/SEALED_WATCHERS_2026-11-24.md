# Sealed watchers

Written November 24, 2026. Build step 5, first part: every result carries the
lens it was read through, and that lens is sealed.

## What a watcher is

A watcher is one rule plus the context it reads before applying that rule.
It is a file under `config/watchers/` (schema `sunlight.watcher.v1`) with:

- `rule`: the rule id, the rule module file and the profile file. One rule
  per watcher.
- `facts`: a fixed list of facts the watcher reads from each record, each by
  a field path, with a kind (`code`, `classification`, `boolean`, `text`),
  the publisher expected to supply it, and a definition cited to a source
  with its SHA-256. A code fact also cites its codelist; a classification
  fact cites the definition of scheme and id.
- `selection`: an ordered table. Each row says which fact values select the
  rule: a code in a cited list, a classification that equals a value, or a
  fact that is missing. The first row whose every condition holds wins.
- `otherwise`: what happens when no row holds. Always `NOT_SELECTED`, with
  the watcher's own reason naming the expected publisher.

Reading a fact is reading a field. Nothing in `code/watcher.py` infers,
scores or judges. A fact that is absent is `missing`; a fact that is present
but not of its declared kind is `unreadable`; neither is ever a value. When no
selection row holds, the rule does not run and the row says so. Missing is
not zero. Whether a procurement should have happened is a human judgement and
stays one; a result is a risk indicator, never an allegation.

## What the seal is

`watcher.seal(root, file)` returns a typed block (`sunlight.watcher-seal.v1`)
with the watcher file path and the SHA-256 of its bytes, the rule version
from `code/custody.py` (rule module bytes, profile bytes, every source the
profile cites) and every source the facts cite. `watcher_seal_sha256` is the
SHA-256 over that block. A changed byte of the watcher file, of the rule
module, of the profile, a changed selection row or a changed cited source
changes the seal.

## What a result row now carries

Each row of both results files (`sunlight.events-in-order-results.v3`,
`sunlight.section53-results.v3`) carries a `watcher` block before its custody
stamp, so `result_sha256` covers it:

- `watcher_id` and `watcher_seal_sha256`.
- `context`: every fact read from the record (`facts`), and which were
  `missing` or `unreadable`.
- `selection`: `SELECTED` with the index of the selection row that held and
  the rule applied, or `NOT_SELECTED` with the reason.

The file carries the full `watcher_seal` block and a count of rows not
selected.

## The two watchers

`config/watchers/events-in-order.json` reads `procurement_method` from each
exported pair. Its definition is cited to the OCDS 1.1.5 release schema and
its codes to the method codelist, both pinned at commit af0d0d41 with the
SHA-256s the rule profile already cites. Selection: a code of the codelist
selects the rule (row 0); a missing method also selects the rule, which
refuses on its own cited terms (row 1); a published value outside the
codelist is `NOT_SELECTED`. On the 193 pairs: 168 rows matched row 0, 25
matched row 1 (method missing), 0 not selected. The 193 outcomes did not
move; `tests/test_custody.py` still pins their digest.

`config/watchers/section53.json` reads `tender.legalBasis` (scheme and id)
from each admitted release. The field is defined by the OCDS legalBasis
extension, pinned at commit 5d412856 (`release-schema.json`, SHA-256
cf02d258...), and scheme and id by the OCDS 1.1.5 Classification definition.
Selection: a release whose published legal basis is `UKPGA 2023/54`, the
Procurement Act 2023 the rule's profile cites, selects the rule; any other
published basis, or none, is `NOT_SELECTED`. The watcher does not decide
which law governs a procedure; it reads what the record publishes and
refuses the rest. On the capture of November 13: all 126 releases that
produced rows publish `UKPGA 2023/54`, so all 150 rows are selected and all
150 outcomes are identical to before; `tests/test_section53_custody.py` still
pins the digest of the rows without custody and lens. The captured pages
also hold 56 releases with a CELEX basis (the 2014 EU directives); none of
them carries a contract document, so none produced a row before or now.

## How to verify

From a checkout, reads only:

    PYTHONPATH=code python scripts/verify_watcher.py \
      config/watchers/events-in-order.json \
      research/events_in_order_2026-11-18/results.json \
      research/events_in_order_2026-11-18/pairs.json

    PYTHONPATH=code python scripts/verify_watcher.py \
      config/watchers/section53.json \
      research/section53_2026-11-13/adapter-run/results.json \
      research/section53_2026-11-13/adapter-run/capture.json

Each recomputes the seal from the checkout, finds every row's record in the
input file, reads the facts again, runs the selection table again, compares,
and recomputes every row's custody hash. Exit 0 means every link holds. The
custody verifiers (`scripts/verify_custody.py`,
`scripts/verify_section53_custody.py`) and `scripts/verify_section53_evidence.py`
are unchanged and still exit 0.

`tests/test_watcher.py` (28 tests): every missing, malformed or extra part of
a watcher file is refused; the seal is stable across locations and moves with
every part; facts are read by path and never inferred; selection takes the
first holding row or the otherwise; every kind of tampering with a row's
lens is found; a record the watcher does not select gets no rule run; both
committed files carry a lens that recomputes from this repository; the
verifier reads only.

## What did not change

`code/events_in_order.py`, `code/section53.py`, both profiles,
`code/custody.py`, its 15 tests and the 12 section 53 custody tests,
`capture.json` and `pairs.json`. No rule, threshold or scoring code changed.
The measure scripts gained the lens and the schema version; nothing else.

## Still to build in step 5

The roster is built: [ROSTER_2026-11-24.md](ROSTER_2026-11-24.md). The
decision inbox is built: [DECISION_INBOX_2026-11-24.md](DECISION_INBOX_2026-11-24.md).
The action log remains.
