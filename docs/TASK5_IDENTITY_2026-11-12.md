# Task 5: cited organizational identity

Read the completed October projection journal, identifier normalizer, subject
resolver, packet replay and actual d-portal query responses first. Count supplier
registry coverage independently of buyer identifiers, then join one published
registry identifier across retained procurement and live aid observations.

Added `scripts/report_watch_population.py` and `scripts/prove_watch_identity.py`.
The report never counts a buyer registry identifier as supplier coverage and
never promotes a GB-CFS internal identifier into a registry identifier. The proof
uses the existing explicit GB-COH zero-padding policy and retains each citation.
Names are neither retained nor compared.

## Observed population

The completed October traversal contains 2,799 admitted release versions and
2,845 award rows, with zero refusals. Of those award rows, 1,172 (41.20%) have
at least one supplier registry identifier supported by the normalizer. That is
potential join coverage, not proof that every identifier matches another source.
No award rows lacked an award identifier or supplier reference.

| Observed identifier scheme | Occurrences |
|---|---:|
| GB-CFS | 3,500 |
| GB-CHC | 7 |
| GB-COH | 1,196 |
| GB-GOR | 86 |
| GB-LAE | 158 |
| GB-SRS | 966 |

Scheme occurrences include buyers and explicit internal GB-CFS prefixes;
award coverage counts only supplier registry identifiers. These denominators
are different. The remaining 58.80% of award rows are not resolved by the
supported supplier registry policy; matching on names is not a fallback.
The API is mutable, so traversal completion is not a publisher snapshot guarantee.

## Cross-source proof

On November 12, the live d-portal request returned nine activities whose
published reporting reference is `GB-COH-1869600`. Contracts Finder publishes
`01869600` under `GB-COH` at `/releases/14/parties/1/identifier`; the aid reference
is cited at `/rows/0/reporting_ref` and the corresponding eight later rows.
The declared padding policy normalizes both to `01869600`.

One resolved subject has categories `aid` and `procurement` and ten cited
observations. Its identifier is
`2f4b248447efd39b2bdf3fa043a92cbf25a2e0d1a41b7f3481be6c7dcc85cc2c`.
Canonical packet replay matched the original examination. This proves shared
published organizational identity, not ownership, a money flow or a labor claim.

The discovery query enumerated 170 GB-COH reporting references across two
pages. Discovery alone was not treated as activity evidence; the proof fetched
actual activities using `select=aid,reporting_ref` and the exact reporting_ref.

Evidence under the chat workspace: `outputs/task5/october-population.json`,
`outputs/task5/identity-proof/proof.json`, `packet.json`, and the proof journal.
The original source responses were not retained. Evidence digests:
- `task5/october-population.json`: `8c8238d388a120e090aef518e267931f4e4ba421a4bb51bf583c44a65a3ceb63`
- `task5/identity-proof/proof.json`: `aece7bcfd44f6c4a51060150aa1f75fa79f9d238ad0b8f44062abab38d9dbd92`
- `task5/identity-proof/packet.json`: `6496c52b6c7cc9844578da0bc38af530dafb35f4d845a9b18c91ab14d425ecb9`

Verification: the two population tests cover supplier-versus-buyer attribution
and unknown denominators. The complete backend suite measured 2,078 passed,
13 skipped, 0 failed and 17 passing subtests in 18.21s on November 10,
America/New_York. The identity helper subsequently executed its live proof and
replay assertion on November 12. Docker, exact reference database and the
non-Mac-only test remain the same documented skip reasons.


## Supplier-only recount, November 12

The earlier scheme table includes buyers. The owner requested a supplier-only
count, now computed by `scripts/report_watch_population.py` from the same frozen
October journal. The denominator is **3,121 supplier entries across 2,845 award
rows**, not unique companies. Supplier references link only to a unique party
with the exact same local identifier; buyer-only identifiers never count.

| Supplier-entry classification | Count |
|---|---:|
| Publishes GB-COH | 1,203 |
| GB-COH accepted by the current identifier rules | 1,191 |
| Only GB-CFS | 1,911 |
| Other nonjoinable identifiers | 19 |
| No supplied scheme identifier | 0 |
| Nothing joinable under the current policy, including only-GB-CFS | 1,930 |

The 19 other nonjoinable entries consist of seven GB-CHC entries and 12 GB-COH
entries that fail the current normalizer. No LEI or other supported registry
join was found among suppliers. This is a limitation of the supported policy,
not a claim that charity identifiers could never be joined by another adapter.
The supplier-only scheme counts are GB-COH 1,203, GB-CFS 1,911 and GB-CHC 7.
There were no ambiguous local-party references in this population.

The valid GB-COH occurrences contain **724 distinct normalized identifiers**.
Only-GB-CFS occurrences contain **1,374 distinct published internal identifier
values**. These values must not be added together and called unique companies:
there is no verified mapping between internal aliases and registry identities.
Only-GB-CFS is a subset of nothing-joinable, not an additional disjoint group.

Evidence: `outputs/task7/october-suppliers.json`, retained outside Git. Its
journal head is the same completed October traversal recorded above.
The supplier count tests cover buyer exclusion, repeated appearances,
normalization of a repeated registry ID, unsupported schemes and missing IDs.

## Recorded coverage finding

These counts are recorded as [WATCH-001](FINDINGS.md): usable registry
identifiers permit potential follow-up beyond the portal for only 38.2% of
supplier appearances in the captured October window. The finding records the
capture and measurement dates, the 61.8% coverage gap, and why portal-local
GB-CFS references cannot substitute for external registry joins.
