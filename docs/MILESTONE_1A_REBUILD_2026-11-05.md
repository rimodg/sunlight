# Organizational watch and Milestone 1A rebuild, 2026-11-05

Implementation is pushed on `milestone-1a-rebuild`. Milestone acceptance is
still open for the checks listed below. This is not a claim of a live global
watch, an independently reproduced owner run or verified native installation.

The branch starts from origin/main `bd9ebef9c90f32ec097679ee24bc38317ad67fc6`.
Commit `88b9143` was cherry-picked as `c26ecd4`, bringing the frozen acceptance
files without the hosted branch's ancestry. Every rebuild commit was pushed
immediately. No commit was pushed to main.

## What now exists

- Cited, authority-qualified organizational identity. Numeric GB-COH identifiers
  are padded to eight; OC, RC, FC, SC and other valid two-letter prefixes are
  retained. Published and normalized values are retained with locators.
  Components are independent of arrival order. Names do not create joins.
- An append-only operator journal for exact capture bytes, observations, source
  receipts, examinations, findings and open questions. Unresolved parties are
  explicit. Historical observations and examinations are retained.
- Scheduled, bounded capture with cursor resume, endpoint scope checks, source
  backoff and a process lock. Failed reaches are receipts. Known personal fields
  are refused before persistence. Last good observations survive failure.
- Pure as-of re-examination of frozen inputs. The current procurement screen
  runs the existing UK TCA rule family, retaining each citation and input basis.
  Missing inputs are UNASSESSABLE. Favorable signals are separate from risk
  indicators. IATI reporter observations can join the same company identifier.
  Open question identity and age survive record revisions. Packets replay the
  actual rule outputs byte for byte with a matching source and rule-data build.
- A macOS LaunchAgent, pinned CPython 3.12.14 environment installer, retained-data
  uninstaller and native verification command. Identical installation is
  idempotent. A missing or mismatched dependency environment is refused.
- Journal-backed status, subject, history, source-document and packet routes.
  `/watch-engine/ui` is a readable view of those same records. It displays
  overdue states, unknown reach, last good capture, rule basis, locators, hashes
  and recorded build identity. There is no separate UI database or model path.

Current scope is organizational structural screening, not price-comparable,
delivery, recovery or arms analysis. No source is enabled by default. A reviewed
organization-only policy is required. The adapters have not been validated
against a live endpoint in this build environment.

## Measured offline verification

Measured November 5, 2026, from a fresh local clone of source commit
`394f2a712e837b5860246803667c4196bfafab06`:

```text
SUNLIGHT_OFFLINE=1 python3 -m unittest discover -s tests -p 'test_watch_*.py' -v
Ran 50 tests in 1.046s
OK
```

A Python audit hook additionally refused external DNS and socket connections,
independently of the application offline flag. Tests use synthetic sources,
organizations and clocks. launchctl is simulated. The new test count is 50,
not a pass count for the whole repository's backend suite.

```text
python3 -m pytest -q tests
exit 1: No module named pytest

npm run build -- --base=/watch/
exit 127: vite not found
```

The sandbox also lacks requests and networkx, plus the dashboard node_modules.
No dependencies were downloaded to work around the no-network constraint.
Branch CI now runs the existing full suite/build jobs and an additional exact
runtime-lock watch job. Remote CI outcomes were not observed here and are not
reported as passed. The local tests used available sandbox dependencies, not a
fully verified installation of the production runtime lock.

The frozen acceptance files match all four recorded SHA-256 digests. The
historical root reference fixture was restored offline from Git blob
`b0043dca177daffb6bce8c05363efba617ce31d4`, retaining SHA-256
`f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f`.
It is ignored, not added to this branch. The exact reference database is absent;
the old uploaded database files could not be resolved. Neither reference-floor
validator was rerun. No calibration, thresholds, corpus or legacy rule conditions
were changed. Existing constructed-reference metrics are not field accuracy.

Chromium inspection used an isolated synthetic ledger through the actual
read-only router. Desktop and mobile source links worked. The 390-pixel mobile
viewport had a 390-pixel document width, zero page errors and zero external page
requests. Frozen source retrieval returned HTTP 200 with its SHA-256 header.
This proves that interface path for the synthetic journal, not the deployment.

Source fingerprint of the measured code and rule data:
`3dd564e67cdb5c2a5e208d7b42e632fefac50dab2c6ecea39a7c41c187139ad7`.
Runtime lock SHA-256:
`2b7343dce9882b86f1da44576cde46863ebaa1114f44e1818e533b406662827b`.

## Exact remaining acceptance gates

1. Observe a passing full backend suite and dashboard build in a provisioned
   environment. The local attempts above did not execute those suites.
2. Supply the original reference database to re-read both reference protocols.
   Do not reconstruct it, substitute a small corpus or reuse a previous result.
3. On a Mac with network access, install from a fresh clone with the reviewed
   policy and exact interpreter. Verify a real running process, then reboot and
   log in. Save the `--after-reboot` receipt. Verification requires the running
   launchd PID to match the journal run, the installed build and a recent
   completed run after boot. This is deliberately not claimed from simulation.
4. Validate the public endpoint contracts and perform the unattended real-source
   acceptance run. The owner-supplied 20-organization intersection remains frozen
   evidence from the owner's machine, not a result produced by this build.

The first three gates apply to the requested installation closeout. The fourth
is the population watch's public-source acceptance, which has not been replaced
by the synthetic integration test. All captured bodies, journals, logs and
packets remain operator-local and outside Git.

## Owner commands and supporting documentation

Use [the Mac installation and verification guide](MACOS_WATCH_SERVICE.md) for
one-command install, post-reboot verification and retained-data uninstall.
See [the engine contract](WATCH_ENGINE.md) and
[the active normalization rule](WATCH_NORMALISATION.md). The current evidence
workspace links to the journal UI. Set the existing API's
`SUNLIGHT_WATCH_DATA_DIR` to the installed data directory before opening that UI.
The installer does not deploy an API server or modify Render.
