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
