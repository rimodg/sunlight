# Notice matching and regime measurement, November 13, 2026

Measurement only. No invariant, adapter, legal profile or finding classifier
was implemented. PR 18 stays draft until a real rule proves the core. The
installed watch and its data were read only, not changed.

## Population and finding

The fixed population is the 96 `(ocid, release_id)` pairs through watch journal
sequence 868, head
`e00b1082eaab91ef7263ec5a3ff171bd8552b5cf034af37fd0496fd9bce2ed2d`.
These are **96 award appearances, 94 distinct award IDs, and 93 procurement
OCIDs**. They are not 96 independent contracts. The original query window is
November 12-14, 2026. Later watch captures do not enlarge this denominator.

| Evidence result | Records / 96 |
|---|---:|
| PCR 2015 supported by identifier-linked primary evidence | 9 |
| Procurement Act 2023 affirmatively established | 0 |
| UNDETERMINED, with individual reason | 87 |
| Regime established from the retained projection alone | 0 |
| Exact frozen release ID returned by supplemental CF retrieval | 94 |
| Frozen release version not returned, not backfilled | 2 |
| Linked to a parent FTS framework/DPS notice | 6 (6.25%) |
| Matched to the corresponding FTS/CDP award notice | 0 (0%) |
| Assessable under proposed PCR publication-order norm | 0 |
| Assessable under proposed PA publication-order norm | 0 |

**Finding:** the retained watch projection cannot currently establish regime
or the required publication-order event pair. Later primary-source enrichment
supports a regime for 9/96 records. Six parent-notice links provide useful
context but do not provide the corresponding call-off award notice. The
measured 0/96 corresponding-award match rate is an evidence-coverage result,
not proof that no matching notices exist and not a legal finding. Zero
confirmed PA records does not mean the remaining 87 are PCR records.

[Every record and its reason](../research/notice_measurement_2026-11-13/record-measurement.json)
is committed, including capture identifiers, source URLs/hashes, source
locators, supplemental retrieval identity and the distinction between parent
and corresponding-award matches. This is the primary per-record deliverable.

## How regime was established, and where it was not

The retained projection omits legal basis and framework/DPS references. A
read-only retrieval of each captured notice's official CF release endpoint
returned the exact frozen release ID for 94 rows. For two older versions it
returned a different release: those remain UNDETERMINED. A later document is
not a substitute for the missing historical version. Supplemental evidence
was fetched later than capture and is explicitly labelled as such; matching
an ID is not a claim that the entire historical raw document was retained.

Eight records identify one of five agreements in their description or explicit
reference field. Their relationship to the agreement was read, not inferred
from an incidental mention. The official GCA agreement pages identify:

| Identifier | Agreement start | Published regulation | Cohort records |
|---|---|---|---:|
| RM1557.14 | 2024-10-29 | PCR2015 | 4 |
| RM6285 | 2025-02-18 | PCR2015 | 1 |
| RM6124 | 2021-09-06 | PCR2015 | 1 |
| RM6244 | 2022-11-29 | PCR2015 | 1 |
| RM6277 | 2023-04-25 | PCR2015 | 1 |

[Primary agreement receipts](../research/notice_measurement_2026-11-13/framework-evidence.json)
include the URL, hash, retrieval time, original local snapshot and locator.
For example, [RM6285](https://www.gca.gov.uk/agreements/RM6285) explicitly
places its start before February 24, 2025 and labels its regulation PCR2015.
These are evidence-backed saved-regime inferences; a new call-off award date
does not replace its parent's regime.

The ninth record explicitly identifies a further competition under DN750494,
FTS reference `2024/S 000-036226`. The official
[FTS notice API](https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages/036226-2024)
returns notice ID `036226-2024`, tender ID `DN750494`, a framework flag,
legal basis `CELEX 32014L0024`, and publication at 2024-11-08T11:49:14Z.
The cited parent and pre-commencement public tender support the saved-PCR
inference under SI 2024/716 regulation 5(3)(c). This does not yet establish
territorial or authority-specific applicability of PCR Part 4 to the call-off.

Nine other records cite DPS `2018/S 031-067685`. That is useful older-DPS
evidence, but the originating TED text was not admitted: direct requests
returned HTTP 202 and an empty body. A related later FTS notice was found,
but a different procurement is not substituted for the originating instrument.
Those nine stay UNDETERMINED. Other earlier tender/contract dates likewise do
not prove which legal regime applies. Remaining rows lack a verified relevant
commencement event or parent/legal-basis chain. Each reason is retained.

The proposed two-way date shortcut needs qualification: the applicable
commencement event is defined by the transitional provisions. Saved frameworks
and DPS can continue producing later call-offs. Territorial scope and other
regimes also matter. We did not assign a regime from award year, `open`,
`selective`, portal presence, supplier name or contract title.

## Notice search and timestamp coverage

All matching used explicit identifiers. The six parent links resolve to three
FTS notices: `037392-2024` via `RM1557.14`, `018833-2021` via `RM6124`, and
`036226-2024` via the explicit FTS reference. The
[retained FTS projections](../research/notice_measurement_2026-11-13/fts-parent-evidence.json)
show the identifiers and publication datetimes on both sides of those joins.
These are parent events, not the relevant call-off award events.

A separate bounded FTS API scan followed all five returned pages for
`updatedFrom=2026-11-12T00:00:00` through
`updatedTo=2026-11-13T05:20:00`, yielding 431 release records. No retained CF
OCID/notice-link cross-reference and no exact tender-reference intersection
with the enriched cohort was found. There was no title or name matching.
The [search receipt](../research/notice_measurement_2026-11-13/fts-search-receipt.json)
retains every request URL, cursor continuation, retrieval time and response
hash. This was a completed traversal of a bounded update window, not an
all-time census or a publisher-guaranteed immutable snapshot. FTS HTML/PDF
requests returned 403; the public individual-notice API did return the three
primary parent notices. Initial exploratory filtered API requests returned
429; those failures are not evidence of missing notices.

The captured `awards[].datePublished` is present in all 96 rows. FTS publication
instants are published for the three parent notices. **No admitted corresponding
award event pair exists for any cohort row.** Initial-publication semantics,
acknowledgement time where relevant, qualifying alternative-system evidence,
notice/lot identity and the duty's scope cannot be filled in with award dates,
contract start dates, release revision times or the parent's publication date.

## One invariant, two regime-selected norm records: design only

Proposed invariant: **a covered downstream publication must not precede the
legally qualifying prior publication event for that procurement and notice.**
The common comparison is `downstream_instant >= qualifying_prior_instant`;
the margin is the elapsed time between those events in an explicit common
time basis. Event identity, stage and precision are part of the comparison.
No event pair was evaluated in this measurement.

### N-PCR: saved Public Contracts Regulations 2015

- Instrument/provision: PCR 2015 regulation 108(5), read with (1)-(3), (7)-(9).
  Provision text is retained at its source locator in the existing
  [source manifest](../research/invariant_core/sources.json), SHA-256
  `4d7a66cc03335932ef03a5e50fa119d86808999835a70e90fd94a9352d1f1f28`.
- Binding status: enacted binding provision, subject to record-specific scope.
- Commencement: February 26, 2015 for authorities acting on behalf of the Crown;
  April 1, 2015 for other authorities, under regulation 1(6). Use the earliest
  commencement in the norm record with the later authority-specific date as
  an explicit scope condition; do not flatten both to one universal date.
- Regime selector: evidence satisfies the saved-PCR conditions in SI 2024/716
  regulation 5. Do not set an unconditional end at February 24, 2025 for saved
  procurements.
- Prior event: corresponding UK e-notification contract award notice publication.
  Downstream event: CF publication of the relevant award information.
- Trigger: authority submits or intends to submit that notice. Establish
  authority/territorial scope, exact notice/lot relation and any relevant
  withholding or deemed-compliance facts. Unknown trigger is UNASSESSABLE.

### N-PA: Procurement Act 2023 publication priority

- Instrument/provision: Procurement Regulations 2024 regulation 5(11), read
  with 5(1)-(10) and the PA provision requiring the particular notice. This
  is the broader newer equivalent appropriate to comparing publication events.
  Source SHA-256: `5f7ecfb0863d8fe006e145a14d907905a70f7ca0fb41ead45a6d025242e3f895`.
- Binding status: enacted binding provision, subject to scope and effective
  version. Commencement is February 24, 2025 under regulation 1(2), tied to
  PA section 11 and its commencement instrument.
- Regime selector: affirmative PA scope evidence, including the relevant
  commencement event and exclusion of saved-framework/DPS procurement. Unknown
  regime selects neither norm and yields UNASSESSABLE, not a default to PA.
- Prior event: legally qualifying CDP publication, or an eligible alternative
  online-system publication. Downstream event: publication elsewhere of the
  covered notice, document or information.
- Qualification: regulation 5(4) permits successful-submission confirmation as
  well as public access to satisfy the platform requirement. Regulation 5(5)
  permits alternatives when the platform is unavailable or prescribed waiting
  conditions are met; (8)-(9) address rejection and later platform publication.
  The unavailable-platform wording took effect on March 24, 2026. Scope must
  select the applicable exception text by date, not apply today's version to
  all earlier events.
- Do not equate acknowledgement with public access: regulation 5(4) expressly
  addresses satisfaction of 5(1). Its interaction with the order duty in 5(11)
  must be resolved before treating acknowledgement as that prior event.
  A later public CDP timestamp alone cannot justify BREAKS without checking
  lawful alternatives and that interpretation. Missing evidence remains
  UNASSESSABLE; acknowledgement is not an automatic HOLDS shortcut.

The [new source manifest](../research/notice_measurement_2026-11-13/law-sources.json)
records full source hashes, retrieval times and locators. Exact XML remains
in the external archive; committed text is an explicitly derived extract.
The two norm records are a design, not instantiated production configuration.
Their supporting scope and exception provisions remain individually cited.

### Verified below-threshold provision

[PA section 87(1)](https://www.legislation.gov.uk/ukpga/2023/54/section/87)
requires the below-threshold tender notice before advertising to invite tenders
for a notifiable below-threshold contract. Section 87(2) excludes advertising
only to particular or pre-selected suppliers. Section 87(4) determines which
contracts are notifiable. Regulations 5(1), 5(3)(w) and 24 provide the platform
route and notice information; regulation 5's qualifications still matter.

The secondary summary is directionally correct but incomplete about the
pre-selected-supplier exception and alternative platform arrangements. This
is a **tender-advertising** duty: a CF award publication cannot silently become
its advertisement timestamp. The broader regulation 5(11) provides the
single publication-priority design above without that event substitution.

## Alternative under the 2023 Act

The measured assessable cohort is zero, not a handful. Prefer a native CDP
contract-details example for **PA section 53(1)(b)'s ordinary-contract
publication deadline**, with regulation 32 identifying the required contract
entry date. This avoids depending on a CF-to-FTS award join for the first proof.
It is proposed only; no rule or legal finding has been implemented.

The primary [notice API for 107781-2026](https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages/107781-2026)
publishes UKPGA `2023/54`, an open procedure, contract ID `1`,
`aboveThreshold: true`, `dateSigned: 2026-11-03T00:00:00+00:00`, and a
contract-details document publication at `2026-11-12T18:15:10Z`. Both fields
are in the [retained candidate](../research/notice_measurement_2026-11-13/alternative-candidate.json).
The date-only hand-check is November 12 minus November 3 = 9 elapsed calendar
days. Midnight in a date field is not proof of an actual midnight signature.
This is descriptive arithmetic, not a statutory margin or HOLDS result.

Before approving implementation, verify the publisher mapping from `dateSigned`
to legal entry, the actual UK7 notice, ordinary rather than light-touch scope,
relevant exclusions and calendar-day counting. Section 53 counts a period
beginning with entry, so the entry date is day one. Public availability can
prove an upper bound on qualifying publication; a late displayed publication
alone must not erase regulation 5's confirmation/alternative routes. These
are concrete remaining gates, not a claim that the alternative is already proved.

## Review and limits

- A parent framework match is not a call-off award match: kept separate.
- A 2026 award on a pre-2025 framework is not automatically PA: regime evidence
  follows the cited originating procurement.
- Missing scheme evidence is not an inference that the obligation does not
  apply: 87 records remain UNDETERMINED.
- Two unavailable historical versions are not overwritten by fresh documents.
- An updated-window scan is not proof of all-time absence; no negative finding
  is made from unmatched records.
- Platform access and successful-submission confirmation are different facts.
- A date-only field or rounded timestamp cannot prove strict event ordering
  within its resolution; a future adapter must represent that uncertainty.

The core remains unchanged from its tested commit. This work proves data
coverage and establishes the source-backed design; it does not yet prove a
real invariant. Operational results are in the separate
[first-day watch report](WATCH_FIRST_DAY_2026-11-13.md).

## Verification performed

Run from this checkout, with the external artifacts and original journal at
the recorded paths:

```sh
python3 research/notice_measurement_2026-11-13/verify.py
```

The executed check verified source/extract hashes, the exact 96 frozen keys,
per-record counts and parent matches, completed FTS pagination, the first-day
source/scheduler counts directly against the read-only journal, and unchanged
core/test hashes. It passed on November 13. It verifies custody and recounting,
not the truth of a publisher assertion or legal interpretation. The backend
suite was not rerun for these measurement-only artifacts; its earlier result
remains dated in the existing receipt.
