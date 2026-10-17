# Geographic investigation desk

The default `/watch/` workspace opens on a full-width investigation desk. The record register, globe and evidence inspector share the same selected result. Import opens a drawer rather than displacing the investigation. Single and batch analysis, jurisdiction calibration, capacity allocation, evidence-gate traces, citations, completeness gaps and exact-response packet downloads continue to use the live API.

## Geographic meaning

The globe is context for the currently analyzed input. There is no connected global procurement feed. Counts come only from the current analysis; submitting another analysis replaces the register. Reloading clears the session. Retain downloaded packets for subsequent review.

Markers represent the **first valid supplied delivery point** in `tender.deliveryLocations[].geometry` or `tender.items[].deliveryLocation.geometry`. Geometry must be GeoJSON `Point`, with finite numeric longitude and latitude in their valid ranges. Zero is valid. Other geometries, country names and calibration profiles do not produce markers. Geography does not enter scoring, certify a location or attribute misconduct to a country. Records without supported coordinates remain in the queue and inspector.

The fictional examples carry explicitly labeled fictional delivery coordinates. Edited and uploaded records retain their separate input-origin labels. Map colors describe the basemap and selection, not national integrity or evidence coverage.

The bundled basemap is Natural Earth 4.1.0 at 1:110m, distributed through `world-atlas` 2.0.2 (ISC; underlying Natural Earth data is public domain). Projection uses `d3-geo`; topology conversion uses `topojson-client`. Rendering needs no external tile service, map key or runtime map request. Boundaries do not imply endorsement.

## Interaction and validation

Drag or use arrow keys on the focused globe to rotate. Zoom, reset and locate controls have keyboard-accessible buttons. Locate selection is disabled for records without coordinates. Markers select records; the register supports title/identifier search, findings and unlocated filters. The import dialog supports Escape, focus containment and return to its opener. Narrow screens stack the map, register and inspector. Motion is user-controlled; reduced-motion preferences disable transitions.

Validated against the production build served by the real API:

- `npm test`: three geography/association checks, including invalid coordinates, zero coordinates, sparse inputs, duplicate identifiers and error results.
- `npm run build -- --base=/watch/`: production build passed.
- Chromium: real single and batch requests, marker selection, duplicate-identifier association, filters, keyboard rotation, packet download, method/readiness navigation, modal Escape and a 390px viewport without horizontal overflow. No browser page errors.
- The packet downloaded through the browser passed `scripts/verify_evidence_packet.py` with local source verification.

These checks validate this interface against the existing engine; they do not reproduce the unavailable historical reference-database evaluation or establish institutional deployment approval.
