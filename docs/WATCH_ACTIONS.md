# A working first view

The global watch now places **What needs attention** above the globe. The
operator can discover the review workflow without knowing a tool name or reading
a release explanation.

- Explore money flows opens the dated monetary atlas.
- Verify funds & delivery opens the delivery evidence desk.
- Review records opens the complete current queue for the selected country.
- The next evidence check shows the first ranked record, its specific next
  evidence request, an individual measurement where available, and assigned
  follow-up labels. Open evidence & next steps selects that exact dossier.
- Need assignment opens the queue with that filter applied, resetting previous
  queue filters while retaining any existing unsaved follow-up draft.

The world remains mounted when a tool opens. The action surface then contracts
to a small heading so the globe keeps its working space. Desktop and mobile
layouts expose the default actions above the map.

The summary is derived from `/workbench/review-queue`, scoped by country. It
refreshes every 30 seconds while the document is visible, on returning to the
document, and after a recorded change. It displays the assessment time. This
refresh does not turn historical published flows into live payments. No new
financial aggregate or engine threshold was introduced.

An empty ledger explains that arrival checks require source records or a
registered delivery. It provides routes to source intake and delivery checks.
Completed reviews and absent coverage have different explanations. A failed
summary request displays an unavailable state and retry action, never a zero
substituted for missing evidence. Retained results are explicitly identified.

The previous small footer entry was replaced and its unused styles removed.
The home view's ineffective Global workspace button was removed; Close tools
still returns to the full watch from an open desk.

## Verification — 2026-10-20

The 48 frontend tests and the production `/watch/` build passed. The existing
review queue and delivery-assurance browser journeys passed, including exact
dossier handoffs, concurrent edits, draft retention and mobile layout.

`sunlight-dashboard/scripts/smoke-watch-actions.cjs` exercises the actual queue
and record APIs against an isolated local ledger populated by the queue smoke:
visible first-view priorities, filtered assignments, exact dossier navigation,
money/delivery actions, and the same mounted globe. It also injects a failed
summary request and an empty summary to check unavailable/retry and honest
first-use states. Mobile has no horizontal page overflow and retains a usable
globe region. No browser page errors were recorded.

Screenshots show isolated validation fixtures, not actual institutional cases:
[desktop](interface/Watch-Actions.png), [mobile](interface/Watch-Actions-Mobile.png).

These results validate local application behavior. Git publication does not
verify the hosted Render rollout or establish source/issuer authentication.
