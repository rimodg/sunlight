# Global monetary workbench

SUNLIGHT needs to help an operator answer five connected questions: **what is
reported, where, for which period, what arrival evidence exists, and who should
check the unresolved difference?** A globe without these handoffs is a display.
A discrepancy without a consistent accounting basis is not a usable finding.

Treasury and development-finance teams need to trace identified funding and
recipient evidence. Procurement and receiving teams need accepted delivery and
service evidence. Audit teams need reproducible comparisons and retained review
work. Economic researchers need definitions, periods, country coverage and
explicit unknowns. These users share a working surface but ask different
questions of the evidence.

The interface therefore keeps three evidence levels distinct:

| Level | What an operator can establish | Working interface |
| --- | --- | --- |
| Published economic context | A source reports a defined amount for a period and country or bilateral relationship | Monetary atlas, globe and source corridors |
| Comparable statistical change | The same monetary measure changed between two retained source years on a compatible basis | Compare & history, exact annual observations and readable export |
| Individual accountability | Attributed execution, arrival, acceptance or public benefit records can be reconciled for a registered obligation or case | Delivery assurance, Records & review, engine results and Review queue |

A macroeconomic difference does not identify an unpaid procurement obligation.
A source-reported disbursement does not independently authenticate a recipient
credit. Connecting these levels requires stable transaction, programme,
recipient and document identities. The current interface exposes that next
step rather than fabricating a join between unrelated records.

## Implemented operator journey

1. Open Monetary atlas beside the persistent globe. The selected measure appears
   first, with its actual source year, accounting type, global perimeter and
   country-observation count. The full measure catalogue is available below the
   result instead of pushing the selected result behind 28 cards.
2. Choose a monetary domain and period. Focus any catalogue country by name or
   ISO code. The map and desk show that country's observation and retain the
   global figure separately. Missing observations remain unavailable.
3. Inspect country observations, order them by absolute value, signed value or
   name, or trace a positive bilateral aid pair into the existing source
   inspector. Source corridors retain their own reporting periods and evidence.
4. Compare up to four countries and the world/covered series for one measure.
   Choose baseline and comparison years. Use the annual chart to inspect a
   source observation and open that year on the map. Focus a comparison country
   directly from its result card.
5. Export the exact scoped analysis as a readable print/PDF brief or CSV.
   Country codes, years, source revision, units and accounting basis are retained.
6. Carry the selected countries and full year range into a saved investigation.
   Monetary, registered source and delivery evidence are selected explicitly.
7. Open the recipient-evidence handoff to review registered evidence or add
   delivery records. The handoff states its deployment/country scope, all-record
   periods, and lack of an automatic join to the chosen statistical measure.
8. Inspect Coverage & sources to see the 27 connected monetary measures, the
   bilateral aid layer and 17 researched domains requiring integration.

The workspace link retains country, measure, period, work view, comparison
countries, baseline and aid role. It records the current source revision. A
different revision on a future deployment produces an explicit notice; the link
does not itself archive an older dataset. Unrelated case/obligation query
parameters are excluded from the shared monetary link.

## Calculation contract

`code/monetary_analysis.py` implements one-measure, current-USD analysis over the
retained 2019–2026 source window. It uses decimal strings and Decimal arithmetic.
No new statistical or fraud-detection threshold is introduced.

- Missing years are explicit nulls; no interpolation or replacement year is used.
- Charts connect consecutive observed years. They preserve gaps and are labelled
  as current USD, without inflation adjustment.
- An absolute difference requires observations on both selected dates and the
  same source basis. A covered aggregate also requires the identical set of
  reporting economies or bilateral pairs. Coverage changes block the aggregate
  change instead of producing a false comparable residual.
- Publisher world aggregates keep their published world basis. The number of
  mapped national observations is not a measured share of worldwide spending.
- Percentage change requires a positive baseline. Zero and negative baselines
  retain a valid absolute difference but have no percentage.
- Debt and reserve positions stay stocks. A position change is not an amount
  paid during the year. GDP remains economic context.
- Aid country comparisons explicitly select recipient or donor role. Signed
  entries are retained in totals, comparisons and exports; a missing donor
  observation is unknown, not zero. Only positive source pairs animate.
- No all-money sum combines trade, remittances, investment, ODA, debt and GDP.
  Overlap and counterpart reporting make such a number misleading.

API routes:

```
GET /watch-data/money/analysis
GET /watch-data/money/analysis/report
GET /watch-data/money/analysis.csv
```

Parameters: `measure`, up to four comma-separated `countries`, `baseline`,
`year`, and `direction=inward|outward` for aid. Invalid identifiers, duplicates,
excess countries and misordered/out-of-window years return 422. No network
requests are required to reproduce the pinned extract analysis.

Readable HTML escapes source text. CSV preserves the exact source decimal
strings, labels missing values with an unavailable basis, and retains the source
revision. Spreadsheet applications may round imported numerical values; decimal
precision in the source is not an accuracy guarantee.

## Source and operational boundaries

The source base remains the pinned WDI mirror documented in
[MONETARY_ATLAS.md](MONETARY_ATLAS.md), alongside the existing trade, materials,
procurement, conflict and arms layers. This upgrade adds analysis and handoffs;
it does not claim new worldwide payment feeds or additional source coverage.

Animated corridors represent dated reported relationships. They do not measure
instantaneous transactions, transport paths or settlement speed. National totals
without known counterparts remain country observations.

The existing delivery and procurement engines still work on their registered
inputs. Optional AI still requires its configured provider and explicit excerpt
sharing. Independent bank/issuer authentication, authorized institutional roles,
durable production storage and independently evaluated operational accuracy
remain deployment requirements. No payment hold, sanction or external referral
is executed by these views.

## Validation — 2026-10-20

The full backend suite passed: **2,122 passed, 3 skipped**, excluding the optional
Docker-live suite. The frontend's 48 tests and production build passed.

Six added backend tests cover exact decimal differences, changed aggregate
coverage, zero/negative baselines, missing periods, signed aid roles, stock
meaning, invalid scopes and escaped readable/exact CSV exports.

The retained `smoke-monetary-workbench.cjs` exercises published data through the
real local API: shared scope reload; comparisons; exact PDF/CSV content; saved
inquiry scope; unknown 2026; stocks; aid direction; coverage inventory;
unavailable analysis and retry; recipient review; missing country observations;
the same globe canvas; and mobile layout. Endpoint failure and revision-mismatch
states are deliberately injected during those checks.

The existing monetary atlas and persistent-world browser journeys also passed,
covering aid tracing, source briefs, saved inquiries, country profiles, reduced
motion and mobile layout. These are local application checks; a Git push does
not independently verify Render's hosted rollout.

The review-queue and delivery-assurance regressions passed as well, including
exact record handoffs, preserved drafts, version conflicts, sender/recipient
reconciliation and the calibrated delivery check. The new journey also checks
that clearing a monetary measure restores the available flow layers.

Published-data views:
[country comparison](interface/Monetary-Workbench-Comparison.png),
[mobile workbench](interface/Monetary-Workbench-Mobile.png).
