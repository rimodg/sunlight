# Global watch and country research

`/watch/` opens on a full-width globe. The record register and evidence inspector open as overlays so they do not permanently narrow the map. Import continues to use the live single/batch analysis API, jurisdiction calibration, capacity allocation, rule citations, input gaps and exact-response verification packets.

## Motion and research

The global globe rotates west to east, one accelerated turn every three minutes. Dragging, keyboard rotation, record inspection and source panels do not stop global rotation. Country search accepts common/official names, translated aliases and ISO codes; ambiguous names require choosing a result. Selecting a country centers, highlights and zooms its boundary and holds rotation until **Return to global watch** or **Global view**. Small countries absent from the 1:110m basemap have a labeled reference point and an explicit resolution notice.

System reduced-motion preferences remain respected. There are no pause or illustrative-flow controls. Annual trade lights continue during country research unless reduced motion is active. Neither lighting speed nor particle counts represent shipment frequency or monetary volume.

## Documented procurement and completion evidence

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

**Background image** selects a local JPG, PNG or WebP up to 3 MB. It is decoded and saved in that browser's local storage; no image-upload API request occurs. **Reset background** restores the default. Storage restrictions are disclosed and permit temporary application for the visit. The shared asset slot remains `src/assets/galaxy-background.{jpg,jpeg,png,webp}` if an original file becomes available for bundling.

Basemap: Natural Earth 4.1.0 / world-atlas 2.0.2. Country metadata: world-countries 5.1.0, with the derived catalog and ODbL license downloadable through the source panel. See [country data provenance](../sunlight-dashboard/src/data/README.md). Country centers are schematic references; reporting areas and map boundaries may differ. Boundaries do not imply endorsement.

## Validation

- Python suite: **2,003 passed, 3 skipped**, Docker tests excluded. The historical 42,835-contract evaluation database remains unavailable.
- Frontend: **13 tests passed** covering coordinate/identity association, release-versus-batch parsing, currencies/stages, duplicate exclusions, document URL safety, country scope, source queries and milestone declarations.
- Production Vite build passed at `/watch/`.
- Chromium exercised real single/batch API submission and packet downloads, category/document inspection, country lookup/zoom/rotation hold, continued motion after dragging, continuing light animation, source tables and a 390px viewport without horizontal overflow.
- Downloaded three-record packet passed offline content and local source-manifest verification.
- Bilateral trade and configured annual-counter UI states were exercised with explicitly fictional test fixtures. These are **not live provider verification**. The actual source request in this cloud was denied by outbound network policy and produced the expected unavailable state. Render-side provider retrieval is unverified until deployment.
