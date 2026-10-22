# Monetary atlas: research, accounting and map integration

Research and implementation date: **20 October 2026**.

SUNLIGHT now includes **27 monetary measures**, country observations and a directed
bilateral aid layer. This extends the existing procurement, materials, selected
goods relationships, arms declarations, conflict context and obligation ledger.
It is a source-dated statistical atlas, not a global real-time payment ledger.

## Use the atlas

Open `/watch/#money`, or choose **Monetary atlas** in the rail. Global totals are
clickable measure cards. Choose a card to map country observations; search the
country table to focus the globe. A country profile shows all 27 measures together,
including explicit missing values. The world stays mounted beside every tool.

Choose **Bilateral development assistance** to trace published donor → recipient
relationships with named endpoints, retained source values and a readable/PDF
connection brief. **Investigate this measure/connection** carries its period,
country and monetary source selection into a saved, source-cited inquiry. Optional
AI retains the existing credential and explicit sharing requirements.

The year selector supports 2019–2026. Default source periods prefer the latest
publisher world aggregate; without one,
they use the latest year with mapped national observations. A world series can
stop before some country series; choose an explicit year to inspect its coverage. Selecting a specific year never substitutes another year's value. An
empty 2026 series remains unavailable, never zero or an interpolated counter.

## What was researched and imported

The World Bank WDI definitions identify the source institution, measure,
aggregation method, unit basis and licence. The extract uses the Open Numbers
transformation mirror, pinned at:

- Repository: https://github.com/open-numbers/ddf--world_bank--world_development_indicators
- Reviewed revision: `4252d91d988efc0f116d4fa48e92357b778729e5`
- Mirror package creation: **14 October 2026**; retrieval: **20 October 2026**.
- **61 source files**, with reviewed SHA-256 pins in
  [monetary_source_checksums.json](../scripts/monetary_source_checksums.json).
- **25,993 country/world year observations**
  across **215 catalogue countries/territories** and
  **14,486 bilateral aid pair/year observations** retained.
- The default aid layer has **2,870 signed net pair observations**
  for **2023**, from **31 donor countries** to
  **136 recipients**. Its covered signed total is
  **$86.73B**; this is a subset of development finance, not an
  addition to ODA aggregates.

The build environment denied access to the direct World Bank API through its
configured network proxy. The research therefore verifies the pinned mirror,
its definitions and source hashes; it does **not** claim an independent download
or reconciliation against the live publisher API. Existing older datasets retain
their separate provenance. A mirror refresh does not turn historical data live.

Geographic mapping uses catalogue ISO alpha3 codes, with an explicit WDI `XKX`
to catalogue `XK` alias for Kosovo. Combined Channel Islands reporting and five
historical entities are retained as documented exclusions, never allocated to
successor countries. All 250 catalogue countries/territories remain selectable;
absence of an observation is a coverage gap. Publisher world aggregates may
include estimation or reporting coverage beyond the individually retained rows.

## Default figures and their bases

These figures are rounded for readability. Original source numeric strings are
retained, including signed and zero values. Long floating-point decimals in the
mirror do not imply audited cent-level accuracy. Source USD measures remain
current-dollar series; no exchange conversion or inflation adjustment is added.

| Measure | Period | USD figure | Total basis | Country observations |
|---|---:|---:|---|---:|
| [Goods exports](https://data.worldbank.org/indicator/TX.VAL.MRCH.CD.WT) | 2025 | $26.39T | Publisher world; annual flow | 205 |
| [Goods imports](https://data.worldbank.org/indicator/TM.VAL.MRCH.CD.WT) | 2025 | $26.69T | Publisher world; annual flow | 205 |
| [Services exports](https://data.worldbank.org/indicator/BX.GSR.NFSV.CD) | 2025 | $9.56T | Publisher world; annual flow | 138 |
| [Services imports](https://data.worldbank.org/indicator/BM.GSR.NFSV.CD) | 2025 | $8.75T | Publisher world; annual flow | 138 |
| [Personal remittances received](https://data.worldbank.org/indicator/BX.TRF.PWKR.CD.DT) | 2025 | $925.55B | Publisher world; annual flow | 132 |
| [Personal remittances paid](https://data.worldbank.org/indicator/BM.TRF.PWKR.CD.DT) | 2025 | $662.43B | Publisher world; annual flow | 135 |
| [Direct investment · net inflows](https://data.worldbank.org/indicator/BX.KLT.DINV.CD.WD) | 2025 | $1.80T | Publisher world; net flow | 200 |
| [Direct investment · net outflows](https://data.worldbank.org/indicator/BM.KLT.DINV.CD.WD) | 2025 | $2.08T | Publisher world; net flow | 176 |
| [Portfolio equity · net inflows](https://data.worldbank.org/indicator/BX.PEF.TOTL.CD.WD) | 2025 | $1.88T | Publisher world; net flow | 104 |
| [Portfolio investment · net](https://data.worldbank.org/indicator/BN.KLT.PTXL.CD) | 2025 | $-779.43B | Covered economies only; net flow | 136 |
| [Development assistance received · net](https://data.worldbank.org/indicator/DT.ODA.ODAT.CD) | 2023 | $259.48B | Publisher world; net flow | 136 |
| [Development assistance provided · net](https://data.worldbank.org/indicator/DC.ODA.TOTL.CD) | 2024 | $209.74B | Covered economies only; net flow | 32 |
| [External debt service paid](https://data.worldbank.org/indicator/DT.TDS.DECT.CD) | 2024 | $1.36T | Covered economies only; annual flow | 120 |
| [External debt outstanding](https://data.worldbank.org/indicator/DT.DOD.DECT.CD) | 2024 | $8.94T | Covered economies only; stock | 118 |
| [IBRD financing · net flows](https://data.worldbank.org/indicator/DT.NFL.MIBR.CD) | 2024 | $18.72B | Publisher world; net flow | 63 |
| [IDA financing · net flows](https://data.worldbank.org/indicator/DT.NFL.MIDA.CD) | 2024 | $17.26B | Publisher world; net flow | 97 |
| [IMF concessional financing · net](https://data.worldbank.org/indicator/DT.NFL.IMFC.CD) | 2024 | $-382.26M | Covered economies only; net flow | 13 |
| [IMF nonconcessional financing · net](https://data.worldbank.org/indicator/DT.NFL.IMFN.CD) | 2024 | $1.48B | Covered economies only; net flow | 78 |
| [Primary income received](https://data.worldbank.org/indicator/BX.GSR.FCTY.CD) | 2024 | $7.44T | Publisher world; annual flow | 169 |
| [Primary income paid](https://data.worldbank.org/indicator/BM.GSR.FCTY.CD) | 2024 | $7.99T | Publisher world; annual flow | 169 |
| [Secondary income received](https://data.worldbank.org/indicator/BX.TRF.CURR.CD) | 2024 | $1.66T | Publisher world; annual flow | 165 |
| [Intellectual property receipts](https://data.worldbank.org/indicator/BX.GSR.ROYL.CD) | 2025 | $628.85B | Publisher world; annual flow | 106 |
| [International tourism receipts](https://data.worldbank.org/indicator/ST.INT.RCPT.CD) | 2019 | $1.86T | Publisher world; annual flow | 141 |
| [Government final consumption](https://data.worldbank.org/indicator/NE.CON.GOVT.CD) | 2024 | $18.65T | Publisher world; economic context | 168 |
| [Military expenditure](https://data.worldbank.org/indicator/MS.MIL.XPND.CD) | 2025 | $2.86T | Publisher world; economic context | 150 |
| [Reserves including gold](https://data.worldbank.org/indicator/FI.RES.TOTL.CD) | 2025 | $16.64T | Covered economies only; stock | 132 |
| [Economic output · GDP](https://data.worldbank.org/indicator/NY.GDP.MKTP.CD) | 2025 | $118.35T | Publisher world; economic context | 186 |

## Accounting rules

- No combined “all money” total: exports/imports are counterpart views, not two
  separate transfers. Goods and materials overlap; tourism/IP are services
  subsets; ODA, institutional finance and other income can overlap.
- Publisher world values are identified as such. Without a world observation,
  the atlas sums **only mapped country observations for the same year**, labels
  the result partial, and excludes regional/income-group aggregates.
- Debt and reserve balances are **stocks**. GDP, government consumption and
  military expenditure are context measures. None is a bank-payment stream or
  a total that can be added to procurement.
- Net FDI, portfolio and aid flows may be negative. Signs survive storage,
  calculation, retrieval and review. Positive net aid pairs animate donor →
  recipient; nonpositive entries remain inspectable and are never reversed into
  invented counterflows. The displayed aid total includes all signed entries.
- National totals supply no bilateral counterpart. They appear as country
  reference symbols with explicitly logarithmic absolute sizing; outlined
  symbols identify negative net values. Gray catalogue reference points remain
  where a selected observation is absent. No bilateral remittance, investment or
  debt path is invented from a single national amount.
- Display budgets do not truncate the source register: aid draws up to 70 global
  corridors, balanced by reporting donor, or 80 in a country scope. Every
  positive pair in the retained selected-year scope is searchable/traceable;
  zero and negative rows remain in the source disclosure. Direction animation
  is schematic, not value, current location, actual shipment speed or a bank path.
- Statistical “disbursement” is not an authenticated recipient credit. Match
  stable activity/payment references and independently attributed debit/credit
  entries in Delivery assurance before assessing an unexplained residual.
  Missing records and publication differences are not findings of theft.

## Remaining monetary domains

The following integration inventory identifies source families and accounting
requirements. These are **unconnected targets**, not newly verified live feeds.
The current update does not claim to have enumerated every monetary transaction
in human society. Some transaction-level data are private or never published.

| Domain | Source family | Integration / comparability requirement |
|---|---|---|
| Humanitarian funding | [OCHA Financial Tracking Service / IATI](https://fts.unocha.org/) | Separate pledges, commitments and paid contributions; match activity and recipient identifiers. Overlaps ODA. |
| Climate and biodiversity finance | [OECD climate-related development finance / UNFCCC](https://www.oecd.org/en/topics/climate-finance.html) | Separate commitments, disbursements, grant equivalents and mobilised private finance. Overlaps ODA and loans. |
| Public revenue, tax and expenditure functions | [IMF Government Finance Statistics / national treasuries](https://data.imf.org/) | Government perimeter, cash/accrual basis, fiscal year and local currency must match. Government consumption is not total public spending. |
| Gross loan disbursements and creditor schedules | [World Bank International Debt Statistics / IMF](https://www.worldbank.org/en/programs/debt-statistics/ids) | Gross drawdowns, principal repayments, interest and net flows are different measures; debt balances are stocks. |
| Cross-border banking | [BIS locational and consolidated banking statistics](https://data.bis.org/) | Mostly positions and exchange-rate-adjusted changes; bank residency and nationality measures differ. Not individual payments. |
| Bilateral portfolio holdings | [IMF Coordinated Portfolio Investment Survey](https://data.imf.org/) | Security holdings are positions, not annual transfers; preserve instrument, counterpart and valuation basis. |
| Bilateral direct investment | [IMF Coordinated Direct Investment Survey / UNCTAD](https://unctadstat.unctad.org/) | Ultimate investor differs from immediate counterpart. Stocks, flows and announced projects cannot be combined. |
| Bilateral remittance corridors | [World Bank / national balance of payments](https://www.knomad.org/) | A modelled bilateral matrix cannot stand in for observed settlement. Current national receipts do not identify a sending country. |
| Institutional procurement and project payments | [UNGM / UNOPS / World Bank Projects / national OCDS publishers](https://www.ungm.org/) | Link awards, amendments, executed payments, recipient credits, acceptance and public service evidence by stable identifiers. |
| Subnational budgets and public enterprises | [World Bank BOOST / national budget portals](https://www.worldbank.org/en/programs/boost-portal) | Reconcile transfers between levels of government; avoid counting the same appropriation and disbursement twice. |
| Full commodity and services detail | [UN Comtrade / WTO / UNCTAD](https://comtradeplus.un.org/) | Expand all HS/EBOPS categories with exporter/importer mirror basis, re-exports and freight/insurance valuation kept distinct. |
| Weapons monetary trade and custody | [UN Comtrade HS93 / UNROCA / SIPRI / published tracing reports](https://www.unroca.org/) | HS93 customs values do not equal all military equipment transfers. SIPRI TIV is not USD; unknown custody requires actual tracing evidence. |
| Health, education and social protection finance | [WHO expenditure database / UNESCO / IMF COFOG / ILO](https://apps.who.int/nha/database) | Functional spending overlaps public expenditure and aid. Separate funding source, payer, provider and service delivery. |
| Domestic payments and recipient credits | [Central banks / treasuries / authorised bank and ERP connectors](https://www.bis.org/) | No universal public transaction ledger exists. Authenticated debit and credit evidence must be permissioned and independently reconciled. |
| Insurance, pensions and other financial services | [OECD / IMF / national regulators](https://data-explorer.oecd.org/) | Premiums, benefits, assets and investment income are different bases; cross-border services overlap services trade. |
| Digital assets and informal finance | [BIS / national regulators / attributable public chain records](https://www.bis.org/) | A blockchain address does not identify residency or beneficial ownership. Do not infer country-to-country payments from unattributed addresses. |
| Illicit financial flows and recovered assets | [UNODC / UNCTAD SDG 16.4.1 / published courts](https://unctad.org/topic/statistics/illicit-financial-flows) | Statistical estimates, adjudicated theft and recovered assets are distinct. A trade or reporting discrepancy alone is not stolen money. |

## Interfaces and reproducibility

- `GET /watch-data/money`: latest stated year per measure, country observations,
  signed aid pairs, source metadata, exclusions and integration inventory.
- Optional `?year=2023&country=GH`: filters country rows and aid endpoints while
  retaining the stated global/covered totals and coverage counts. Unknown codes
  and years outside 2019–2026 return 422.
- `scripts/build_monetary_snapshot.py`: fetches only pinned source paths through
  the inherited proxy, verifies reviewed checksums, parses numeric values with
  `Decimal`, rejects duplicate country/year observations and writes the extract.
- `code/monetary_snapshot.json`: bundled data; runtime atlas use requires no
  external API credential or upstream availability.
- Research source `monetary` uses the same snapshot and respects country/year
  selection. The existing bounded lexical retrieval is not an exhaustive
  worldwide investigation; the optional read-only statistics tool provides
  separate measure-specific summaries, with no cross-domain total.

Each indicator retains its original compiler, definition and licence in the API
and atlas. Most are CC BY 4.0; military expenditure retains **SIPRI terms and
conditions** from the source metadata. The mirror's existence does not replace
publisher-specific attribution/licensing requirements.

## Validation

Accounting regression tests cover source pins, world/covered totals, exclusion
of aggregates, signed/zero/missing values, no mixed-year substitution, scope and
bilateral direction. Browser checks use an isolated local ledger and verify the
persistent globe, 27-measure country profile, source-period gaps, aid tracing,
readable brief, saved investigation and mobile layout. See
[VALIDATION_2026-10-20.md](VALIDATION_2026-10-20.md) for final results.
