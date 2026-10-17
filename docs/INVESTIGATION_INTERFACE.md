# Global watch and country research

`/watch/` opens on a full-width globe. The record register and evidence inspector open as overlays so they do not permanently narrow the map. Import continues to use the live single/batch analysis API, jurisdiction calibration, capacity allocation, rule citations, input gaps and exact-response verification packets.

## Motion and research

The global globe rotates west to east, one accelerated turn every three minutes. Dragging, keyboard rotation, record inspection and source panels do not stop global rotation. All 250 catalog countries and territories have selectable reference markers and a searchable directory, including places without source data. Country boundaries also support direct map selection. Country search accepts common/official names, translated aliases and ISO codes; ambiguous names require choosing a result. Selecting a country centers, highlights and zooms its boundary and holds rotation until **Return to global watch** or **Global view**. Small countries absent from the 1:110m basemap have a labeled reference point and an explicit resolution notice.

System reduced-motion preferences remain respected. There are no pause or illustrative-flow controls. Annual trade lights continue during country research unless reduced motion is active. Neither lighting speed nor particle counts represent shipment frequency or monetary volume.

Flow particles use a dedicated canvas layer driven by `requestAnimationFrame`, separate from React's map and panel updates. A visual route crossing takes **1.8 seconds** (previously six seconds), with no tails or route strokes and cached glow sprites. Route geometry and back-face clipping use sampled great-circle unit vectors and the same orthographic camera as the SVG map. The slower earth rotation retains its three-minute period; map geometry updates at up to 20 Hz while particles follow the display refresh rate. Resizing and high-DPI displays resize the canvas buffer. Reduced motion holds particles still but redraws for explicit zoom, drag, selection and filters; hidden tabs suspend motion without a catch-up jump.

A five-second local Chromium comparison at 1512×982, with 240 real material routes and 80 explicit trade fixture routes, measured **40.9 RAF frames/second before and 60.2 after**. The 95th-percentile frame interval fell from **50 ms to 16.8 ms**; observed long tasks fell from five to zero. This is a local browser responsiveness measurement, not a frame-rate guarantee for every device or a live data throughput measure.

## Published procurement numbers

The published procurement card opens on **US$4.30 trillion** and **10,617,058 contracts**, covering **52 countries in 2024**. The bundled source includes 59 countries across 2017–2024. These are sourced country-year aggregates, not live worldwide spending or SUNLIGHT-detected cases. Clicking opens source-year selection, published market slices, a country register, checksums and pinned source links. The independent analyzed-record card still opens contract-level findings, references and evidence gaps. Their values are never combined.

The publisher repeats totals across risk indicators. The snapshot builder deduplicates them, validates consistent repeats, excludes the overlapping EU aggregate, maps UK to GB and keeps source years separate. Source money is converted from million USD using decimal arithmetic. See [data provenance and limitations](GLOBAL_WATCH_DATA.md).

## Analyzed procurement and completion evidence

Click the documented value near **Procurement watch** to open categories, values, document references and completion-evidence gaps. Amounts remain separate by currency and stage: contract value, award value or tender estimate. No currency conversion occurs. Multiple releases with a repeated OCID are excluded from totals rather than double-counted or silently reconciled. Records missing identifiers or with analysis errors are excluded; counts disclose these exclusions. The register still permits inspection of every result.

The category view uses `tender.mainProcurementCategory` (goods, works, services or unclassified). It lists HTTP(S) source-document links, documents without usable URLs, the record source and its country. Root documents and metadata survive API normalization and remain bound by the submitted-request receipt. Releases containing their own `contracts[]` are correctly treated as single releases, distinct from an explicit portfolio wrapper.

Completion indicators distinguish:

- Records containing completion-document links from records without them.
- Recorded amounts attached to records without completion links, by currency/stage.
- Records declaring at least one contract complete.
- Implementation milestones marked met, not met or partially met, with repeated milestone identifiers excluded within a contract.

These are documentary and declared-status measures. A link does not authenticate the referenced document or prove delivery. Missing links do not establish theft, non-delivery or a monetary loss. Milestone counts are not a project completion percentage. Independent corroboration remains the separate evidence/delivery workflow.

Country attribution uses the buyer's explicit country, directly or through buyer parties. It never uses the selected analysis profile, supplier location or delivery point to infer buyer nationality. Country figures cover the current analyzed inputs, not the nation's complete expenditure. Unknown coverage is stated explicitly. Reloading clears analyzed session records; download evidence packets to retain them.

## Trade layer

Yellow paths use the separately sourced, dated UN Comtrade context described in [GLOBAL_WATCH_DATA.md](GLOBAL_WATCH_DATA.md). Paths connect country reference points along great circles. The globe displays up to 80 trade links, selecting one leading route per available exporter before filling the budget; country research filters links to those involving the selected country. Source tables retain the available links, source query, period, values and source reported flag. Missing trade data produces an unavailable state, with no fictional substitute routes.

White paths show selected material exports from the bundled 2023 CEPII BACI-derived snapshot. The white counter opens national export values, global shares, material composition, country merchandise-export shares and rounded leading-partner shares, with source checksums and a complete snapshot download. All 250 countries/territories remain searchable, including those without source observations. Country views keep material contributions separate from procurement coverage and analyzed records. The 85-code basket includes some processed primary inputs; it is defined explicitly in the source panel. Gross exports are not GDP or domestic extraction. White lights travel exporter to importer, use the same visible glow as yellow lights, and continue during country research while globe rotation holds. Global drawing covers all 204 available exporting origins within a 240-route budget; country research draws up to 80 routes. The material selector filters both the white map layer and contribution totals. White rings identify countries with export data but no published procurement count. Source limitations and precision are documented in [GLOBAL_WATCH_DATA.md](GLOBAL_WATCH_DATA.md).

Supplied procurement relationships appear as distinct dashed paths. An award supplier with a valid `location.geometry` Point can be linked to the first valid delivery point in `tender.deliveryLocations[]` or `tender.items[].deliveryLocation`. A supplier ID can instead resolve its origin through the matching `parties[].location`. These location fields are visualization extensions. Cancelled/unsuccessful awards, invalid coordinates, duplicate links and identical endpoints do not produce links. Up to 20 selected-record links and 20 other supplied links are drawn; the map states drawn/available counts. Relationships are not shipment or payment tracking. Geography never enters the detection score.

## Conflict observations

Small steady red points show **UCDP Candidate 26.0.8** observations whose source start dates fall in **August 2026**. They use a separate cached canvas above the trade lights and country badges, with uniform 1.9-unit radius, muted red fill and no glow/pulse. Click selection uses the same orthographic camera, including back-face rejection; marker selection takes precedence over an overlapping country badge. The red legend provides keyboard access to the searchable, paginated source register and violence-type filter. Active filters remain visible on the legend and can be cleared there.

The extract is **partial and preliminary**: 1,500 source records, 1,018 with named/nearby-location precision, grouped into 658 unchanged reference coordinates. Another 482 broader-location records remain searchable but are not drawn at misleading province/country centroids. Exact coordinate matches can carry several source place labels; their shared-point panel explains that these are source references, not claims that all incidents occurred at one exact site. Source IDs, actors, intervals and precision remain attached.

Country research filters plotted reference points against the selected approximate basemap boundary. It does not substitute a UCDP reporting area for a procurement jurisdiction, including for Gaza records coded by UCDP under `Israel`. Dates, source coverage, source revision/checksum, codebook links, licensing and a downloadable snapshot are exposed. The layer neither classifies whole countries as war zones nor changes procurement detection scores. Exporting, aid dependence, loan need, theft and causation cannot be inferred from co-location alone. See [the full source and limitations](GLOBAL_WATCH_DATA.md#conflict-and-organized-violence-context).

## Arms reporting and accountability

The blue legend opens historical UNROCA declarations for 2020–2022, with year, family, category, status and country search. Export/import reports stay separate; comparable signed differences, one-sided mirror coverage and quantity ambiguities remain distinct. Each row links to its original state report. The map shows small blue moving points for declared relationships, never unverified recovery sites. Two GAO audit summaries provide separate historical accountability context; full reports and recovery coordinates remain unverified. No global diversion quantity is inferred. See [source definitions and calculation](GLOBAL_WATCH_DATA.md#arms-declarations-and-accountability).

## Background and sources

Photo backgrounds and background-upload controls are removed. The application clears the previously saved galaxy-image preference on load and uses the plain dark map surface.

Basemap: Natural Earth 4.1.0 / world-atlas 2.0.2. Country metadata: world-countries 5.1.0, with the derived catalog and ODbL license downloadable through the source panel. See [country data provenance](../sunlight-dashboard/src/data/README.md). Country centers are schematic references; reporting areas and map boundaries may differ. Boundaries do not imply endorsement.

## Validation

Verified interface captures: [global material flows](interface/Material-Flows.png) and [Ghana material contributions](interface/Material-Contributions.png).

Conflict layer captures: [red geographic observations](interface/Conflict-Context.png) and [dated source register](interface/Conflict-Source-Register.png).

- Python suite: **2,019 passed, 3 skipped**, Docker tests excluded. The historical 42,835-contract evaluation database remains unavailable.
- Frontend: **30 tests passed**, including source-year separation, 250-country inclusion, published values, missing observations, fallback years, incomplete market slices, material contribution calculations, correct partner-share denominators, source-balanced route drawing, camera alignment, sampled great-circle accuracy, conflict precision filtering, geographic hit tests, reporting-area separation and observation-date freshness.
- Production build passed at `/watch/`.
- Chromium verified real bundled published figures with no mocked procurement data, year switching, pinned source links, all 250 directory rows, country selection with/without source values, direct map selection, continued rotation after dragging, removal of the old image preference, and a 390px viewport without horizontal overflow.
- Chromium additionally verified the real material snapshot, Ghana and DR Congo export values, material filtering, white particle glow/movement during country hold, full snapshot download, native dialog controls, mobile width and system reduced motion. A separate explicit trade fixture checked coexistence of yellow and white layers; actual material and procurement checks used bundled source data.
- Canvas browser checks verified visible white/yellow pixels, front-face clipping, continued country-view motion, responsive and high-DPI buffers, reduced-motion stillness, explicit zoom redraw and runtime motion-preference changes, with no browser errors.
- Conflict browser checks verified steady red pixels, source dates and partial coverage, record search/pagination/type filters, snapshot download, Gaza reference-point selection above country badges, Sudan map context and mobile dialogs/resizing. A five-second benchmark with all 658 reference points and the existing 320 flow routes remained approximately 60 FPS with no observed long tasks.
- Provider trade retrieval remains unavailable in this cloud because outbound policy blocks the source. Published procurement and material values are independently available from their bundled, source-pinned snapshots. The user's Render screenshot confirms that the trade connector can return data there; local provider failure is not evidence of a Render failure.

Arms layer validation: 2022 mirror comparison counts (46 comparable, 31 different), signed Germany-to-Latvia assault-rifle example (2,330 export / 5,753 import / −3,423 reporting difference), source details, year/family/category/status filters, complete snapshot download, audit-summary limits, country research and mobile dialogs were verified in Chromium with no browser errors. The tail-free renderer with 160 additional arms relationships measured 60.2 RAF frames/second, 16.7 ms p95 frame interval and zero long tasks in the same five-second local responsiveness check. This is a local browser result, not a universal frame-rate guarantee.

Arms captures: [global point layers](interface/Arms-Global.png) and [declaration comparison register](interface/Arms-Reporting.png).
