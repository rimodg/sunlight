# SUNLIGHT as an institutional instrument

Product questions, software audit and implemented response · 20 October 2026.
Baseline reviewed: `afcf33b`. This is a product and engineering assessment, not
institutional endorsement or evidence of adoption.

## 1. Who needs this instrument?

The first operational users are people accountable for a defined resource chain.
Their problem is not a shortage of world totals. It is the inability to connect
authorisation, execution, arrival, acceptance and public benefit with comparable,
attributable evidence and a person responsible for unresolved questions.

| User | Decision they need to make | Evidence needed | Useful SUNLIGHT output |
|---|---|---|---|
| Treasury and financial controller | Does a released payment reconcile to recipient credits and legitimate deductions? | Debit, separate receiving record, shared transfer identity, currency, settlement cutoff and correction history | Exact per-transfer residual or an explicit missing/non-comparable state; a responsible financial review |
| Procurement and contract manager | Does the current contract and its execution warrant review? | Contract, competition facts, applicable profile, amendments, invoice and acceptance basis | Existing calibrated rule findings, current source revision, readable case brief and review history |
| Programme manager, warehouse or receiving team | What was accepted, when, and what service was actually available? | Deadline-covering cumulative receipt/acceptance, issuer attribution, units and service target | Separate physical/service shortfalls, missing evidence requests and dated follow-up |
| Internal auditor, supreme audit institution or inspector | Which cases require independent examination and what supports the conclusion? | Original sources, reproducible calculation, prior versions, amendments, engine inputs and reviewer notes | Inspectable dossiers and priority work, with the source condition kept separate from administrative closure |
| Multilateral or humanitarian fiduciary/results team | Which registered projects have unresolved delivery, financial or assurance questions? | Portfolio denominator, independent recipient/field evidence, owners and deadlines | Scoped review queue, country context, project-level source trail and a meeting brief |
| Economic researcher or policy team | What does the published evidence support about a country or relationship, and what remains unknown? | Dated statistical definitions, coverage, units and attribution | Monetary atlas, source-preserving map, bounded cited investigation and explicit gaps |

A financial-intelligence or law-enforcement body may eventually use an authorised
investigative view, but public statistics alone do not identify beneficial owners,
private bank payments, criminal intent or legal authority to intervene. Public
transparency and protected institutional casework also need separate access models;
the current shared deployment access gate does not provide that separation.

## 2. What problem does SUNLIGHT answer?

The operational question is:

> For a specific public obligation, what was promised, what was executed, what
> arrived, what was accepted, what benefit was evidenced, what cannot yet be
> reconciled, and who is responsible for the next check?

Scarcity can result from theft, failed delivery, poor procurement, timing,
classification problems, waste or simply missing evidence. These causes require
different remedies. A single global “gap” subtracting published spending from
unmatched observations would obscure those distinctions and produce false losses.

The instrument therefore needs three connected levels:

1. **World context:** source-dated economic relationships and coverage, useful for
   orientation and forming questions.
2. **Comparable evidence:** attributable obligations, transactions, physical
   stages and service outcomes, with stable identities and original periods.
3. **Responsible work:** a reviewable condition, a next evidence requirement, an
   owner/deadline, calibrated checks where eligible, and retained outcomes.

The globe should orient a decision. The dossier should substantiate it. The
review workflow should make it possible to act within an institution's mandate.
A map mark alone cannot justify a payment stop or allegation.

## 3. How could SUNLIGHT become a default tool?

“Default” is an adoption outcome that must be earned. More datasets and a polished
interface do not establish it. The strongest entry is a repeatable assurance
workflow alongside existing treasury, procurement and programme systems.

A credible sequence is:

1. Choose a bounded portfolio and accountable sponsor. Identify all obligations
   in the pilot, their owners, source systems and expected receiving evidence.
2. Connect actual source identifiers and authorised records. Keep budget,
   commitment, executed debit, credit, acceptance and service measures separate.
   Global statistics provide context, not substitute bank or inspection records.
3. Demonstrate correct, reproducible checks and useful handling of missing,
   conflicting and corrected evidence. Compare against independent human review.
4. Show that operators complete the work faster and that issues have owners,
   deadlines, retained evidence and documented outcomes.
5. Establish identity, permissions, segregation of duties, durable storage,
   operational monitoring, data agreements and deployment ownership.
6. Expand to further countries and domains through documented mappings and
   interoperability standards, rather than replacing their accounting rules with
   a universal score.

The adoption thesis is that an institution repeatedly returns to SUNLIGHT because
it can see what requires attention, understand the basis, complete its work and
reproduce the record. Institutional integration and independent validation remain
necessary; no current UN, World Bank or treasury partnership is implied.

## 4. What must the engines do?

The existing detection and calibrated delivery engines should assess their
eligible inputs and retain their rule evidence. Exact ledger comparisons should
continue to use decimal quantities, units, currency, coverage dates, settlement
cutoffs and source identity. These are distinct calculations.

The review queue must then explain:

- Whether a difference is actually comparable and due, or evidence is absent.
- Whether the relevant engine ran, has input errors, or needs rerunning because
  its acceptance basis changed.
- Which specific source condition needs review and what evidence to obtain next.
- Which follow-up/reviewer is assigned, with deadline and recorded history.

Queue priorities in this release are deterministic work-order rules, not a new
fraud model or calibrated global risk ranking. No country, conflict, wealth,
budget magnitude or cross-currency comparison determines priority. An engine's
“current” status refers to retained evidence inputs, not independent source
verification or proof that its calibration is suitable for every jurisdiction.

## 5. Software audit and the changes made

| Reviewed gap | Institutional consequence | Implemented correction |
|---|---|---|
| Global watch exposes context and individual desks but no unified work list | Operators cannot reliably answer what needs attention now across registered resources | Review queue derived from current delivery obligations and latest source case revisions |
| Portfolio footer only offers a general delivery entry | World context does not lead clearly into concrete review work | Queue entry and registered review/assignment/overdue counts around the persistent globe |
| Case and obligation selection rely on local component state | Reopening an already mounted desk can show the previous dossier | Explicit selection requests for the exact record; working URL links for obligations and cases |
| Source cases have a review label that can be confused with correcting the source condition | A completed review could be read as an erased shortfall | Completed reviews are filterable separately; their source condition and measured difference remain retained |
| Per-record actions exist but no central assignment entry | Evidence gaps have no convenient route to accountable work | Direct evidence follow-up assignment with owner, deadline, issue key and optimistic version check |
| Navigation/filter changes can replace an unsaved source-case review | Analysts can lose work or review the wrong dossier | Draft-preserving pending-record handoff, explicit discard/keep choice, and guarded asynchronous case loads |
| Individual reports exist but no scoped review meeting output | Teams cannot readily take the current priority work into a review meeting | Readable, escaped HTML brief with scope, as-of time, record versions, next evidence, owners and dossier links; print/save PDF |
| Calibrated recommendations, evidence-gate detail and engine state are scattered or underexposed | A previous check can look applicable after acceptance evidence changes | Queue retains statistical recommendations and yellow/red evidence-gate review leads even when reported values match; the dossier exposes profile, structural verdict, confidence, gate dimensions and thresholds, alongside current/stale/error state |

The queue assesses all current registered records in the selected deployment,
country and record-type scope before pagination. It does not silently scan only
the newest 100 or 500 records. The meeting brief explicitly limits display to the
first 500 matching records and reports its denominator; refine scope for larger
meetings. This pilot currently recalculates from SQLite rather than maintaining a
streaming/materialised institutional index.

## 6. How the working interface is used

Open **Review queue** beside the globe, or `/watch/#queue`.

1. Choose a work focus: treasury/control, programme/receiving, procurement/trade
   or audit. These are task filters, not access roles.
2. Use country, record type, owner/reference search, assignment and review filters.
   Counts identify registered scope and current matching work.
3. Read the priority's reason, actual next evidence, deadline, responsibility,
   engine basis and exact individual measurement. Missing evidence has no invented
   monetary value; physical and financial measures remain separate.
4. Open the exact dossier and existing rule findings, or assign an evidence
   follow-up directly for a delivery obligation.
5. If a concurrent revision invalidates the draft version, keep the draft,
   inspect the changed evidence and explicitly refresh its version before saving.
   An issue that has cleared or changed cannot silently receive an old assignment.
6. Review progress and evidence in the retained obligation/case history. Completion
   of a follow-up does not zero the underlying comparison. A new current source
   revision reopens the source-case review through the existing ledger workflow.
7. Use **Review meeting brief / PDF** for a scope-labelled human-readable output,
   or each dossier's existing complete source/report history.

The same globe remains mounted while using the queue, monetary atlas, record,
delivery and research desks. **Locate country on watch** changes geographic scope
without dismissing the queue. It locates the country reference, not an invented
project/warehouse coordinate. Selected-obligation investigation preserves the
exact obligation ID and evidence-source selection.

## 7. What makes each visual or control justified?

- A world relationship must retain a direction, source period and inspectable
  source. Annual statistics must not appear as authenticated live payments.
- A country symbol must identify a real reference and show the selected measure's
  basis. It must not imply that unobserved countries have zero economic activity.
- A global number must explain its denominator, year, unit, overlap and source.
- A priority colour must mean a disclosed work category, not presumed criminality.
- An action button must open an exact record, calculate on eligible retained
  evidence, record an attributed workflow change or produce a readable output.
- A disabled/missing calculation must state which evidence or comparison condition
  prevents it. Absence of an engine result cannot look like a clean verdict.
- A refresh must identify the current assessment time and retain/report failure.
  Rechecking existing records is distinct from ingesting a new upstream feed.

The audit improves the central decision loop; it is not a claim that every legacy
screen or possible enterprise user journey has been exhaustively validated.

## 8. Evidence required for institutional adoption

| Gate | Current position | Evidence required before claiming readiness |
|---|---|---|
| Public source provenance | Dated and pinned snapshots, source definitions and coverage are available | Provider terms, current retrieval, correction handling and domain-specific reconciliation tested against publisher records |
| Financial and delivery evidence | Registered, attributed claims with exact comparability checks | Authorised treasury/bank/ERP and receiving/inspection connections, independently mapped identities |
| Calculation validity | Automated regressions and calibrated existing engine paths | Independent domain review and blinded, representative known-outcome evaluation; calibration applicability and uncertainty assessed |
| Identity and duties | Shared deployment access; owner/reviewer labels | Institutional SSO, per-source/tenant roles, dual controls where required and auditable signing identities |
| Durability and operations | SQLite on deployment filesystem; persistence not independently verified | Approved durable storage, backups/restores, retention, monitoring and replica/scale tests |
| Intervention | Retained follow-ups; no external payment or enforcement executor | Legal mandate, authorised actor, approval path, idempotent institution connector and acknowledged result |
| Pilot value | End-to-end browser workflows exercised on isolated synthetic/public fixtures | Measured institution pilot with a known denominator, independent receiving evidence and operator outcomes |

Success measures should be defined with the sponsor: time to first review, time
to obtain missing evidence, assignment coverage, overdue follow-ups, independent
confirmation/false-positive rates, repeatability from retained inputs, and verified
service/acceptance outcomes. Monetary benefits must be independently supported
and reported within compatible currency, period and stage. Software test counts
are engineering evidence, not a corruption-detection accuracy study.

## 9. Technical and scope notes

`GET /workbench/review-queue` derives one work item per current obligation/source
case and uses one SQLite read snapshot. Optional country, work-focus, record-type,
query, assignment, reviewed-state and isolated-example filters are supported.
Pagination is applied after scoped assessment and disclosed deterministic ranking.
Priority order is measured comparable differences, overdue follow-ups, evidence
work and planned checks; ties use due time and stable record identity. Completed
source-case reviews have a separate lower-priority view.

The queue reuses existing reconciliation, comparison and analysis data. It neither
changes detection thresholds nor adds budgets, physical shortages or unlike
currencies together. Ownership remains a label until institutional identity is
connected. API queue derivation is read-only; its assignment form uses the existing
version-checked, audited obligation action endpoint. No external person is
messaged and no money moves when a follow-up is saved.

The existing [institutional standards research](INSTITUTIONAL_REBUILD_RESEARCH.md),
[monetary source/accounting notes](MONETARY_ATLAS.md) and
[delivery assurance contracts](DELIVERY_ASSURANCE.md) provide the supporting
architecture and current capability boundaries.

Implementation and browser evidence: [institutional validation](VALIDATION_INSTITUTIONAL_2026-10-20.md).
