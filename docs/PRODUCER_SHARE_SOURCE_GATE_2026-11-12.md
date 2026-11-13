# Producer share: primary-source gate, November 12, 2026

Status: **BLOCKED at Task 1. No invariant, legal profile or tests implemented.**
Branch invariant-producer-share starts at origin/main
`0617f5c888c841a2293a28bf2e2509c059edaddd`. The running watch and its data were
not read, changed, restarted or used by this investigation.

## Statute admission

The enacted text of Ghana Cocoa Board Act, 2026 (Act 1182) was not obtained
from an official source. Consequently there is no admitted section number,
verbatim statutory wording, commencement date, interpretation of realised gross
FOB, statutory price-setting authority, exception or adjustment clause. These
fields remain unknown. No press or institutional summary is promoted to law.
It is not possible to supply the requested Act-in-its-own-words note or an
exhaustive press-versus-statute comparison without that text.

Searches covered the exact Act title/number and official Parliament, COCOBOD,
Finance Ministry and Judicial Service domains. Parliament's public Acts
navigation and COCOBOD's resources listing yielded no enacted text in the pages
read. Parliament's Bills listing includes a Cocoa Board Bill, not proof of the
final Act. The parliamentary repository search, committee-report page and
legacy repository returned HTTP 403 on direct retrieval. A third-party Eskwai
catalogue/preview was found but was not admitted as an official statutory source.
This is a failed acquisition, not proof that no official copy exists anywhere.

The [ISD assent announcement](https://www.isd.gov.gh/president-assents-to-10-bills-fulfils-cocoa-farmer-price-pledge/)
is dated August 26, 2026 and reports assent. It is not the signed/Gazetted Act
and does not establish its commencement mechanics. An assent announcement date
must not silently become the implementation's statutory commencement constant.

## Primary announcements obtained

The [source manifest](../research/producer_share/source-manifest.json) records
URLs, UTC retrieval timestamps, byte sizes, SHA-256 hashes, textual locators,
HTTP outcomes and exact external snapshot paths. Hashes identify retrieved HTML
bytes, including page framing; they do not authenticate a legal proposition.
HTTP-error bodies are explicitly not admitted as document content.

- [COCOBOD, August 4, 2025](https://cocobod.gh/news/government-announces-producer-price-of-cocoa-for-the-20252026-cocoa-season),
  paragraphs 4-9: declares 70% against USD7,200 gross FOB, USD5,040 producer
  price, GHS10.25/USD, GHS51,660 per tonne, and commencement of this price on
  August 7. Paragraph 6 describes a combination of outstanding contracts and
  a forecast, not a later audited realised-season return. Paragraph 5 reports
  63.9% for the earlier setting; paragraphs 11-14 describe subsequent currency
  support and a different share. Thus 63.9% is not established here as one
  immutable realised result for the whole 2024/25 season.
- [COCOBOD, October 2, 2025](https://cocobod.gh/news/review-of-producer-price-for-the-202526-cocoa-season),
  paragraphs 2-6: confirms the opening setting and raises it to GHS58,000 per
  tonne, effective October 3. This intervening increase is missing from the
  supplied opening-to-closing summary.
- [COCOBOD, September 25, 2026](https://cocobod.gh/news/review-of-the-producer-price-of-cocoa-for-the-202627-cocoa-season),
  PRODUCER PRICE: confirms GHS41,392 as the preceding setting, GHS42,400 as the
  new setting, a declared 71.18% and GHS2,650 per 64-kilogram bag. The EFFECTIVE
  DATE heading sets the price and season opening to September 25. This primary
  declaration confirms the reported price/share, but supplies no numerical
  realised gross FOB denominator or a complete realised accounting period.
  The original instrument reducing the preceding season to GHS41,392 was not
  acquired in this bounded investigation; the later official release confirms
  its existence, not its original effective date.

The two supported discrepancies are an omitted in-season increase and
oversimplification of the earlier share as a season-wide constant. Exact legal
comparisons with press wording remain blocked. Official summaries also use
world-market price and realised gross FOB language; their legal equivalence
must not be assumed without the Act's definitions.

## Corrections to the implementation plan before coding

1. An announced-share HOLDS can describe only a sourced declaration against an
   admitted threshold. Keep it distinct from a realised-share result. The
   2026/27 test must not force a statutory HOLDS before the Act and applicability
   are admitted. The requested 2024/25 NOT_APPLICABLE test belongs after legal
   commencement is verified, not before a date is guessed.
2. Independently recomputing 71.18% requires a published numerical denominator
   on the same currency, unit and period basis. Computing the denominator as
   42400 / 0.7118 and dividing back would merely reproduce the input claim.
   No worked 2026/27 statutory arithmetic or margin is presented as verified.
3. Source unit pairs need special care: 42400 / 2650 equals 16 bags, whereas
   1000 / 64 equals 15.625. Simple metric conversion gives
   2650 * 1000 / 64 = 41406.25, not 42400. Gross bag weight, pricing weight or
   the source's tonne convention must be established by cited evidence. Do not
   infer a net bag weight or silently treat the pair as a generic conversion.
4. Capture each announcement with its effective interval and any later revision.
   A season identifier alone would erase the documented price change. A separate
   realised-season check needs the legally defined denominator and corresponding
   numerator/accounting basis; do not average declarations without evidence.
5. Do not claim the realised figure is unpublished merely because it was absent
   from this release. Its actual availability and legally responsible publisher
   remain to be researched after the statute gate. Do not invent a publishing
   duty or select a spot/forecast price as a substitute.

These are pre-implementation source-review findings, not a completed adversarial
review of a built rule. They guard against false holds from declarations or
circular arithmetic and false breaks from wrong dates, currencies, units or
superseded price settings. An official could reasonably challenge any of those
unstated assumptions; the final review must use the admitted Act itself.

## Exact resumption requirement and scope today

Obtain an official-hosted enacted Act 1182 or an official Gazette copy with
verifiable issuing provenance and publication/commencement details. Read its
pricing section, definitions, adjustment/exception provisions and transitional
terms before admitting constants. A bill, third-party transcription, press
summary or issuer's explanation alone does not satisfy the owner's source gate.
Other provisions mentioned by official summaries, including processing and
financing reforms, remain candidates only; none is implemented here.

Today this branch can document the retrieved official price declarations and
their gaps. It cannot state the Act's legal test, evaluate statutory compliance,
produce a realised share, or label any season a breach. Tasks 2-4 are not started.
No invariant tests or backend suite were run for this documentation-only stop;
no earlier test count is presented as a new result. Verification checked the
saved source bytes against their manifest hashes and the Git diff for whitespace.
