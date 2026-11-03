# Cited organizational identity policy

Active policy: `sunlight.cited-organisations.gb-coh-pad8.v1`.

GB-COH numeric strings of one through eight ASCII digits are padded on the left
to eight digits. Prefix forms of two uppercase letters and six ASCII digits are
kept exactly as published, including OC, RC, FC, SC and NI. No case, whitespace
or prefix repair is performed. Malformed or unsupported identifiers are retained
as unresolved evidence, never silently converted into a match.

Every observation retains the published value, normalised value, policy and
source locator. Matching uses only the normalised value and its authority.
LEIs require the ISO checksum. Unknown authorities do not create identity edges.
IATI reporting references beginning GB-COH are parsed as that authority by the
source adapter, not treated as a name match.

Explicit identifiers co-cited for one organization can join components. Names,
addresses and geographic proximity never do. Unresolved parties remain distinct
nodes. Component membership and IDs are canonical for the complete as-of graph,
independent of observation arrival order. A later cited bridge may change the
component ID. Previous snapshots retain the former membership and ID.

This policy resolves organizational identifiers. It does not verify company
ownership, beneficial owners, an identifier issuer or the truth of a source claim.
