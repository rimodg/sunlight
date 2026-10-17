# Data behind the global watch

The interface keeps published procurement aggregates, analyzed procurement records, configured annual spending context, annual merchandise trade and selected material exports separate. They cannot be combined into a worldwide completion or theft estimate. Material exports are a subset of merchandise trade: never add the white and yellow layers as independent economic contributions.

## Conflict and organized-violence context

`GET /watch-data/conflicts` serves a bundled **UCDP Candidate 26.0.8** extract. It contains **1,500 preliminary records starting August 5–31, 2026**, some with reported intervals ending as late as September 10. The source mirror was generated October 6; SUNLIGHT retrieved it October 17. Those are publication/retrieval dates, not newer observations. This is a fixed snapshot, not live front lines, an all-2026 record or complete worldwide conflict coverage.

Source: Uppsala Conflict Data Program, Department of Peace and Conflict Research, Uppsala University, via the public [WorldWatch data mirror, revision a01e6fe3dd2fac5f6335cc24eca3ea2296b24779](https://github.com/drdjcannon/worldwatch-data/tree/a01e6fe3dd2fac5f6335cc24eca3ea2296b24779). The source JSON SHA-256 is `daad6da8a79dfdf9ce4b4dee7391797bc7532c83dba0fedf1d742f8e870cac99`, enforced by `scripts/build_conflict_snapshot.py`. The mirror publishes 2,000 records, reserving 500 annual records and retaining 1,500 recent candidate records. SUNLIGHT takes only records starting in 2026; it does not turn the capped slice into national/global totals or use the mirror's separate full-window country totals. Original provider downloads are blocked by this cloud's network policy; the existing public mirror is accessible. SUNLIGHT has not independently recoded the original reports.

UCDP data is attributed under **CC BY 4.0**. The panel links the source, candidate release directory/codebooks, license, pinned JSON, checksum and complete derived snapshot. Citations retained:

- Davies, Shawn, Therése Pettersson and Magnus Öberg (2026), *Organized violence 1989–2025, and violent political protests*, Journal of Peace Research, [doi:10.1093/jopres/xjag046](https://doi.org/10.1093/jopres/xjag046).
- Sundberg, Ralph and Erik Melander (2013), *Introducing the UCDP Georeferenced Event Dataset*, Journal of Peace Research 50(4), 523–532, [doi:10.1177/0022343313484347](https://doi.org/10.1177/0022343313484347).

The source codes state-based conflict, non-state conflict and one-sided violence against civilians. A local fatal-organized-violence observation does not classify its whole country as a war zone. The panel can filter these types separately. Candidate reports can be revised, date intervals may be imprecise, and one record can summarize multiple incidents. News headlines and casualty figures are omitted from SUNLIGHT's derived snapshot; dot size/color does not rank severity.

Only location precision **1 (named location)** or **2 (near a named location)** is plotted: **1,018 records at 658 distinct source coordinates**. Exact coordinate matches share one small, steady red point without random displacement. Multiple source place names can share that reference point; the detail panel preserves and explains them. The other **482** broader-location records remain searchable in the global register but do not become misleading pins at province/country centroids. All source IDs, coordinates, reporting-area labels, intervals and precision codes remain attached.

UCDP reporting areas are not procurement jurisdictions: its `Israel` area includes Gaza/West Bank records. Source labels are preserved; country research filters plotted points by the selected approximate Natural Earth boundary, rather than assigning that reporting area's aggregate to Israel or Palestine. Basemap precision still limits border/small-territory attribution. Clicking a red point opens its source records; the red legend opens the searchable, paginated register and provenance. Keyboard access is provided by that register rather than hundreds of separate animated map targets.

Conflict data does not enter detection scores. No aid/loan amount, stolen-fund estimate, dependency score or causal claim is derived from overlap with material exports or procurement. Those layers have different years and coverage. Missing observations do not establish peace, and sampled point density does not establish conflict intensity. Compare the evidence without silently turning co-location into a verdict.

Reproduce from the exact pinned source file:

```sh
python scripts/build_conflict_snapshot.py \
  --source /path/to/worldwatch-data/ucdp/ucdp-events.json \
  --output code/conflict_snapshot.json
```

## Materials and primary inputs

`GET /watch-data/materials` serves a bundled snapshot with **US$3,951,738,847,968** in **2023** gross material exports, **223 exporting economies**, and **85 distinct HS4 headings**. It needs no runtime provider account or external data call. All 250 catalog countries remain in its register; missing observations stay explicit. Coverage of national totals is broader than coverage of the available leading-partner routes.

The economic source is **CEPII BACI, HS 2017, release BACI_HS17_V202601**, licensed under France's **Etalab Open Licence 2.0**. SUNLIGHT uses the published, BACI-derived numerical partitions from [Trade Atlas at revision d63f2c7ba9e3639d9904da7f490bc69e96468188](https://github.com/Lucas-Speciale/trade-atlas/tree/d63f2c7ba9e3639d9904da7f490bc69e96468188). Retrieved October 17, 2026 UTC (October 16 in New York). The original BACI archive has **not** been independently reprocessed here. No application code, visual design, boundary files or product-label metadata from that project is included. Country geometry and catalog remain SUNLIGHT's existing sources. Each used data file has a pinned link and SHA-256 checksum in the explorer; the builder enforces `scripts/materials_source_checksums.json`.

The SUNLIGHT basket is an explicit operational selection, not a universal or exhaustive definition of raw materials: energy feedstocks, ores/concentrates, mineral inputs, agricultural/forest inputs, primary metals and precious materials. Some HS4 headings include processed forms (for example milled rice, roasted coffee, semi-manufactured gold and unwrought refined copper). The complete code list and individual labels are visible in the material selector and snapshot. Finished manufactures, services and many other agricultural commodities are outside this basket. **2023** is used consistently; the mirror's provisional 2024 observations are not mixed into it. BACI reconciles trade reports rather than measuring audited domestic production. The mirror uses `Other Asia, nes` as its practical proxy for Taiwan; reporting areas can differ from map boundaries.

The global figure sums each country/HS4 export value once. Source values have already been converted to current USD and rounded to whole dollars; SUNLIGHT applies no further thousand-dollar multiplier. Imports remain separate. Country contribution is its selected export value divided by the covered world value for the same material selection and year. The country view also shows selected exports as a share of that country's total merchandise exports. This is gross trade, including possible re-exports and repeated border crossings, not a measure of extraction, ultimate producer origin, GDP, value added, domestic retention or welfare. Country attribution identifies the exporting trade economy.

The source publishes up to ten leading partners per country/product on that country's net-exporter or net-importer side, with a national/product threshold of US$1 million and source geography restrictions. The snapshot contains 56,832 directional source rows; deduplication yields **47,942 exporter/importer/material relationships involving 204 exporting economies**. Outbound shares use exporter product exports as denominator; inbound shares use importer product imports. When both source views identify a link, its outbound view is used. **Shares are rounded to 0.01 percentage point, with a 0.01% lower bound. Exact bilateral monetary values and quantities are not present in these partitions and are not asserted.**

White lights always travel from exporter to importer along schematic great-circle connections between country reference points. Global drawing includes one available leading route per exporting economy before filling its 240-route budget. Country research draws up to 80 routes involving that country. A material filter changes the white layer and its totals without changing procurement data. Country totals are never calculated by summing the truncated route subset. Brightness, particle count and speed encode neither money nor physical tonnage. The source table shows up to 200 leading relationships for the selection; the downloadable snapshot retains every source row, national total and checksum.

Reproduce from the pinned mirror checkout (source hashes and revision are enforced):

```sh
python scripts/build_materials_snapshot.py \
  --source-dir /path/to/trade-atlas/public/data/trade \
  --output code/materials_snapshot.json
```

## Published procurement observations on first load

`GET /watch-data/procurement` serves the bundled, pinned snapshot in `code/public_procurement_snapshot.json`. It does not require external network access at runtime. The source is [Anti-Corruption Compass public datasets / undp-anticorruption](https://github.com/undp-anticorruption/public-procurement-datasets), whose repository describes the CSV files as public data supporting its indicators and visualizations. Source attribution does not imply institutional endorsement of SUNLIGHT or independent verification of the underlying contracts.

- Source revision: `9fd6f26cb22a48b883ee3791fbb3e9da4950f999`, committed August 25, 2026.
- Source files: `tab_1.csv` for country-year totals and `tab_3.csv` for published market breakdowns.
- Source observations: **2017–2024**, 447 unique country-year rows covering **59 countries** across the period.
- Default **2024** view: **10,617,058 source contracts**, **US$4,301,531,960,000**, **52 countries**. This is covered procurement, not a complete global-spending estimate.
- Values are published in million USD, at up to two decimal places. Conversion to USD is exact in decimal arithmetic; it does not create precision beyond the source's 0.01 million USD granularity.

Each total appears repeatedly for different risk indicators. The builder selects the `ALL` contract-value group and retains one consistent total per country-year. Conflicting repeated totals cause a build failure. It excludes the overlapping `EU` regional aggregate, maps `UK` to ISO `GB`, and keeps years separate. The global value is the sum of the unique country-year rows for the selected year; it never adds every observation year together. Repeated indicator-availability/category rows are similarly collapsed without multiplying their values. Published market slices may be incomplete; SUNLIGHT does not invent a residual category or claim they reconcile to national totals.

Source CSV SHA-256 checksums are enforced by `scripts/build_public_procurement_snapshot.py` and exposed in the source panel. Regenerate from the two exact source files at the pinned revision:

```sh
python scripts/build_public_procurement_snapshot.py \
  --source-dir /path/to/pinned-source-files \
  --output code/public_procurement_snapshot.json
```

The source has no completion documents or verified delivered amounts. A procurement-to-completion gap cannot be calculated from these aggregate counts. Public aggregate context remains separate from uploaded contract-level evidence and SUNLIGHT's own findings.

The map and country directory include **all 250 countries and territories** in the country catalog. A country missing from this source remains searchable, visible and selectable, with no invented spending amount. At a selected year, markers can show a country's latest observation at or before that year; each marker and country view states the observation year. The global total always uses exactly the selected year. It therefore need not equal a sum of markers with mixed latest years.

## Analyzed procurement evidence

Your OCDS-shaped JSON supplies a separate session register. Its values, source documents, completion declarations, milestone counts and reproducible receipts reflect only actual analyzed records. They are not added to the public snapshot totals, where overlaps cannot be reconciled from aggregates. Reloading clears this analyzed session state while the bundled published figures remain available.

A complete national/global ingestion service still needs release identity/version histories, currencies/stages, source timestamps, document access and corroborated delivery evidence. Country inclusion on the map does not imply complete country data coverage.

## Optional annual context counter

`GET /watch-data/context` exposes a deployment-configured annual baseline. It is unavailable by default, and its card appears only when a baseline is configured. The published procurement card does not depend on this estimate. To configure a cited baseline in Render Environment, supply all of:

- `SUNLIGHT_PROCUREMENT_ANNUAL_ESTIMATE`: positive finite annual amount in currency units.
- `SUNLIGHT_PROCUREMENT_ESTIMATE_YEAR`: the baseline year, no later than the current year.
- `SUNLIGHT_PROCUREMENT_ESTIMATE_CURRENCY`: uppercase three-letter currency code (default USD).
- `SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_URL`: HTTPS source-document URL.
- `SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_TITLE`: readable source title.

The deployment owner must review the source and baseline. The endpoint validates configuration, not the underlying economic estimate. Invalid or incomplete configuration produces an unavailable state.

The displayed current-year pace is `annual baseline × elapsed UTC calendar year / length of UTC calendar year`. It updates every second, handles leap years and is labeled **modeled pace**, with baseline year and source exposed in the value panel. It is not observed spending, a forecast, money lost or a sum of the analyzed documents. It must not be subtracted from the partial procurement register to infer a global delivery gap.

## UN Comtrade annual trade preview

`GET /watch-data/trade` retrieves the public [UN Comtrade preview API](https://comtradeapi.un.org/public/v1/preview/C/A/HS), with no added provider secret. Query:

- Classification HS, annual frequency A, goods type C.
- Period **2023**, flow **X** (exports), commodity **TOTAL**.
- All primary partners requested; secondary partner 0, customs C00, mode 0.
- At most 500 preview records per reporter.
- Selected source reporter codes: 842, 156, 276, 392, 826, 251, 699, 528, 76, 710.

Country research can request any recognized country reporter via `/watch-data/trade?reporter=<ISO numeric code>`, with source-code mappings applied and a bounded per-country cache. The global initial request remains a selected-reporter view; it does not launch hundreds of provider requests at once. This is **partial source coverage**, even if every request succeeds. World/region aggregates, self-links, mismatched periods/flows/commodities, invalid values and conflicting duplicate bilateral totals are excluded. Values are in current USD as returned by the source. Source reporting flags and names are retained. Some Comtrade reporting areas use non-ISO codes: the geographic mapping handles US 842→840, India 699→356, France 251→250, Italy 381→380, Norway 579→578 and Switzerland 757→756; raw source codes remain attached to the query links. This mapping does not assert that reporting areas exactly match political borders. Unsupported aggregate areas are not assigned to a country.

Successful responses cache for 12 hours. Partial/errors cache for one hour. A lock prevents simultaneous client requests from fanning out new source requests. A previous successful snapshot may be returned as **stale**, preserving its original fetched timestamp and reporting the failed refresh. There is no generated fallback dataset. The cache is in memory, resets on service restart and is not a durable source archive.

Yellow moving points represent dated bilateral relationships between country reference points. They are not live shipments, physical route geometry or government procurement flows. The top 80 available links are drawn, with source values and all available links in the table; country research filters the trade layer by the chosen country. Light speed and repetition are visual pacing only.

The outbound policy in this development cloud denied `comtradeapi.un.org`. Parsing, filtering, caching, failure/stale behavior and the interface were tested with fixtures; actual provider retrieval on Render remains unverified. The deployed UI states loading/partial/stale/unavailable explicitly. A source that fails is never described as a functioning live global feed.

## Arms declarations and accountability

`GET /watch-data/arms` serves a pinned historical UNROCA mirror, normalized from
[Klohto/UNROCA-scraper](https://github.com/Klohto/UNROCA-scraper/tree/7291ca6a06c4095d0c92e0c544337edff1d621ef),
captured June 16, 2023. The bundled years are **2020–2022**, not current-year
tracking. The three source files and SHA-256 checksums are exposed by the API and
in the blue legend's explorer. Regenerate using:

```sh
python scripts/build_arms_snapshot.py --source-dir /path/to/pinned-unroca-mirror
```

Only export/import declarations are retained; holdings and production are
excluded. The 6,953 source transfer rows yield 6,832 normalized records. Identical
source duplicates are retained once with a repetition count; affected category
sides are unassessable rather than silently summed. There are 121 repeated groups
and 57 normalized records without usable quantities.

A comparison key is `(year, exporter, importer, family, category)`. Each side sums
its usable declared items separately. Missing counterpart reports are **unknown**,
not zero or proof of non-reporting outside this partial mirror. Any unknown
quantity, duplicate ambiguity or unsafe sum prevents a numerical comparison.
Where both sides are assessable, the signed difference is export declaration
minus import declaration. Equal counts are not verified weapon-identity matches.
Differences require review of timing, models, temporary transfers, corrections
and category definitions. They do not quantify stolen or diverted weapons.

For **2022**, this method produces 1,392 pair/category groups: **46 comparable**
(15 equal, 31 different), **1,234 one-sided** and **112 ambiguous**. These are
comparison-group counts, not a total number of weapons. Counts in different
categories/families are never added into one physical weapons total, and neither
USD nor SIPRI TIV is manufactured from UNROCA item declarations.

The map has 678 distinct available declared exporter/importer relationships in
2022; up to 160 are drawn globally, chosen to include available exporting
countries before allocating additional links. Positive assessable declarations
on either side can support a relationship. Both declarations never create two
transfers. Small blue points use country reference centers and great-circle
interpolation, not actual routes, shipment positions, verified recoveries or
untraced-weapon locations. Year/category controls filter the explorer and map.

### Inspected audit summaries and remaining ground-evidence gap

Two separately attributed GAO audit records are included: **GAO-24-106289**
(Ukraine, March 13, 2024) and **GAO-09-267** (Afghanistan, January 30, 2009).
Their titles, dates and limited summaries were inspected in the public
[CetiAlphaFive/gao metadata mirror](https://github.com/CetiAlphaFive/gao/blob/3e7d52cfb2bac0940de9ffa61f9c25bba3965ef4/inst/extdata/gao_links.rds),
pinned at `3e7d52cfb2bac0940de9ffa61f9c25bba3965ef4`, source SHA-256
`1dd719514cd67de582b3b8ff93d0b77f195d8c1a8997256986e24a3e05f0df05`.
`code/arms_audit_context.json` contains the limited factual summaries and original
publisher links. No mirror package code or complete database is redistributed.
The full GAO reports were not independently inspected. These records document
historical accountability concerns within their audit scopes, not present-day
custody or proven theft. They carry **no recovery-site coordinates or matched
declaration IDs**, and are not plotted as precise field observations.

A global official-to-ground diversion gap is **not measurable from these
sources**. Annual declarations are flows; field recoveries are selective stock
observations. A defensible reconciliation requires independently verified
weapon/batch identity, comparable periods, documented transfers, custody and
inventory evidence. SUNLIGHT does not subtract unmatched field sightings,
audit-summary dollar figures or absent reports from declared counts. No arms or
conflict variable is added to procurement detection scores.

### Point animation

All flow layers now use luminous **points without tails, along thin fixed country-to-country lines**.
Visual traversal remains 1.8 seconds per relationship, independent of economic
value, quantity or source date. Blue particle radius is 1.9 map units, matching
the small red conflict points. This is accelerated presentation of dated data,
not real-time monitoring. System reduced motion remains supported.

The connection register and inspector expose the actual source measure for each relationship. Selecting a route highlights its direction and opens its evidence; the full register includes available relationships omitted from the bounded map sample. Exact bilateral material USD and procurement theft are not inferred from rounded trade shares. Comparable arms discrepancies can be filtered as review leads, with source reports and next-evidence requirements attached. See [connection research](INVESTIGATION_INTERFACE.md#inspecting-a-connection).
