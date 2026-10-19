# A persistent world, with tools around it

The globe is now the permanent working surface at `/watch/`, including direct
links to delivery, research and records. Opening a tool docks it beside the
world instead of hiding the map. Camera, connection selection and tool drafts
remain mounted. On narrow screens, the globe occupies the upper section while
the active tool scrolls independently below it.

Review the [global workbench](interface/World-Workbench.png),
[selected flow](interface/World-Flow-Tracking.png), or
[delivery dock](interface/Delivery-Assurance.png).

## Follow a relationship

1. Open **Flow tracking** in the tool rail, or **Explore connections** on the map.
2. Search by origin, destination, product or material; optionally select a layer.
   The register searches all loaded records in the current scope, beyond the
   bounded subset drawn on the map.
3. Choose **Trace on globe**. The camera eases to the relationship while retaining
   the globe's curvature. A filled origin and outlined destination have explicit
   FROM/TO labels. A continuous selected path and small direction marks establish
   the movement; other connections fade to preserve context.
4. Inspect the source period and measure in the dock. Expand **Source evidence &
   interpretation** for references and limitations, create a readable brief, or
   open a scoped investigation without losing the selected connection.
5. **Clear trace** restores the preceding camera. **Global view** clears the
   country/connection focus. Country research remains available through search
   and the complete country directory; explicit country research can zoom closer.

Hovering over a corridor highlights its direction and names the endpoints.
Country reference points remain available across the catalog; the previous
clusters of overlapping contract-count balloons no longer cover the geography.
Published figures remain in the totals, country directory and source controls.

Connections with matching geographic endpoints, layer and source period are
grouped into drawn corridors. Their individual records remain separate members,
with a source selector when several drawn records share a corridor. Different
products, import/export bases, years, opposite directions and arms categories do
not become a combined financial or quantity measurement. The full register
retains source records even when the drawing budget excludes their geometry.

## Delivery and investigation around the world

**Delivery assurance** retains its obligation chain, guided intake, exact
comparisons, source corrections, calibrated checks, responsible follow-ups and
printable reports. Its obligation finder is a compact disclosure in the dock.
**Locate on watch** focuses the geography while leaving the obligation open.

**Investigate** retains saved inquiries, PDFs, source selection, scoped facts and
optional model assistance. Saved inquiries are in a compact library disclosure.
Selecting a connection or obligation carries its original evidence scope into
the inquiry; the world remains visible while results are reviewed.

**Records & review** retains the operations ledger and its guided source forms.
Closing the dock restores the wider globe without discarding an opened desk.
Document/source dialogs and intake forms remain temporary dialogs when needed.

## Rendering and evidence meaning

Geography, corridors, country references, conflict points and direction marks
now share one Canvas 2D camera and animation loop. Automatic rotation no longer
updates React state or regenerates SVG geography strings. The SVG remains the
accessible interaction surface; country search and the directory expose the
country catalog. Pointer picking uses the current canvas camera and actual SVG
screen transform, with cached route vectors. Eased focus follows the shorter
longitude direction, including across the dateline and after manual rotations.

The renderer respects reduced-motion preference and hidden-document state.
Geography and selected-source quantities do not change because an arrow moves.
The visual traversal interval varies with angular span for legibility; it is not
a shipment duration, payment arrival estimate, economic rate or value encoding.
Line widths are visual emphasis, not additive economic magnitudes.

This pass adds no external feed. The dated public snapshots, partial Comtrade
preview and registered institutional evidence keep their existing coverage and
authentication limits. A corridor is a reported relationship between reference
locations, not a tracked vehicle, bank transfer or inferred transport route.

## Verification

- 46 frontend tests passed, including source-preserving corridor grouping,
  distinct import/export identities, dateline camera continuity, visual-time
  helpers, great-circle projection and route picking.
- Production `/watch/` build passed; the existing bundle-size advisory remains.
- `scripts/smoke-world-workbench.cjs` exercised persistent canvas identity across
  tracking, research, delivery and records; a traced source and printable brief;
  a saved scoped inquiry; country search; the mobile split layout; and reduced
  motion. It observed zero SVG subtree mutations during automatic rotation.
- A three-second local Chromium sample at 1680×1050 measured about 60 frames/s
  with approximately 17 ms p95 frame intervals. This is a local observation, not a universal
  hardware, source-load or network guarantee.
- The retained delivery-assurance browser regression passed in the dock,
  including exact reconciliation, actual calibrated analysis, source corrections,
  concurrent review drafts, retained completion evidence, PDFs and reloads.

Both browser scripts require an isolated local API and environment-supplied
Playwright/Chromium, using the variables described in the delivery-assurance
validation record. They refuse remote hosts. Backend calculations and data feeds
were not changed in this pass.
