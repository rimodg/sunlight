# Master plan foundation work, November 9, 2026

The [owner's master plan](plans/MASTER_PLAN_2026-11-09.txt) is preserved verbatim
with its hash and [implementation notes](plans/README.md). Work remains on
`milestone-1a-rebuild`. Every commit was pushed immediately; main was not pushed.
No new categories, public sources, monetary invariants, model path or payment
control were added. The dependency order in the plan remains in force.

## Completed changes

- README test and detection claims now distinguish constructed reference
  regression from field validation and dated subset tests from a whole-suite
  result. Unsupported claims of international calibration/adoption were removed.
  Five nonexistent HTTP endpoints were removed from the advertised API. The
  published list was checked against the regenerated OpenAPI schema.
- Both reference report generators now qualify synthesized positives,
  presumed-negative comparisons, legacy label fields, settlement-reference
  weights and assumed analyst time. Stored historical reports were re-rendered
  with explicit correction notices and original Git blob references. Every
  numeric leaf was checked unchanged. No scoring, threshold, sampling or
  classification arithmetic changed, and no reference evaluation was rerun.
- `/version` now reports a startup-frozen content identity and revision basis.
  The Dockerfile writes a packaged source/environment manifest without copying
  Git metadata. A declared revision is labeled as declared, not authenticated.
  Without a revision, a real source fingerprint is returned. A mismatching
  packaged source or runtime refuses startup.
- `config/reference-inputs.json` records the expected reference-file identities,
  the historical fixture blob and the missing storage locator. The new
  read-only admission command never downloads, creates or substitutes inputs.
  Matching hashes authorize only proceeding to a run, not claiming it passed.

## Measured verification

A fresh offline clone of source commit
`f5bebf51d19f9c7624ad70d5534a387fe146982f` passed these commands on November 9:

```text
python -m unittest discover -s tests -p 'test_watch_*.py' -v
50 passed
python -m unittest discover -s tests -p 'test_build_identity.py' -v
8 passed
python -m unittest discover -s tests -p 'test_reference_inputs.py' -v
6 passed
python -m unittest discover -s tests -p 'test_evaluation_provenance.py' -v
4 passed
```

Total: 68 targeted tests. The unittest process additionally denied external DNS
and sockets through an audit hook. `SUNLIGHT_OFFLINE=1` was set. These are not a
whole-backend-suite pass, a live-source run, a reference-floor run or a native
Mac service test. The full backend attempt still failed before execution because
pytest is unavailable. No packages were downloaded to bypass that constraint.

An isolated copy of the actual API without `.git` returned HTTP 200 from
`/version`, `state: packaged_files_match` and the supplied full revision with
`git_commit_basis: declared_build_input`. Changing its packaged API source then
refused startup. This was an API packaging simulation, not a Docker image build.
The managed Docker daemon was available but had no cached images; no base image
was pulled and no actual image build is claimed. Remote CI outcomes were not
observed. The exact-lock CI job includes all four targeted test subsets.

All four frozen acceptance-file hashes matched. The reference case fixture's
hash matched its expected digest. The database was unavailable, its durable
storage locator remains null, and neither reference protocol was run. The
owner's reported database size remains attributed, not independently measured.

## Gates still open

1. Register and retrieve the exact database from durable private storage, verify
   it, then reproduce the reference floor on another machine. Admission alone
   does not close this gate.
2. Observe the complete suite/build checks and an actual packaged container run
   in a provisioned environment. Only the targeted tests and no-Git API copy
   above were verified here.
3. Install the watch on the Mac, verify after reboot and validate both public
   endpoint contracts before the unattended population/change acceptance run.
4. Preserve the old hosted state before taking that instance offline or changing
   its tracked branch. No Render control-plane credentials or capabilities were
   configured here, so preservation, shutdown and replacement were not executed.

The Mac's reported default Python is 3.14; the service pin is exactly 3.12.14.
The available terminal tool reported no app terminal attached to this thread.
Neither the failed command nor failed hostname appears in the stored records.
Those details were not guessed, and no interpreter pin was relaxed to evade a
missing native verification.

The next substantive proof remains the unattended real-source change run.
Later invariants, human-layer calculations and payment control remain deferred.
In particular, preserving the master plan does not constitute the separate
explicit, dated decision or institutional delegation required for payment action.

See [build identity](BUILD_IDENTITY.md), [reference inputs](REFERENCE_INPUTS.md)
and the [Mac service guide](MACOS_WATCH_SERVICE.md) for the exact interfaces.
