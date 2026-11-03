# Milestone 1A rebuild status, 2026-11-03

Status: acceptance evidence frozen and pushed; service rebuild blocked by the
missing watch-engine baseline. This is not a completed Milestone 1A.

## Preserved on origin

Branch: `milestone-1a`. Its baseline is origin's `codex/sunlight-hosted-access`
commit `87d6bae4bee467216350ea17c16b0a6680921a52`, titled
`Record successful packaged offline installation verification`.

First rebuild commit: `88b9143084e667a3df6a7032b4272207bea7a475`.
It contains the four owner-supplied acceptance files, manifest and README under
`acceptance/2026-10-27/`. The four digests match the prior supplied-file receipt,
and the three JSON digests also match the supplied path-bearing `hashes.txt`.
Original JSON bytes and redaction were retained. No acceptance counts were
recomputed. The README's offline verification command passes:

```text
Verified: all four manifest digests and all three supplied JSON hashes
```

All commits made for this rebuild are pushed immediately to this branch.
No push to main is part of this work.

## Exact blocker

The rebuild order assumes the pre-existing watch engine, capture/resume loop,
identifier resolver, journal and read-only watch status route are intact.
They are absent from the available checkout and all branch tips fetched from
origin on 2026-11-03. In particular:

- `code/watch_engine.py`
- `code/watch_capture.py`
- `code/watch_identity.py`
- `code/watch_journal.py`

`git log --all -- <path>` has no history for these four paths in the fetched
repository. The available hosted branch has `watch_arms.py`, `watch_conflicts.py`,
`watch_materials.py`, `watch_money.py`, `watch_procurement.py` and `watch_trade.py`,
which are source-layer modules, not the described continuous subject watch.
Searching Python source also finds no `WatchEngine`, `CaptureScheduler`,
`WatchJournal` or `/watch-engine/status` interface.

The prior starting-point commit recorded in this conversation,
`ab8af73c60bb948493222d1aae6d9fcaf9b2042a`, is not a locally available Git object.
The previously lost service commit is not being recreated from its reported hash.

Tasks 1 through 4 cannot safely wrap, extend or test a missing implementation.
No replacement engine, invented command, fabricated journal API or synthetic
acceptance reproduction has been substituted. Supply a source archive or a
reachable Git ref containing that baseline before continuing these tasks.

## Verification limits

Only the acceptance admission and documented offline hash command have been run
for this rebuild. A new backend-suite pass count has not been measured. The prior
2,487 result belongs to the lost build and is not a result for this checkout.

No source requests were made. Network use was limited to the explicitly required
Git fetch/push transfers. No operational captures or journal database were added.
Native Mac installation and post-reboot service verification remain open, as the
rebuild order requires; neither can be proved from this Linux environment.
