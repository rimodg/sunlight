# Data behind the global watch

The interface keeps three quantities separate: analyzed procurement records, annual spending context and annual merchandise trade. They cannot be combined into a worldwide completion or theft estimate.

## Procurement observations

The current procurement source is the user's analyzed OCDS-shaped JSON. It is a session register, not an automatically collected worldwide procurement database. Values change when new records are analyzed. There is no fabricated per-second observation counter. Country/category/document coverage reflects the available records only.

A future national/global ingestion service must supply release identity/version history, currencies and procurement stages, source timestamps, source documents and delivery/corroboration evidence. Without that coverage, SUNLIGHT cannot truthfully present full country expenditure or a worldwide completed-value gap.

## Optional annual context counter

`GET /watch-data/context` exposes a deployment-configured annual baseline. It is unavailable by default. To configure a cited baseline in Render Environment, supply all of:

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

This is **partial, selected-reporter coverage**, even if every request succeeds. World/region aggregates, self-links, mismatched periods/flows/commodities, invalid values and conflicting duplicate bilateral totals are excluded. Values are in current USD as returned by the source. Source reporting flags and names are retained. Some Comtrade reporting areas use non-ISO codes: the geographic mapping handles US 842→840, India 699→356, France 251→250, Italy 381→380, Norway 579→578 and Switzerland 757→756; raw source codes remain attached to the query links. This mapping does not assert that reporting areas exactly match political borders. Unsupported aggregate areas are not assigned to a country.

Successful responses cache for 12 hours. Partial/errors cache for one hour. A lock prevents simultaneous client requests from fanning out new source requests. A previous successful snapshot may be returned as **stale**, preserving its original fetched timestamp and reporting the failed refresh. There is no generated fallback dataset. The cache is in memory, resets on service restart and is not a durable source archive.

Yellow trails represent dated bilateral relationships between country reference points. They are not live shipments, physical route geometry or government procurement flows. The top 80 available links are drawn, with source values and all available links in the table; country research filters the trade layer by the chosen country. Light speed and repetition are visual pacing only.

The outbound policy in this development cloud denied `comtradeapi.un.org`. Parsing, filtering, caching, failure/stale behavior and the interface were tested with fixtures; actual provider retrieval on Render remains unverified. The deployed UI states loading/partial/stale/unavailable explicitly. A source that fails is never described as a functioning live global feed.
