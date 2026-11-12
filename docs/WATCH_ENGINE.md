# The rebuilt organizational watch

The watch is additive to the existing analyzer. Its four organs share one
operator-local append-only journal:

1. `watch_identity.py`: authority-qualified cited organizational identifiers.
2. `watch_journal.py`: organizational projections, original-response digests, observations, examinations and
   operational receipts. Updates and deletes are refused by database triggers.
3. `watch_capture.py`: two reviewed adapters, bounded HTTPS, same-endpoint cursor
   paging, one page per source per poll, persistent resume and backoff on failure.
4. `watch_examination.py` and `watch_engine.py`: deterministic as-of screening,
   identity across categories, history, open questions and changes from the last
   examination. `watch_packet.py` exports frozen inputs for byte-for-byte replay
   with the matching source build. No model is called.

The journal is physically shared; a subject's logical ledger is its cited
observations and examinations over time. Merges never erase historical identity.
Source-state and health records are control-plane receipts. They do not enter
the rules or turn a failure into zero activity. Startup freezes the running build
identity. A different Git HEAD at a later query is not substituted for it.

## Current analytical scope

The Contracts Finder adapter accepts OCDS release pages of at most 100 releases.
Every admitted procurement record is processed through the existing UK profile's
complete TCA structural rule family. Rule citations and source pointers are
retained. No thresholds or existing rules were changed. A rule not triggered is
not a declaration of no risk. Every rule carries an explicit input-availability
statement. Missing or non-comparable inputs are UNASSESSABLE. Favorable rule
outputs are DOCUMENTED_SIGNAL, distinct from risk indicators. The underlying
rule-fire log is retained separately; this wrapper does not retune the rules.
Missing publication time stays explicitly unknown.

The d-portal adapter accepts JSON rows carrying `aid` and `reporting_ref`, with
`reporting_ref_like` wildcard required in the reviewed endpoint. The reporter's
GB-COH reference can join the same legal company identifier in an OCDS party.
It is a reporting observation, not proof of disbursement or arrival. An IATI
page at its limit advances the explicit `orderby=aid&limit=100&offset=...`
query rather than being treated as an exhaustive population. Other full-page
shapes without a next link are refused. Offset pagination is not a publisher
snapshot: changes during traversal can move rows. Both adapters passed one-page
live probes on November 10, 2026; population and unattended gates are separate.

Price comparables, delivery, recovery and arms dossiers are not supplied by
these two feeds. The watch states this scope rather than producing findings for
those engines without their inputs. Duplicate unchanged captures do not become
new analytical observations. Two differing versions with the same publication
and capture times are unassessable, not resolved by arrival order.
When an earlier version is republished, the most recent applicable occurrence
selects the active version while history retains one immutable observation per
content version. A source failure makes `--once` exit nonzero, even when the
last good data can still be examined.

## Protection and source review

There are no enabled default sources. An operator must supply a reviewed,
organization-only policy. Each adapter projects only declared organizational
fields before admission. Source names, addresses, contacts, narratives and other
unlisted fields are discarded in memory. Personal-shaped content in an allowed
field still refuses that row, with a fixed reason and schema-derived field path.
The rejected value is never retained. This deterministic guard is not a
comprehensive privacy classifier or a legal basis for processing. See the
[projection contract and live proof](TASK2_PROJECTION_2026-11-10.md).

Retained captures contain the projection, its digest, the original-response
SHA-256, source URL, adapter version, policy hash and capture time. No original
response body is retained. Replay reproduces the projection-based examination;
it cannot reconstruct excluded text or independently recheck the original-byte
digest without an independently obtained original. Packet schema v2 states that
limit. Old body-bearing captures are refused for replay pending explicit
migration; no existing journal is rewritten or deleted automatically.

Coverage accompanies each observation: mapped paths, gaps and their reasons,
publisher/service identifier, adapter and source-contract versions, exclusions,
and explicitly unknown population completeness. Review-body roles and addresses
are not supplied by this projection. Rules needing them remain unassessable;
their absence in a projection is not a negative claim about the source.

Failures retain fixed receipts without source exception text or rejected bodies.
HTTP failures record that the source was reached. A transport failure leaves
reach unknown. The last good capture survives both. Paging cycles, cross-origin
or cross-path links, redirects, oversized responses and unreviewed sources are
refused. A completed page cycle is only the endpoint's represented coverage,
not evidence of a census of all procurement or all aid.

## Local use

The service guide supplies pinned installation. For an already verified runtime:

```bash
python -m watch_engine --data-dir /absolute/operator-data --policy /absolute/policy.json --once
python -m watch_engine --data-dir /absolute/operator-data --policy /absolute/policy.json --health
python -m watch_engine --data-dir /absolute/operator-data --policy /absolute/policy.json --replay 2026-11-03T12:00:00Z
```

Use `PYTHONPATH=/absolute/clone/code` for these module commands. Operational
captures, database, logs and packets live outside the clone. `--packet ID`
exports an examination packet to stdout; `--verify-packet PATH` replays it with
the same source hash. Persist either output outside the repository.

The hash chain detects accidental mutation; it is not an issuer signature and
cannot prevent a database administrator rebuilding a chain. Packets prove
reproducibility of a reading from frozen inputs, not truth of the source claims.

Offline tests use synthetic organizations, documents, clocks and transports.
They are not the owner's October 27 run, a public-source acceptance run or an
independent reproduction of the 20-organization intersection.
