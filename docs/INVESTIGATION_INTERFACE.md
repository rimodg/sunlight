# Global watch and country research

`/watch/` opens on a full-width globe. The record register and evidence inspector open as overlays so they do not permanently narrow the map. Import continues to use the live single/batch analysis API, jurisdiction calibration, capacity allocation, rule citations, input gaps and exact-response verification packets.

## Motion and research

The global globe rotates west to east, one accelerated turn every three minutes. Dragging, keyboard rotation, record inspection and source panels do not stop global rotation. All 250 catalog countries and territories have selectable reference markers and a searchable directory, including places without source data. Country boundaries also support direct map selection. Country search accepts common/official names, translated aliases and ISO codes; ambiguous names require choosing a result. Selecting a country centers, highlights and zooms its boundary and holds rotation until **Return to global watch** or **Global view**. Small countries absent from the 1:110m basemap have a labeled reference point and an explicit resolution notice.

System reduced-motion preferences remain respected. There are no pause or illustrative-flow controls. Annual trade lights continue during country research unless reduced motion is active. Neither lighting speed nor particle counts represent shipment frequency or monetary volume.

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

Yellow paths use the separately sourced, dated UN Comtrade context described in [GLOBAL_WATCH_DATA.md](GLOBAL_WATCH_DATA.md). Paths connect country reference points along great circles. The globe displays up to 80 trade links, ranked by annual export value; country research filters links to those involving the selected country. Source tables retain the available links, source query, period, values and source reported flag. Missing trade data produces an unavailable state, with no fictional substitute routes.

Supplied procurement relationships appear as distinct dashed paths. An award supplier with a valid `location.geometry` Point can be linked to the first valid delivery point in `tender.deliveryLocations[]` or `tender.items[].deliveryLocation`. A supplier ID can instead resolve its origin through the matching `parties[].location`. These location fields are visualization extensions. Cancelled/unsuccessful awards, invalid coordinates, duplicate links and identical endpoints do not produce links. Up to 20 selected-record links and 20 other supplied links are drawn; the map states drawn/available counts. Relationships are not shipment or payment tracking. Geography never enters the detection score.

## Background and sources

Photo backgrounds and background-upload controls are removed. The application clears the previously saved galaxy-image preference on load and uses the plain dark map surface.

Basemap: Natural Earth 4.1.0 / world-atlas 2.0.2. Country metadata: world-countries 5.1.0, with the derived catalog and ODbL license downloadable through the source panel. See [country data provenance](../sunlight-dashboard/src/data/README.md). Country centers are schematic references; reporting areas and map boundaries may differ. Boundaries do not imply endorsement.

## Validation

- Python suite: **2,008 passed, 3 skipped**, Docker tests excluded. The historical 42,835-contract evaluation database remains unavailable.
- Frontend: **16 tests passed**, including source-year separation, 250-country inclusion, published values, missing observations, fallback years and incomplete market slices.
- Production build passed at `/watch/`.
- Chromium verified real bundled published figures with no mocked procurement data, year switching, pinned source links, all 250 directory rows, country selection with/without source values, direct map selection, continued rotation after dragging, removal of the old image preference, and a 390px viewport without horizontal overflow.
- Provider trade retrieval remains unavailable in this cloud because outbound policy blocks the source. Published procurement values are independently available from the bundled, source-pinned snapshot.
