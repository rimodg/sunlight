# Geographic investigation desk

The default `/watch/` workspace opens on a full-width investigation desk. The record register, globe and evidence inspector share the same selected result. Import opens a drawer rather than displacing the investigation. Single and batch analysis, jurisdiction calibration, capacity allocation, evidence-gate traces, citations, completeness gaps and exact-response packet downloads continue to use the live API.

## Geographic meaning

The globe is context for the currently analyzed input. There is no connected global procurement feed. Counts come only from the current analysis; submitting another analysis replaces the register. Reloading clears the session. Retain downloaded packets for subsequent review.

Markers represent the **first valid supplied delivery point** in `tender.deliveryLocations[].geometry` or `tender.items[].deliveryLocation.geometry`. Geometry must be GeoJSON `Point`, with finite numeric longitude and latitude in their valid ranges. Zero is valid. Other geometries, country names and calibration profiles do not produce markers. Geography does not enter scoring, certify a location or attribute misconduct to a country. Records without supported coordinates remain in the queue and inspector.

The fictional examples carry explicitly labeled fictional delivery coordinates. Edited and uploaded records retain their separate input-origin labels. Map colors describe the basemap and selection, not national integrity or evidence coverage.

The bundled basemap is Natural Earth 4.1.0 at 1:110m, distributed through `world-atlas` 2.0.2 (ISC; underlying Natural Earth data is public domain). Projection uses `d3-geo`; topology conversion uses `topojson-client`. Rendering needs no external tile service, map key or runtime map request. Boundaries do not imply endorsement.

## Interaction and validation

Earth rotates west to east at an accelerated visualization speed of one turn every three minutes. This preserves rotational direction; it is not real-time sidereal rotation. Motion stops when the user focuses, drags or locates a record on the globe. Pause/resume controls stop both rotation and the traveling lights. Reduced-motion preferences start the view paused; a user can explicitly resume. Background tabs do not accumulate a large rotation jump.

Drag or use arrow keys on the focused globe to rotate. Zoom, reset and locate controls have keyboard-accessible buttons. Locate selection is disabled for records without coordinates. Markers select records; the register supports title/identifier search, findings and unlocated filters. The import dialog supports Escape, focus containment and return to its opener. Narrow screens stack the map, register and inspector.

## Procurement relationships and traveling lights

An award supplier with explicit `location.geometry` can be linked to the supplied delivery point. A supplier referenced by ID may instead take its location from the matching `parties[].location.geometry`. These location fields are visualization extensions requiring valid GeoJSON points. Country names alone and unrelated parties never produce links. Cancelled and unsuccessful awards are excluded; duplicate links and identical endpoints are suppressed. No location enters the detection core.

Lines follow great-circle geometry and are clipped to the visible hemisphere. Traveling lights indicate schematic supplier-to-delivery direction, not observed shipments, cash transfers, trade volume or event timing. The first 80 links are displayed for large batches, with selected-record links prioritized and the display limit stated. Fictional examples include a labeled Rotterdam-to-Washington supplier relationship.

The **Illustrate flows** toggle explicitly switches to three fictional cross-continent routes. A persistent notice and mode badge identify the illustration; it does not change records, findings, scores or packet contents. **Show record links** returns to the supplied relationships.

**Background image** selects an exact local JPG, PNG or WebP up to 3 MB. The browser validates that the image decodes and retains it in local storage on that browser; no API upload occurs. **Reset background** restores the default. If storage is unavailable or full, the image applies for the current visit and the interface states that limitation. A dark overlay preserves text contrast and the image is scoped to the globe panel.

The optional shared asset slot accepts `src/assets/galaxy-background.jpg`, `.jpeg`, `.png` or `.webp`, bundled by Vite. The exact pasted image has no accessible original file or URL in the agent workspace; the new local image selector lets the user apply that original immediately. Until a shared asset is supplied, other browsers retain the default background.

Validated against the production build served by the real API:

- `npm test`: five geography/association checks, including invalid coordinates, zero coordinates, sparse inputs, duplicate identifiers, error results, supplier identity matching and excluded awards/links.
- `npm run build -- --base=/watch/`: production build passed.
- Chromium: real single and batch requests, marker selection, duplicate-identifier association, filters, keyboard rotation, packet download, method/readiness navigation, modal Escape and a 390px viewport without horizontal overflow. No browser page errors.
- The packet downloaded through the browser passed `scripts/verify_evidence_packet.py` with local source verification.
- Motion checks in Chromium verified gradual eastward movement of a centered marker, visible light movement, pause/resume freezing both map and lights, reduced-motion initialization, explicit preview labeling, supplied-link counts and mobile width without overflow.
- Background checks verified decoded image application, retention across reload, reset, invalid/oversize rejection, disabled-storage fallback and zero API requests uploading the image. A local test image exercised the workflow; the pasted galaxy preview was not available as a file for the test.

These checks validate this interface against the existing engine; they do not reproduce the unavailable historical reference-database evaluation or establish institutional deployment approval.
