# Install the organizational watch on a Mac

The service is a per-user LaunchAgent. It starts at login, including login after
a reboot, and restarts after failure. It is not a daemon that runs before login.
Native installation and running-process verification passed on November 12
after the owner approved Python's Documents-folder access prompt.
See the [observed native gate](TASK6_NATIVE_2026-11-12.md). Reboot persistence
remains unverified; use the checks below on the actual service host.

## One command from the fresh clone

Check out the tested `watch-live-sources` revision. Have CPython **3.12.14** available and supply its
absolute executable path. The installer refuses any other version. It does not
install an interpreter or fall back to a system Python.

```bash
./scripts/install-watch --python /absolute/path/to/python3.12 --data-dir /absolute/path/to/SUNLIGHT-operator-data --policy /absolute/path/to/reviewed-source-policy.json
```

The one command creates an external virtual environment using that interpreter,
installs every exact `requirements.lock` distribution with no dependency
resolution or source-build fallback, verifies the environment, writes the agent
and reports whether launchd loaded it. Network access is needed on the Mac for
package wheels and enabled public sources. The live probes and locked-package installation were executed on the Mac.

If the environment cannot be created or verified, the service is not loaded.
Partial state is retained for diagnosis. No fallback environment is used. The
error reports paths created so far. An existing mismatched environment is
refused rather than overwritten or deleted.

## Review and configure sources

`config/watch-sources.example.json` has an empty source list. Choosing that file
explicitly installs an idle watch. It is not evidence of live capture or a
population run. The owner acceptance files are never used as a feed.

A source policy has this shape. URLs below are synthetic schema examples:

```json
{
  "schema": "sunlight.watch-source-policy.v1",
  "sources": [
    {
      "id": "reviewed-procurement-source",
      "adapter": "contracts_finder",
      "url": "https://example.invalid/ocds?limit=100",
      "interval_seconds": 3600,
      "organisation_only_reviewed": true
    },
    {
      "id": "reviewed-aid-source",
      "adapter": "iati_dportal",
      "url": "https://example.invalid/q?reporting_ref_like=GB-COH-%25",
      "interval_seconds": 3600,
      "page_limit": 100,
      "organisation_only_reviewed": true
    }
  ]
}
```

Replace endpoints only after reviewing scope, access, organizational fields and
paging. Both adapters have passed one-page live probes; population acceptance is separate.
Only the adapter's declared organizational projection reaches admission. Contact
fields are discarded in memory; personal-shaped content inside an allowed field
refuses that record before persistence. Do not switch off protection to make a
source pass. Review the projection exclusions and per-record coverage gaps.
The review flag is an operator assertion, not an automated privacy certificate.
See [the engine's scope and refusal rules](WATCH_ENGINE.md).

## Paths and cadence

All paths derive from command configuration or the current user's OS home.
There are no hardcoded user home paths.

| Item | Path |
| --- | --- |
| Virtual environment | `DATA/runtime`, configurable with `--environment` |
| Configuration | `DATA/service.json` |
| Reviewed policy copy | `DATA/source-policy.json` |
| Journal, projections and original-response digests | `DATA/journal.sqlite3` |
| Scheduler mutual-exclusion lock | `DATA/journal.lock` |
| Standard output and error | `DATA/logs/stdout.log`, `DATA/logs/stderr.log` |
| Installation/build receipt | `DATA/install-receipt.json` |
| Agent | Current user's `Library/LaunchAgents/org.sunlight.watch.plist` |

`DATA` must be outside the repository. The default is the current user's
`Library/Application Support/SUNLIGHT`. Agent directory, label, data path,
environment and interval can be overridden with the install options shown by
`./scripts/install-watch --help`.

The default scheduler poll is 60 seconds. A poll reads at most one due page from
each source. A cursor resumes next poll. After a completed page cycle the
source's own interval applies. HTTP 429 honors integer or HTTP-date Retry-After
and never retries earlier than that deadline;
other failures use backoff and keep the previous cursor and last good capture.
A page cycle represents the reviewed endpoint's coverage, not all global flows.

Identical repeated installation changes no file bytes or mtimes and does not
reload a loaded unchanged agent. Changed source, policy or configuration causes
an explicit retained-data reload. A foreign agent with the same label is
refused. Reinstall after code changes: the runtime verifies the source and lock
before starting and refuses source drift during the loop.

If macOS asks for Documents-folder access for the selected Python, the owner
must handle that OS prompt. A loaded agent can be paused before creating its
journal. Do not count that state as successful startup or unattended runtime.

## Ledger interface and health

The service installs the watch loop, not a second web server. To use the existing
API and its read-only ledger interface, point that API process at the same data:

```bash
export SUNLIGHT_WATCH_DATA_DIR=/absolute/path/to/SUNLIGHT-operator-data
```

Run the existing API with its normal locked environment and local access
controls. Open `/watch-engine/ui` on that API. The current evidence workspace
also links there. No model or writable intake route is added by this work.
The existing hosted Render page does not automatically read a Mac's journal.
Do not expose the journal API publicly without the institution's access controls.

The interface queries the journal for scheduler receipts, source last reach,
outcome, unknown silence, last good capture, overdue state, startup build,
subjects, findings and open questions. Source links return the retained organizational projection with its SHA-256
and the original-response digest; every reading retains a source locator and citation.
Packets are downloads from recorded examinations. No separate UI data store is
populated. Health receipts do not independently prove current process liveness.

## Verify, reboot and close the native gate

First check the running service:

```bash
./scripts/watch-service verify --python /absolute/path/to/python3.12 --data-dir /absolute/path/to/SUNLIGHT-operator-data
```

Reboot, log in, allow a poll cycle to complete, then save a fresh receipt:

```bash
./scripts/watch-service verify --python /absolute/path/to/python3.12 --data-dir /absolute/path/to/SUNLIGHT-operator-data --after-reboot > /absolute/path/to/SUNLIGHT-operator-data/reboot-verification.json
```

Verification refuses unless launchd reports a running PID, the exact environment
and source policy match, a recent completed journal run matches the installed
build and that same PID, the run occurred after the current boot, and that boot
is later than install. A manual run from another process cannot validate a
different worker merely because it wrote a recent receipt.
Reinstalling or changing configuration resets this reboot requirement. The
JSON remains on stdout; the shell's final exit receipt is on stderr. This proves
service persistence only, not completeness of capture from enabled sources.

## Remove the service, preserve everything observed

```bash
./scripts/uninstall-watch --python /absolute/path/to/python3.12 --data-dir /absolute/path/to/SUNLIGHT-operator-data
```

This unloads the owned agent and removes only its plist. The whole operator data
directory, environment, policy, logs, receipts, captures and journal remain.
Repeated uninstall is harmless. Nothing observed is deleted.
