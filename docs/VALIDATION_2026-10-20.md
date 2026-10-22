# Monetary atlas validation — 20 October 2026

The update expands the existing watch using a pinned WDI mirror, with a separate
source-dated monetary atlas and bilateral net aid relationships. Detection rules,
calibrated thresholds and authenticated fund-transfer capabilities are unchanged.

## Data and calculation checks

The extract includes 27 measures, 25,993 country/world year observations across
215 catalogue economies and 14,486 aid pair/year observations. There are 2,870
signed net aid pairs for 2023, including 2,780 positive pairs available for tracing.
The signed covered aid total is approximately USD 86.73 billion. It is not added
to ODA aggregates. All 61 raw source files have reviewed SHA-256 pins.

Tests check that publisher world observations exclude regional aggregates;
partial covered sums use one year and retain signs; stocks remain separate from
flows; missing observations remain unknown; national totals do not invent bilateral
endpoints; code mappings include Kosovo; and selected country/year/source filters
remain effective in the API and research statistics. Research statistics retain
bilateral aid separately from national ODA and preserve both-endpoint scope.

Commands:

```sh
/workspace/.venvs/sunlight/bin/python -m pytest -q --ignore=tests/test_docker_live.py
npm --prefix sunlight-dashboard test
npm --prefix sunlight-dashboard run build -- --base=/watch/
git diff --check
```

Final results: **2,106 backend tests passed, 3 skipped**; **48 frontend tests
passed**; production build passed. The existing Starlette TestClient deprecation
and Vite bundle-size advisory remain. Docker live tests were excluded; no Docker
or remote Render deployment validation is asserted by this run.

## Actual-browser checks

Chromium/Playwright ran against an isolated local API and SQLite ledger.

- Monetary atlas: all 27 measure cards plus the aid layer, monetary search,
  source-year selection, unavailable 2026 observations, a 27-measure Nigerian
  profile, country focus, source-preserving aid tracing, readable connection
  brief, saved source-scoped inquiry and mobile layout. The same globe canvas
  remained mounted throughout. No page errors or mobile horizontal overflow.
- Existing world workbench: source relationship lookup/trace/brief, saved
  investigation, country search, delivery and records docks, reduced motion,
  mobile split view and no SVG mutations during rotation.
- Existing delivery assurance: worked example, calibrated checks, guided new
  obligation, debit/credit reconciliation, acceptance shortfall, evidence-backed
  follow-up, corrections, concurrent-review handling, reload, exact obligation
  inquiry, readable PDF and country handoff. No browser errors.

The expanded global source scene recorded about 47.4 frames/second and 33.4 ms p95
frame intervals in the local workbench regression while other validation work was
running. This is an environment-specific sample, not a performance guarantee or
live financial activity. Drawing budgets remain separate from complete retained
source registers. The monetary browser regression is
`sunlight-dashboard/scripts/smoke-monetary-atlas.cjs`.

Review the [atlas screenshot](interface/Monetary-Atlas.png) and
[country profile](interface/Monetary-Country.png).

## Source and deployment boundaries

Direct publisher API access was blocked by the configured environment network
policy. Data was retrieved from a pinned Open Numbers WDI mirror; there was no
independent current-publisher comparison. Source revision, definitions, licences,
file hashes, observation years, reporting exclusions and source URLs are retained.
See [the research and accounting notes](MONETARY_ATLAS.md).

No full worldwide payment census, live recipient bank credits, automatic theft
finding or intervention authority is supplied. Seventeen unconnected integration
domains are documented in the interface. Authenticated settlement and final
service evidence still require institution-specific connectors and mandate.

The repository branch can trigger Render auto-deploy; successful branch publication
alone does not establish that the remote build is Live. No paid hosting settings
or external institutional records were changed.
