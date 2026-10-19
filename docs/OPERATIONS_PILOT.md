# Operations desk: a source-connected investigation pilot

SUNLIGHT opens on **Global watch** at `/watch/`. Open **Records & review**
(`/watch/#operations`) to use the operational ledger. Country scope carries from the watch. The operations workflow is independent of the
map animation: a source supplies versioned expected and observed measurements,
the server validates and compares them, runs the applicable existing engines,
and retains an investigation history.

This is an operational **push-ingestion pilot**, not a connected UN, World Bank,
customs or live global shipment feed. No external polling is active in this
workflow. The existing `live_monitor.py` remains a separate tool; its presets do
not establish current source availability or a delivery observation. UNDP Quantum
and Compass adapters remain placeholders pending validated institutional schemas.

## Use the application

1. Register a source with a stable source ID, declared publisher reference,
   explicitly selected jurisdiction profile and expected publication interval.
   Registration is attribution, not publisher authentication.
2. Open **Submit source records**. Use the guided form for a physical-delivery or payment snapshot: identifiers, source revision, countries, units/currency, period, baseline, due time, optional observation and source documents. Blank observations remain unknown and 0 is explicit. Submission records publication time. Advanced integrations can paste/upload a JSON batch. The synthetic
   example is an editable, clearly labeled demonstration; it is not seeded into
   the ledger or sent until you explicitly submit it.
3. Submit the batch. The server validates it, runs the available engines and
   saves the source snapshots, engine responses and content hashes in SQLite.
4. Search and filter by source, contract/title/category/country code, comparison
   state, workflow status or followed cases. Open a case to inspect expected and
   observed measurements, covered periods, due time, publication/observation/
   receipt clocks, source references and rule-level engine evidence.
5. Assign an analyst label, follow a case, add a review note and save its workflow
   status. New current source evidence reopens the case while preserving following
   and ownership. Every review change remains in the case history.
6. Open the readable case brief and use **Print / save as PDF** for a report with measurements, calculation, evidence, findings, revisions and review notes. An advanced JSON case packet retains declared source configuration, all retained source revisions, stored engine
   responses, audit entries and local content-integrity verification.

The visible desk refreshes every 15 seconds and on returning to a visible tab.
The API recomputes date-sensitive comparison states on read; engines run on
accepted source revisions. No counter advances without source evidence. A failed
refresh retains the last view with an error and its last successful timestamp.
Sources disclose their latest publication separately from their receipt date.
An old publication does not become fresh merely because it was just ingested.

## Comparison contract

Each record identifies one `(source_id, contract_id, item_id)` case. Supply a
positive integer `revision` and immutable publisher `event_id` for each cumulative
snapshot. A snapshot is a cumulative value for a stated period, not an increment.
Later revisions replace the current view; they are not added to prior revisions.

`expected` contains:

- `value`: nonnegative decimal, up to 24 digits including up to six decimal places;
- `metric`: `delivery`, `payment`, `goods_export` or `goods_import`;
- `unit`: stable physical unit, or exactly `currency` with an ISO currency;
- `currency`: uppercase ISO code for money; null for physical measurements;
- `period_start`, `period_end`: ISO calendar dates;
- `document_url`: reference for the expected baseline;
- `due_at`: timezone-aware due timestamp, on/after the period end.

`observed` is null when unknown. Otherwise it contains the same measurement
fields plus a timezone-aware `observed_at`, and its own document reference.
Its observation cannot predate its period end or postdate `published_at`.
Publication cannot be over five minutes in the future. Server `received_at` is
recorded separately. Decimal **strings** are recommended to preserve source
precision through external JSON clients.

The server subtracts only when metric, unit, currency and covered period match,
the target is due, and the observation covers the deadline. It distinguishes:

| State | Meaning |
| --- | --- |
| `missing_observation` | No observation; unknown is not zero. |
| `not_comparable` | Metric, unit, currency or covered period differs; no subtraction. |
| `not_due` | Target is not due; no shortfall inferred. |
| `awaiting_due_observation` | Latest observation predates the due time. |
| `shortfall` | Comparable observed value is below expected. |
| `matched` | Comparable attributed values are equal. |
| `overage` | Observation exceeds the baseline; retained separately. |

The measured shortfall is `max(expected − observed, 0)`. Overage is the reverse
positive difference. An explicit zero observation is valid evidence of a reported
zero; absent evidence never becomes zero. No exchange conversion, inferred item
valuation, linear forecast or theft estimate is produced. Units are matched
exactly, not automatically converted. Case classification is publisher-supplied.

Totals use only the latest revision and comparable cases. They remain separate
by **source, category, metric, unit, currency and covered period**. Missing,
incomparable, pre-deadline and not-due values are excluded. Overages never cancel
shortfalls. Separate publishers can cover the same underlying contracts; their
totals are never merged into a global figure. Stable record/line identities and
nonoverlapping source classifications remain the integration mapper's duty.

## Engine execution

An optional `procurement_record` carries OCDS-shaped JSON. Its `ocid` must match
`contract_id`; it is passed to the existing `/analyze` implementation using the
source's explicitly selected calibration profile. The full response and analysis
receipt are saved. Origin/destination codes do not determine the legal profile.
A source adapter must choose and validate the applicable jurisdiction mapping.

Comparable, due, physical **delivery** quantities are also passed to the existing
`/delivery/analyze` implementation as an outcome record. Missing observations,
unknown dimensions and mismatched measurements do not generate a default clean
result. Payment/export/import measures are compared in the ledger but do not get
misrepresented as delivery-engine input. Engine runs cover supplied dimensions
only; a low/no-finding result does not verify absent financial, staffing,
inspection or custody evidence. The existing delivery engine uses floats and
its calibrated thresholds; the independent ledger differences use decimal
arithmetic and retain the original values.

A failed validation/analysis rejects the atomic intake batch. Engines can report
partial/error stages in their normal response format; those are retained and
shown. Responses already stored for an identical replay are reused, rather than
rerunning analysis. This is synchronous bounded ingestion (50 events / 2 MB),
not a distributed background job service.

## API for an authorized institutional adapter

The deployment's existing access gate also protects `/operations/*`. Generated
request schemas are in `/openapi.json`.

| Endpoint | Purpose |
| --- | --- |
| `GET /operations/status` | Mode, source-connection and storage limits. |
| `POST /operations/sources` | Register immutable source identity/configuration. |
| `GET /operations/sources` | Publisher attribution and publication freshness. |
| `POST /operations/ingest` | Atomically validate/analyze/save up to 50 snapshots. |
| `GET /operations/cases` | Search/filter/paginate current cases and separated totals. |
| `GET /operations/cases/{id}` | Current comparison, stored engine results and history. |
| `POST /operations/cases/{id}/review` | Follow/assign/note/status with revision and audit-head locking. |
| `GET /operations/cases/{id}/report` | Escaped, self-contained readable HTML brief, printable to PDF. |
| `GET /operations/cases/{id}/export` | Full source/engine/review evidence packet. |

An identical event replay is idempotent. Changed content under the same event ID,
a different event under an already used case revision, or a higher revision with
an earlier publication time yields HTTP 409. Late older revisions are retained
as history without replacing the latest one. Baseline/category changes are
explicitly recorded and highlighted in the queue and case, alongside the previous target. A conflict rolls back the ledger batch.

Review updates require `expected_revision`, `expected_audit_head`, `status`,
`followed`, an analyst/owner label and a nonblank `note`. Concurrent source or
review changes reject a stale edit with HTTP 409. The UI retains a dirty review
draft and requires acknowledging new case history before saving against it.
An analyst label is not an authenticated institutional audit identity.

A connector client is included:

```sh
python scripts/submit_operations.py \
  --url https://YOUR-SUNLIGHT-HOST \
  --source /secure/path/source.json \
  --batch /secure/path/batch.json --dry-run
```

Dry run validates locally and sends no requests. Remove `--dry-run` to submit.
The optional source file registers the source before ingestion. Provide deployed
Basic access through securely injected `SUNLIGHT_CONNECTOR_USER` and
`SUNLIGHT_CONNECTOR_PASSWORD`, not command arguments or committed files. The
client requires HTTPS (loopback HTTP allowed for development), follows no
redirects, and does not log credentials or payloads. This client submits an
already mapped source envelope; it does not scrape a UN system or authenticate
publisher truth from its name or URL.

## Deployment storage and institutional boundary

SQLite is stored at `SUNLIGHT_OPERATIONS_DB`, defaulting to
`$SUNLIGHT_CALIBRATION_DIR/operations.sqlite3` or the local `calibration/`
directory. Records survive process restarts on the **same filesystem**. An
ephemeral Render filesystem can erase the ledger on redeploy; the API and UI do
not claim that deployment-volume durability has been verified.

For the existing Render service, before retaining institutional records:

1. Attach a persistent disk at `/var/data/sunlight` using a disk-capable plan.
2. Set `SUNLIGHT_OPERATIONS_DB=/var/data/sunlight/operations.sqlite3` in the
   service environment. Ensure the application user can write the mounted path.
3. Keep a single replica, verify records survive a restart/redeploy, and establish
   backups and restoration. Do not point a multi-replica deployment at local
   SQLite and assume shared/consistent storage.

No paid disk, credentials or external account have been created by this change.
A real institutional deployment still needs gateway identity/access roles,
per-source authorization, validated source mappings, publisher authentication,
managed refresh/cursor/retry policy, retention/backup controls and independent
inspection/custody/delivery evidence. The current application is a shared-access
pilot ledger, not an institutional SSO or tenant-isolation service.

Document URLs are references only: this workflow does not fetch/validate their
contents. Case hashes cover normalized submissions and saved analysis, not
original source bytes or authenticated document signatures. The per-case audit
hash chain detects edits/deletions inconsistent with retained history; a database
owner can rewrite an entire unanchored chain. It is not a theft verdict, source
signature, external timestamp or legal chain-of-custody certificate.

## Validation

Targeted tests cover exact comparisons, real procurement/delivery engine runs,
replay idempotence, atomic rollback, conflicting/late revisions, baseline changes,
review locking/reopening, source freshness, access gating, filtering/pagination,
and local packet integrity. Browser checks exercise source registration, actual
engine ingestion, exact gaps, review persistence through reload, correction
without double counting, packet export, mobile layout and retained globe access.
Synthetic browser test records are explicitly labeled and confined to a local
test database; they are not bundled into the hosted ledger.

Validation run: **2,030 Python tests passed, 3 skipped** (Docker tests excluded), **33 frontend tests passed**, and production build passed with `/watch/` asset paths. A local process restart preserved all six test cases, their revisions, normalized hashes and review state on the same SQLite filesystem. Connector dry run, actual local submission and duplicate replay were exercised. This verifies same-filesystem persistence; it does not verify a Render persistent volume.

Interface captures use synthetic integration-test data only: [operations desk](interface/Operations-Desk.png) and [mobile investigation](interface/Operations-Mobile.png).
