# Observed findings

## WATCH-001: portal identifiers limit external supplier coverage

**Recorded:** November 12, 2026. **Status:** observed coverage limitation in the
captured population, not a field-accuracy estimate.

**Population and dates:** Contracts Finder's October 2026 award window, queried
with `publishedFrom=2026-10-01` and `publishedTo=2026-11-01`. The 28-page traversal
completed November 10, 2026 at 22:52:23 Eastern (November 11 at 03:52:23 UTC).
The supplier-only recount was measured November 12, 2026. It covers 2,799
admitted release versions and 2,845 award rows; no releases were refused.

| Finding basis | Count |
|---|---:|
| Supplier appearances | 3,121 |
| Appearances publishing GB-COH | 1,203 |
| Appearances with valid GB-COH under the current normalizer | 1,191 |
| Appearances carrying only GB-CFS | 1,911 |
| Appearances with nothing joinable under the current policy | 1,930 |
| Distinct normalized company identifiers, GB-COH | 724 |

The 724 is the company count at the level of cited normalized registry
identifiers. It is not an independent registry verification of 724 companies,
a beneficial-ownership count or proof of 724 cross-source matches. Appearances
repeat across awards. Only-GB-CFS is included in nothing-joinable; those counts
must not be added together. The other 19 nonjoinable appearances comprise seven
GB-CHC identifiers unsupported by the current join policy and 12 GB-COH
identifiers that fail its normalizer.

**What this means:** the watch has usable company registry identifiers for
roughly a third of supplier appearances: **1,191 / 3,121 = 38.2%**. This is its
potential identifier-based follow-up coverage beyond the portal in this month.
The remaining **61.8%** cannot be followed beyond the portal through the current
supported registry joins. Capturing the whole queried population therefore does
not mean resolving its suppliers across systems. Internal GB-CFS identifiers
support portal-local references but do not establish an external company join.

An identifier makes an external lookup possible; the external source must still
publish a matching cited identifier. The separate live proof establishes one
actual cross-source organization match, not matches for every usable identifier.
This finding does not imply that unsupported schemes are intrinsically
unjoinable or that another month has the same distribution.

**Operational consequence:** disclose this coverage gap alongside findings and
keep unresolved supplier references visible. Increasing captured volume alone
will not fix it. Extending coverage requires published registry identifiers or
a separately reviewed identifier mapping; names are not a substitute for a
cited join, and missing identity is not evidence of wrongdoing.

**Evidence:** [supplier aggregate](../reports/reference-2026-11-12/october-supplier-summary.json),
[method and identity proof](TASK5_IDENTITY_2026-11-12.md), and the completed
October journal with head
`1b9550e83d03391fc1d7024e38ab345286c7d3522dbf84ba29de3e4283bbfdac`.
The source is mutable; this completed traversal is not a publisher-guaranteed
consistent snapshot.
