# Invariant core and UK rule proposal, November 13, 2026

The generic core is implemented and tested. **No UK rule is implemented or
approved.** The proposed live legal proof remains open because the captured
fields do not yet establish both statutory events and applicability. Approval
of the rule is not evidence that these missing facts have been established.

Branch `invariant-core` starts at origin/main
`0617f5c888c841a2293a28bf2e2509c059edaddd`. All changes are isolated from the
installed watch. Its journal was opened with SQLite `mode=ro` in a read
transaction. No service, configuration, capture or journal data was changed.

Ghana is separately recorded in the findings and defect registers on
[producer-share PR 17](https://github.com/rimodg/sunlight/pull/17), including
all three source-note corrections. It is UNASSESSABLE, parked, not dropped:
the official enacted Act 1182 text has not been obtained, and the numerical
realised-FOB denominator was **not found in the September release** declaring
71.18%. Availability elsewhere is not determined. The owner is obtaining the
Act; Task 1 stays open. This core contains no Ghana statute or price profile.

## Design and contract

[The core](../code/invariant_core.py) uses immutable quantities with a Decimal
amount, unit, optional currency, half-open calendar period, and a source URI,
locator and SHA-256. Calculations retain a tree of the original quantities and
any cited conversion profile entry. Derived amounts are never presented as
published inputs. There are no commodity, exchange-rate, bag or legal threshold
constants in the module.

Arithmetic uses exact rational intermediates and constructs finite Decimals
without depending on the ambient Decimal precision. Floats, non-finite values,
zero denominators and non-terminating decimal division are refused. There is no
implicit rounding. A future rule can compare products instead of dividing,
where its domain establishes the denominator's sign. A cited, positive
conversion must match the input unit/currency and cover its entire period.
Addition, subtraction and ratios require identical units, currencies and
periods. Multiplication is deliberately limited to a sourced dimensionless
ratio, rather than pretending to support arbitrary dimensional algebra.

Norms retain provision text, instrument, binding status and cited commencement
(and optional end) dates. Source hashes identify bytes; they do not establish
authenticity, completeness, or the truth of a legal interpretation. A separate,
cited scope determination must establish that the norm applies to the subject.
Unknown scope or unverified binding force yields UNASSESSABLE. A whole period
before verified commencement returns NOT_APPLICABLE. A period crossing a legal
boundary must be split; it cannot become a whole-period breach or hold.

Findings retain both named terms, their recursive provenance, the equation,
norm, scope, evaluation period, reason, and a signed margin. HOLDS includes
zero margin for an inclusive boundary. Positive margin means headroom for
either supported comparison (`>=` or `<=`); negative means BREAKS. Undefined
margins in UNASSESSABLE and NOT_APPLICABLE are explicitly null, not zero.
Missing terms name the missing evidence and its expected publisher. Arithmetic
errors raise `InvariantError`; comparison basis mismatches are recorded as
UNASSESSABLE. An adapter must preserve an arithmetic refusal as an evidence
limitation rather than supply a guessed value.

Announcement series retain every identifier, announcement date, effective
window, value and effective-window citation. Selection requires an effective
date and a known-on date, so a future announcement is not silently selected.
Gaps and overlapping effective values are refused; there is no averaging or
implicit preference for the latest announcement. The caller supplies explicit,
cited windows and splits evaluation periods at changes. This is not a full
bitemporal revision database: `known_on` checks the announcement date, not the
date a researcher learned of a correction to an effective window. Revision
history and completeness must be established by the eventual rule adapter.

## Worked core example: synthetic, not a Ghana finding

The executable fixture in
[test_invariant_core.py](../tests/test_invariant_core.py) identifies its
synthetic source bytes and hashes them. Its deliberately simple figures are
72 monetary units per tonne, a denominator of 100 in the same currency, unit
and period, and a minimum ratio of 0.70. A person can reproduce:

```text
72 / 100 = 0.72
0.72 >= 0.70
margin = 0.72 - 0.70 = 0.02 (dimensionless ratio)
state = HOLDS
```

The result is 2 percentage points of headroom, not a claim of 2% relative
improvement. Changing the numerator to 69 makes the comparison BREAKS; a
missing denominator makes it UNASSESSABLE. The synthetic bag conversion is
an explicitly cited test profile, not a real-world unit convention. These
examples prove core mechanics and assert no actual legal obligation.

## Primary law read and retained

The [source manifest](../research/invariant_core/sources.json) records each
URL, UTC retrieval time, byte count, SHA-256 and section locator. Exact XML
responses are retained at each manifest entry's `local_path` in the local
source archive. Text companions are committed derived reading aids; the XML
bytes are the evidence. Both source and extract hashes are recorded. GitHub
push protection rejected legislation XML annotation identifiers as possible
Mailgun keys. No bypass was used: raw XML was removed from the unpushed commit
and retained locally, unchanged. A fresh checkout needs that archive or exact
matching downloads to reverify the raw sources. Retrieved November 13, 2026.

- [PCR 2015 regulation 108, historical text at December 31, 2024](https://www.legislation.gov.uk/uksi/2015/102/regulation/108/2024-12-31):
  paragraph (5) governs the order of publication on Contracts Finder and the
  UK e-notification service where a contracting authority submits or intends
  to submit a contract award notice. Paragraphs (1)-(3) determine the relevant
  circumstances, information and withholding grounds; (7)-(8) address deemed
  compliance through automatic extraction. Paragraph (4) uses reasonable
  time, rather than itself prescribing a universal 30-day CF clock.
- [PCR regulation 1 as made](https://www.legislation.gov.uk/uksi/2015/102/regulation/1/made):
  paragraph (6) gives regulation 108 different commencement dates for Crown
  and other contracting authorities: February 26 and April 1, 2015. Paragraphs
  (7)-(8) also limit territorial/application scope. The proposed rule must
  verify the applicable version and authority, not flatten these dates.
- [Saving regulation 5, SI 2024/716](https://www.legislation.gov.uk/uksi/2024/716/regulation/5):
  some earlier procurements remain under PCR; paragraph (4)(a) disapplies the
  new Act where the saved PCR regime applies. A 2026 publication date alone
  therefore does not select the Procurement Act 2023.
- [PCR regulation 50](https://www.legislation.gov.uk/uksi/2015/102/regulation/50/2024-12-31):
  its deadline concerns submission for publication, not CF publication. The
  text also distinguishes framework call-offs and dynamic purchasing systems.
- [Procurement Act sections 50](https://www.legislation.gov.uk/ukpga/2023/54/section/50)
  and [53](https://www.legislation.gov.uk/ukpga/2023/54/section/53): a contract
  award notice precedes entry into a contract; a contract details notice
  follows entry. Section 53 distinguishes ordinary and light-touch contracts
  and has exclusions. The commencement Schedule and its 2024 amendment are
  retained, as is saving regulation 6 for context. They are not interchangeable
  with PCR 108 or a CF award release.

These are source notes, not an encoded UK legal profile. The historical PCR
text is intentionally retained: the default current URL displayed revocation
rather than the operative historical provision. Saved-regime applicability
must be separately evidenced for the particular procurement.

Verify the retained source and example bytes from this checkout:

```sh
python3 scripts/verify_invariant_core_evidence.py
# On another machine, provide the directory containing the nine XML files:
# python3 scripts/verify_invariant_core_evidence.py --source-dir /path/to/source-archive
```

## Actual live watch fields

[Field inventory](../research/invariant_core/watch-fields.json), inspected at
2026-11-13T05:04:17Z, covers the retained Contracts Finder observations through
journal head sequence 868, hash
`e00b1082eaab91ef7263ec5a3ff171bd8552b5cf034af37fd0496fd9bce2ed2d`.
The query window is November 12-14, 2026; this is not the earlier October
population and is not a completeness claim for that window.

There were 18 CF observation events and 96 distinct `(ocid, release_id)` pairs,
using the last retained occurrence of each pair. These contained 96 awards.
All 96 retained award date, award publication date, award value and contract
period. Tender value was retained in 70, procurement method in 76, tender
period end in 96 and tender period start in zero. A field being present does
not prove its accuracy or its equivalence to a legal event.

The projection does not retain legal regime, authority classification,
exemption/withholding evidence, notice submission time, the corresponding
UK e-notification notice publication time, or proven contract entry time.
Those are gaps in this retained evidence, not claims that the publisher has
no such information elsewhere.

The [retained example](../research/invariant_core/watch-example.json) has:

```text
ocid: ocds-b5fd17-c8fceea3-acd2-4db9-a7b9-70192ea24eef
/record/record/awards/0/date:          2026-10-27T00:00:00Z
/record/record/awards/0/datePublished: 2026-11-12T14:32:49Z
/record/record/date:                 2026-11-12T14:35:22Z
```

A hand-check of the first two timestamps gives 16 days, 14 hours, 32 minutes,
49 seconds: `16*86400 + 14*3600 + 32*60 + 49 = 1,434,769` seconds. This is a
**descriptive difference between two published fields**, not a statutory
margin. Using the release revision time instead would produce a different
number. Neither difference proves the applicable submission deadline or
contract-entry clock. No legal HOLDS or BREAKS is asserted from this example.
The retained watch projection has its own digest; the upstream body hash is
a receipt only, because the watch deliberately does not retain raw bodies.

## Single rule proposed, awaiting approval

**PCR 2015 regulation 108(5): for an in-scope, saved-PCR award where the authority
submits or intends to submit a contract award notice to the UK e-notification
service, Contracts Finder publication must not precede that notice's publication.**

Proposed equation and margin:

```text
CF initial award-information publication instant >= corresponding UK notice publication instant
margin = CF instant - UK notice instant, expressed in a common cited time basis
```

This is preferable for the first CF-based rule to guessing a value threshold
or treating publication as submission: it compares two publication events
specified by the same provision. The known CF field is a candidate input,
not yet an admitted mapping to initial publication. Unknowns must remain
UNASSESSABLE. Findings would be indicators, never determinations of misconduct.

**Correction to the work plan:** both statutory sides are not yet in hand in
this snapshot. Before implementation or claiming a real proof, obtain and hash
one corresponding official UK notice, establish the exact contract/notice
join and initial publication semantics, and evidence the saved-PCR regime,
applicable territorial/authority scope and paragraph (5) trigger. Check the
relevant version of regulation 1 and regulation 108, and the impact of deemed
compliance and withholding provisions. Do not infer any of this from price,
portal presence, supplier names, `open`/`selective`, or award year alone.

The owner approval gate remains closed. Approving this proposal would authorize
the source-matching and scope work first; implementation and real HOLDS/BREAKS
proof still require that evidence to pass. No UK adapter, profile or live-rule
test has been added in this change.

## Adversarial self-review

| Risk found | Change or constraint retained |
|---|---|
| Ambient Decimal precision silently rounds money or margins | Rational intermediates, exact finite Decimal construction; low-precision tests |
| A derived number borrows a source citation as if it was published | Recursive calculation tree retains each operand and conversion separately |
| A season crossing commencement becomes a false full-season breach | Whole-before period is NOT_APPLICABLE; straddling period must be split |
| Verified commencement alone is mistaken for subject-specific applicability | Separate cited scope gate; unknown regime is UNASSESSABLE |
| Unit, currency or period mismatch creates a false hold or break | Arithmetic refusal and explicit comparison abstention; conversions cover full period |
| A later announcement erases a mid-season change | Immutable entries and explicit effective windows; ambiguity/gaps refused |
| A known-on filter is oversold as a full historical revision model | Documented its limited announcement-date semantics; no completeness claim |
| Null evidence becomes zero margin or a pass | Missing terms name publisher; undefined margins are null |
| A CF award/publication difference is called a legal deadline finding | Kept only descriptive arithmetic; UK event and regime gates remain open |
| SHA-256 is mistaken for proof of authenticity or truth | Verification checks retained bytes only; legal admission remains a separate decision |

False holds and false breaks remain possible if an adapter supplies false
scope facts, misidentifies a source term, omits a revision, or admits a claimed
conversion without checking its meaning. An official could correctly object
that CF is not the relevant statutory notice, that a new rather than saved
regime applies, that the matched notice covers another lot, or that a timestamp
is a revision rather than first publication. These are mandatory evidence
questions for the proposed rule, not something the arithmetic core can decide.

## Verification and present limits

November 13, 2026, Python 3.12.14: **54 core tests passed**. Full backend suite:
**2,144 passed, 10 skipped, 0 failed; 17 subtests passed** in 19.25 seconds.
Nine skips require Docker and one is the non-Mac refusal case running on Mac.
Two dependency warnings were emitted. The [validation receipt](../research/invariant_core/validation.json)
records the command, tested-code hashes and log/XML hashes. The reference
fixture was restored by the existing hash-identified helper; the existing
reference database was used, not reconstructed. No scoring code was changed.

The core can produce deterministic, sourced comparisons under explicitly
supplied norms and scope, preserve effective changes, and refuse incompatible
or missing evidence. It cannot obtain or authenticate statutes, establish a
legal regime, prove source completeness, infer a financial recovery, or certify
that a publisher's assertion is realised fact. It is a tested foundation, not
yet a demonstrated live statutory invariant. Ghana remains parked, and the
single UK proposal awaits owner approval plus its identified evidence gates.
