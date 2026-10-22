# SUNLIGHT without internet

SUNLIGHT can run the watch, monetary comparisons, procurement/delivery engines,
document reading, evidence search, reconciliation and follow-up on a local
computer. A browser connects to that computer's local API; internet access is not
required for those calculations or for retained evidence.

An offline computer cannot observe an event that has not reached it. SUNLIGHT
uses existing source, contract, event, transfer, issuer and document references
to reconcile delivered records. Banks, treasuries, receiving offices and field
teams may provide records through an authorized local connection or carried
files. The software preserves their source periods and receipt times. It does
not fill interruptions with invented observations.

## Install the prepared local edition

Docker Engine or Docker Desktop must already be installed. Obtain the offline
bundle while connected, or through your institution's trusted file distribution.
No Docker registry or package-manager download is needed after obtaining it.

1. Extract the installation ZIP into a folder.
2. On macOS/Linux, open a terminal in that folder and run `sh start.sh`.
   On Windows use `powershell -File start.ps1`.
3. Open `http://127.0.0.1:8000/watch/` after the local health check passes.
4. Open **Offline workspace** in the header to inspect the policy, retained
   evidence, source dates and checkpoint actions.

The launcher checks SHA-256 hashes, loads the included image, uses its immutable
image ID with `--pull=never`, creates a dedicated Docker bridge network and publishes
only the loopback browser port. The API starts with `SUNLIGHT_OFFLINE=1`.
The local edition uses a read-only application filesystem and a durable Docker
volume, `sunlight-offline-state`, for registered records and calibration.

The bundle states its CPU architecture. An `linux/amd64` image requires an x86-64
Linux runtime or Docker's compatible emulation, including Docker Desktop's
configured support on Apple Silicon. Install required Docker/emulation support
before disconnecting. The shell launcher is exercised in the build environment;
the supplied PowerShell launcher is not a claim of a Windows host test.

To inspect readiness:

```sh
docker inspect --format '{{.State.Health.Status}}' sunlight-offline
```

To stop and resume without deleting records:

```sh
docker stop sunlight-offline
docker start sunlight-offline
```

Do not delete the state volume. Closing the browser or stopping the container
does not delete that volume. A cloud-hosted website alone cannot keep running
its remote engines when the browser loses access to that server; use this local
edition for that situation.

## What offline policy changes

- Packaged monetary, procurement, material, conflict and arms snapshots remain
  available, with their actual historical dates and coverage.
- Local engines, comparison calculations, document extraction and cited evidence
  retrieval remain available. Remote model synthesis is disabled, even if a
  provider key happens to be configured.
- Trade previews are retained in checked disk caches. A previously fetched
  extract survives restart; its original `fetched_at` is preserved. If none is
  retained for a requested scope, the response is unavailable rather than zero.
- The API blocks non-loopback Python socket/name-resolution attempts. The
  bridge network permits access to the local browser port; it is not an
  operating-system firewall. External refreshes remain disabled by the runtime
  policy. The no-network test also exercises operation with all networking absent.
- The document, case, obligation and action stores remain local. No background
  upload, automatic source refresh, or automatic cross-instance merge runs.
- Deadline-sensitive checks use the local system clock. Verify its time when a
  trusted time service is unavailable. Source observation dates and local
  receipt dates remain separate.

Static source links may point to external publishers. Their retained citations
remain readable; opening those external sites requires a later connection.
FastAPI's optional interactive Swagger page uses external UI assets; the
machine-readable `/openapi.json`, local workspaces and readable briefs do not.

## Bring existing records to a local instance

Use **Records & review** for attributed source submissions, retaining stable
source IDs, event IDs and revisions. Existing duplicate/version rules still
apply. Use **Delivery assurance** to register an obligation and record separately
attributed sender debits, recipient credits, deductions, acceptance and service
evidence. Text-readable PDFs can be retained in **Investigate**.

Your institution can call the same local APIs from an approved integration, or
prepare normalized source files for the existing `scripts/submit_operations.py`
push client. No internet is required when that client and the API are on the
same machine or authorized local network. The standard launcher binds to
localhost; broader network access requires an operator's explicit deployment
configuration and institutional access controls.

## Export a complete evidence checkpoint

In **Offline workspace**, choose **Download full evidence checkpoint**. This
exports the whole deployment, across all country scopes:

- a transactionally consistent SQLite backup including source revisions,
  analyses, review/action history, obligation evidence, saved inquiries and
  uploaded PDF originals;
- empirical calibration JSON sidecars and retained trade-preview cache files;
- a manifest with file sizes, SHA-256 hashes, packaged source/engine file hashes,
  Python/library versions, creation time, scope and interpretation limits.

It excludes environment secrets, access-gate configuration, application
containers, and in-process ephemeral dossier/session caches. Original documents
and source records are copied as provided, including sensitive data they may
contain. Register source records and save
investigations for work that must survive a restart. Calibration/cache sidecars
are copied individually; quiesce writes when all stores must align at exactly
one operational cut-off.

The archive contains a copy of all those records, including original documents.
Handle it as deployment data. It uses the same access gate as the records it
contains. A download does not alter the live deployment.

The checkpoint format accepts at most 300 data files, 256 MiB per file and
512 MiB uncompressed in total. Larger deployments need an operator-managed
backup procedure rather than this portable export.

## Verify and restore without replacing existing records

The checkpoint must be used with its matching engine/source and runtime version. The examples
below run from the extracted installation folder on macOS/Linux. Set the absolute
path to the checkpoint; its filename may have spaces.

```sh
sunlight_checkpoint="/absolute/path/sunlight-evidence-checkpoint.zip"
sunlight_image_id="$(cat image-id.txt)"
docker run --rm --pull=never --network none \
  --mount "type=bind,src=$sunlight_checkpoint,dst=/checkpoint.zip,readonly" \
  "$sunlight_image_id" python -m portable_checkpoint verify /checkpoint.zip
```

Stop the existing local service, then restore into a **new** subdirectory of its
state volume. This retains the original database in its original directory.

```sh
docker stop sunlight-offline
docker run --rm --pull=never --network none \
  --mount type=volume,src=sunlight-offline-state,dst=/app/calibration \
  --mount "type=bind,src=$sunlight_checkpoint,dst=/checkpoint.zip,readonly" \
  "$sunlight_image_id" python -m portable_checkpoint restore /checkpoint.zip \
  --directory /app/calibration/restored-evidence
```

The destination must not exist. The tool verifies entry names, limits,
duplicates, hashes, source-version compatibility, actual restored bytes and
SQLite integrity. It rejects path traversal and never executes archive code or
silently overwrites/merges a ledger. A different engine/source version requires
an explicit `--allow-different-version` maintenance decision; that option does
not establish schema compatibility or an independently validated migration.

After a successful restore, remove only the stopped container, retaining its
state volume, then select the restored directory:

```sh
docker rm sunlight-offline
SUNLIGHT_DATA_SUBDIR=restored-evidence sh start.sh
```

For PowerShell set `$env:SUNLIGHT_DATA_SUBDIR = 'restored-evidence'` before running
`start.ps1`, and use `Get-Content image-id.txt` for the image ID. Adapt the same
Docker mount arguments to your local file path. To return to the original store,
stop/remove the container and run the launcher without the subdirectory setting.

A checkpoint is a portable snapshot, not multi-writer synchronization. Offline
changes do not automatically update the hosted service. Normal source/event
revision checks, transaction uniqueness and optimistic review versions still
apply when records are deliberately submitted to another instance.

## Build a distributable bundle

On a connected build machine with Docker, from the repository root:

```sh
docker build --build-arg SUNLIGHT_BUILD_REVISION="$(git rev-parse HEAD)" \
  -t sunlight-offline:local .
python3 scripts/build_offline_bundle.py --image sunlight-offline:local \
  --output /path/to/new/sunlight-offline-bundle
```

The builder exports the image, adds checksum-verifying launchers and this guide,
and writes a ZIP beside the new bundle directory. It includes no user ledger or
credentials. Keep the package's image ID and source revision through your normal
trusted distribution process; hashes alone are not publisher signatures.

The managed cloud build uses its configured proxy and a BuildKit-mounted CA
bundle for dependency installation, with TLS verification enabled. That session
CA is not copied into the runtime image. Building requires dependencies; running
the prepared edition does not.

## Traceability and its limits

SUNLIGHT retains transaction/issuer references, source and correction versions,
document content hashes, reproducible calculations and local audit chains.
Those mechanisms do not depend on internet availability. They also do not
independently authenticate a bank, certify field delivery, or prevent the owner
of an archive from rewriting both data and its manifest. Authentic institutional
issuer identities and evidence remain necessary for those conclusions.

## Validation of this edition

The local edition was exercised in a Docker container with no network: monetary
analysis, exact sender/recipient reconciliation, delivery acceptance, the
calibrated engine, real PDF extraction, saved cited inquiries, readable reports
and checkpoint verification/restoration passed. Replacing the container retained
the original PDF, saved inquiry and exact reconciliation result in the volume.

A cold browser session blocked every non-local request and completed record
intake, saved research, guide printing and checkpoint download/verification with
zero external requests. Reloads and a mobile viewport passed. The existing
monetary investigation browser journey also passed in offline mode.

Backend validation: **2,129 passed, 3 skipped** (optional Docker-live tests
excluded); frontend checks: **48 passed**. The separate no-network Docker
exercise above tested the actual offline appliance.

Interface captures use fictional validation records:

- [Desktop offline workspace](interface/Offline-Workspace.png)
- [Mobile offline workspace](interface/Offline-Workspace-Mobile.png)

The prepared `linux/amd64` installation was also started using its generated
checksum-checking shell launcher. The local health endpoint, loopback port,
read-only application filesystem and complete cold-browser journey passed
against that image. Application policy blocks external Python requests; Docker's
bridge permits the local browser connection. This is distinct from the separate
`--network none` engine test.

Prepared image: `sha256:264c0b5a749324febe2b3c92402759ac5afc6a5e66d15dc0e107052561adcffb`.
Source revision: `a800f85` (subsequent documentation changes do not change the engine).
Installation ZIP SHA-256: `8724a53847c153cc8a121456c3a5835cbec095c3e8017a6450e39c9d589cd58a`.
