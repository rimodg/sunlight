# Delivery assurance: from public promise to recorded result

SUNLIGHT now has a working obligation-centred workflow at `/watch/#delivery`.
It connects a programme or contract baseline to separately attributed financial,
physical-delivery and service records, exposes breaks in that chain, and retains
accountable follow-up. The global watch remains the geographic entry point.

This is a shared-deployment pilot for supplied evidence. It is not a connected
bank ledger, authenticated receiving network, global spending census or payment
control system. “Recorded arrival” means an attributed submitted credit, not
independently confirmed arrival. Distinct declared issuer IDs do not establish
source independence.

## Use the visible workflow

1. Open **Delivery assurance** from the navigation or the watch's delivery strip.
2. Choose **Open worked example** to inspect the complete fictional chain. It is
   labelled synthetic and excluded from the default institutional portfolio.
3. Choose **Register an obligation** for a programme or delivery item. Supply its
   stable reference, baseline document, intended recipients, owner, quantity,
   unit and deadline. A service outcome target and budget are optional.
4. Use **Record evidence** for each actual ledger entry or cumulative delivery
   snapshot. Sender debits and recipient credits are separate records, each with
   an issuer, unique entry reference, source URL and observation time.
5. Open **Evidence & breaks**. Each issue provides the next evidence to obtain
   and an **Assign follow-up** action with a responsible team and deadline.
6. Use **Response & follow-up** to record progress. Completion requires a current
   retained evidence reference. Completing a task does not erase a discrepancy.
7. Use **Investigate this obligation** to carry its exact ID, country and evidence
   layer into the research desk. The saved dossier retains calculated facts and
   supporting references. Add relevant PDFs there if needed.
8. Open **Readable brief / PDF** for a printable report of the obligation,
   measurements, issues, sources, engine findings, follow-ups and history.

The page also offers explicit jurisdiction calibration and a **Run calibrated
delivery checks** button. It runs the existing delivery engine only when the
accepted quantity is comparable and covers the obligation deadline. The saved
run records the profile, input version, source evidence IDs and result. A later
correction changes its “basis current” flag; earlier results remain retained.
This adapter uses the engine's existing float-based quantity representation;
the ledger's exact decimal comparison is separate. No absent inspection,
resource, financial or procurement dimensions are invented.

## Measurement and reconciliation contracts

An obligation currently describes one delivery target, an optional service
target and a shared deadline. Its baseline is immutable. Formal baseline
amendments, multi-item programmes and different deadlines per milestone remain
future work; do not register amended versions as duplicate funding obligations.

Financial entries use the tuple **transfer ID + sender party ID + recipient
party ID**. These are operator-supplied correlation identifiers, not a bank's
authentication result. One executed debit can be allocated to only one
obligation in this pilot. Partial credits use distinct issuer ledger references.
Splitting one transfer across programmes requires an allocation model that is
not implemented here.

- An absent sender debit is **sender unobserved**; recorded credits remain
  visible without inventing the outgoing amount.
- An absent recipient credit is **arrival unobserved**, or **awaiting settlement**
  while the sender's settlement deadline remains open. Missing is never zero.
- Currency disagreement, a credit preceding its debit, or a sender/receiver
  issuer label shared across the records blocks a settled residual.
- Raw difference is sender debit minus submitted recipient credits. Once the
  settlement window closes and comparison conditions hold, the claim-based
  residual subtracts submitted pre-credit deductions. Both quantities remain
  visible. A deduction is not treated as independently validated.
- Post-credit refunds, payment reversals, FX conversion, intermediary custody
  and cross-currency settlement are not modelled. Do not disguise them as
  pre-credit deductions.
- Negative residuals remain excess arrivals. They do not offset shortfalls in
  other transfers. No cross-domain or “global theft” sum is produced.

Dispatch, receipt, acceptance and service records are **cumulative snapshots**
for the exact obligation. SUNLIGHT uses the latest coverage per declared issuer,
never adds repeated cumulative reports, preserves explicit zero, and refuses to
choose between conflicting issuer values or coverage times. The target and
snapshot must share a unit. Due comparisons require coverage at or after the
deadline; this describes the current cumulative report, not a reconstruction of
the exact historical state at the deadline. Equal-timestamp delivery stages
with impossible quantity ordering produce a review issue.

Acceptance and service shortfalls have their own units. A funded amount cannot
be subtracted from a kit count, and accepted kits do not prove a causal service
benefit. A matching report is labelled **reported target met**.

## Persistence, corrections and action history

`code/delivery_assurance.py` uses the existing `SUNLIGHT_OPERATIONS_DB` SQLite
path and additive `assurance_*` tables. Existing operations/research records and
calibrated rules are preserved. Writes acquire a SQLite write lock and compare
the expected obligation version; stale writes return HTTP 409, preserving the
draft in the UI until the investigator reviews the latest version.

Evidence is appended. Corrections reference the current entry and preserve its
stage, issuer, ledger reference and transfer identity. Prior payloads remain
available. A duplicate issuer/stage/entry reference is rejected across
obligations. Source correction is distinct from an authorized baseline amendment.

Follow-ups record a response type, issue link, responsible label, deadline and
note. Their local completion requires a current evidence ID from the obligation.
If that evidence is later superseded, a new review signal appears. A task's
completion never changes measured quantities or silently resolves an issue.
No email, external request, financial hold or payment instruction is sent.

The export checks a local hash chain against baseline, evidence content,
supersession relationships, latest action state and engine-run payloads. This
detects inconsistent local modification. It is not an external signature,
independent timestamp, proof of issuer authenticity or protection against an
administrator rewriting the entire database and chain.

**Hosting:** mount the SQLite path on a persistent writable volume and operate
one replica. The supplied free Render blueprint remains ephemeral; this change
does not silently switch plans or purchase a disk. A process-restart check on
the same local filesystem passed, which does not establish Render durability.
Shared access is not individual or tenant authorization. Institutional operation
requires the appropriate identity, source permissions, durable storage and
authenticated adapter mappings.

## API and investigation integration

- `GET /assurance/status`: precise capability and connection status.
- `GET/POST /assurance/obligations`: scoped portfolio / baseline registration.
- `GET /assurance/obligations/{id}`: retained chain and current assessment.
- `POST /assurance/obligations/{id}/evidence`: attributed entry or correction.
- `POST /assurance/obligations/{id}/actions`: assigned follow-up.
- `POST /assurance/obligations/{id}/actions/{action_id}`: progress or completion.
- `POST /assurance/obligations/{id}/delivery-analysis`: calibrated acceptance run.
- `GET /assurance/obligations/{id}/report`: escaped readable/printable HTML.
- `GET /assurance/obligations/{id}/export`: technical audit packet.
- `POST /assurance/example`: explicit, reusable synthetic worked example.

All evidence/action/analysis writes require `expected_version`. Schema details
are available in `/docs`; the normal UI requires no JSON editing.
Amounts use decimal strings or exact JSON integers. Floating-point JSON amounts
are rejected to avoid accepting a value already rounded by a JSON decoder.

The research layer `delivery_assurance` retrieves the latest 200 scoped
registered obligations, or an explicit selection of up to ten. Country scope
is applied before the scan; year filters use the obligation's deadline year.
Synthetic examples are excluded unless their IDs are explicitly selected.
Facts retain exact amounts, stages, current issues, follow-ups, source URLs and
engine results. Saved inquiry snapshots remain unchanged after later source
corrections; rerun to create a linked updated dossier.

The optional model has a read-only `inspect_delivery_obligation` tool and
stage-specific issue counts. Original layer/country/year/obligation selection
is enforced in code. It cannot widen its scope, alter records, authenticate
issuers or act on funds. Evidence retrieval works without a provider credential;
live model quality is not established by mocked tool-protocol tests.

The UI refreshes the active assurance desk every 20 seconds and immediately
after local submissions. This is a changing registered-evidence workspace,
not a live worldwide financial feed. The map's dated movement context retains
its existing periods and coverage limitations.

## Validation

See the delivery-assurance addendum in
[the validation record](VALIDATION_2026-10-19.md). Tests cover exact large decimal
values, partial credits, explicit zero, missing arrival, duplicate allocation,
currencies, clocks, issuer overlap, cumulative/conflicting snapshots, corrections,
stale writes, evidence-backed completion, local integrity, saved inquiry scope,
synthetic isolation and calibrated-engine evidence freshness. Chromium exercised
the guided workflow, printable PDF and desktop/mobile handoffs.

Review the [workspace screenshot](interface/Delivery-Assurance.png) or the
[explicit synthetic example brief](presentation/SUNLIGHT-Delivery-Assurance-Example.pdf).
