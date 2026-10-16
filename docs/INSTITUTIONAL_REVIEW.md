# SUNLIGHT: institutional review brief

SUNLIGHT examines whether records of public value agree with their governing
rules and with independently supplied evidence. Procurement is the operational
entry point. The wider Global Humanitarian Watch is the staged direction in
[Charter v2](CHARTER_v2_global_humanitarian_watch.md).

## The institutional problem

An award, a payment, a delivery report, and an outcome claim can each look
plausible while their relationships contradict one another. Reviewing them
separately can leave that contradiction undiscovered. Oversight teams also have
limited capacity: a queue that silently exceeds its declared ceiling is not a
workable handoff.

SUNLIGHT provides a repeatable reading of supplied records with attributable
rules, separate evidence-gate reasoning, visible input gaps, and a portable
analysis packet. It supports an institution's review process. It has no mandate
to determine wrongdoing or execute financial or enforcement actions.

## A five-minute examination

1. Start the API and dashboard using the commands below. Open the dashboard in
   the local development environment.
2. Run the clearly labelled synthetic direct-award example. Inspect the actual
   rule output and its citation. Explain that the finding identifies a condition
   requiring review, not proof of an unlawful award or intent.
3. Run the sparse-record example. Inspect missing fields and indeterminate axes.
   Absence of a reported contradiction is not an integrity certificate.
4. Supply a public OCDS-shaped record. Select an appropriate jurisdiction and
   confirm its currency. Review the engine's observed basis alongside the source
   document; this interface does not authenticate the document.
5. Download the packet. Run the offline verifier. Inspect the calculation trace
   and the deployment requirements under Institutional readiness.

For an international-relations reviewer, the wider research question is how
reporting obligations and cross-border records can be read consistently, with
public versus institutional access stated explicitly. For an economics reviewer,
the question is what the measurements establish, their calibration and sampling
limits, and whether they improve review allocation. For a trade reviewer, it is
whether counterpart records and physical traces support a reproducible chain.
Those additional domains require their own validated adapters and reference sets;
procurement performance cannot establish performance in another domain.

## What is executable now

| Capability | Review artifact | Important boundary |
|---|---|---|
| Single procurement record | `POST /analyze` | Supplied inputs; no authentication of external facts |
| Portfolio triage | `POST /batch` | Hard capacity ceiling; administrative tie ordering is disclosed |
| Structural and evidence-gate trace | Per-result response | Different quantities; neither is a probability of corruption |
| Input completeness | `ingestion_quality` | Equal-weight presence heuristic over 15 fields; numeric zero counts as missing in v1 |
| Reproduction receipt | `analysis_receipt` | Content hashes, source manifest, calibration hashes, selected runtime versions; not a signature |
| Delivery, recovery, and corroboration | Separate OpenAPI workflows | A procurement response does not run or substantiate all these stages |
| ATT reporting-consistency rules | Python library and tests | No general transfers endpoint or global observation service |
| Current capability boundaries | `GET /assurance` | Descriptive metadata, not accreditation or a live evaluation |

The shared cross-category Registry, generalized Need Ledger, and broader
observatories remain charter work. Quantum and Compass adapters remain stubs.
Institutional approval, partnerships, external security review, and access to
private systems have not been established by these software changes.

## Calculation and queue policy

Analytical verdicts and evidence gates retain their existing rules and
thresholds. The output composite summarizes determinate structural sub-scores;
its qualification and decomposition remain visible. It must not be presented as
an estimated probability of corruption.

The queue includes only successfully analyzed records clearing the statistical
review threshold. With a capacity budget, selection takes at most that many
records, ordered by risk descending and OCID ascending. Exact duplicate OCIDs
fall back to submission index. Equal-score boundary cases are reported in
`threshold_metadata.boundary_tie`, including whether each was selected. Deferred
records remain in the result; their findings do not change. Identifier ordering
is administrative and makes no claim that one tied case is more serious.

`binding_threshold` alone is not a selection predicate when ties are present or
capacity is zero. Consumers must read the per-record recommendation flag and the
selection metadata. No non-finite threshold values are emitted.

## Reproduction and content verification

The downloaded JSON contains the submitted request, response, and declared input
origin. Each receipt retains the normalized request used for its input digest.
The packet request is also checked against a separate submitted-request digest.
The download preserves API number serialization to avoid client-side rounding.
Batch receipts bind the normalized batch digest and record index as well as the
individual contract. Retain the full batch request to reproduce a batch.

Canonical hashes use UTF-8 JSON with sorted keys, compact separators,
`ensure_ascii=False`, and no non-finite numbers. The result digest excludes
`processing_time_ms`, `analysis_receipt`, and
`structural_scoring.corpus_stamp.computed_at`. No analytical finding is excluded.
Restart the API after changing source files so the executed code matches the on-disk tree.
The source manifest fingerprints Python files under `code/`; it does not claim
to cover every asset or third-party dependency. Profile and global-parameter
hashes identify calibration content. Record the complete dependency environment
for release reproduction, in addition to the key versions included in a receipt.

```bash
cd /workspace/sunlight
/workspace/.venvs/sunlight/bin/python scripts/verify_evidence_packet.py /path/to/sunlight-evidence-packet.json --code-root code
```

An edited packet should fail verification. A self-consistent replacement can
still be fabricated by replacing both data and hashes. Trusted signing,
institutional custody, and independent source authentication are separate work.
The verifier checks content equality, not substantive correctness.

## Development run

```bash
cd /workspace/sunlight
/workspace/.venvs/sunlight/bin/python -m uvicorn api:app --app-dir code --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd /workspace/sunlight/sunlight-dashboard
npm ci
npm run dev -- --host 127.0.0.1
```

`SUNLIGHT_API_TARGET` can override the development proxy target. Production
hosting must configure equivalent same-origin routes; a Vite production build
does not itself provide the API proxy. The API requires an authenticated,
authorized institutional gateway before exposure. Use public or synthetic
inputs for demonstrations until appropriate data-handling controls exist.
Downloaded packets include submitted records and must inherit their disclosure
restrictions. This workspace does not implement the charter's complete
protection-sensitive disclosure workflow.

## Evaluation and release evidence

Run the ordinary suite with:

```bash
cd /workspace/sunlight
PYTHONPATH=code /workspace/.venvs/sunlight/bin/python -m pytest tests/ -q --ignore=tests/test_docker_live.py
cd sunlight-dashboard
npm run build
```

The five DOJ fixture tests require the root `prosecuted_cases.json`. Its last
tracked version was recovered from Git history for current-instance validation.
Reproduce that restoration without overwriting an existing file with:

```bash
python scripts/restore_reference_cases.py
```

This restores an existing reference artifact; it does not create or reconstruct
the 42,835-contract database. That SQLite database was not found in the available
checkout or Git history. The prosecution fixture and the database are separate
prerequisites. The tracked
`knowledge_base/legal_framework/prosecuted_cases.json` has a different schema and
is not a replacement. Do not manufacture a corpus or omit failed tests to claim
the suite is green.

Historical procurement metrics must be reproduced with the exact reference
database, prosecution corpus, profile, and sampling settings. The existing
readiness assessment records this protocol:

```bash
python code/evaluation.py --db /path/to/reference.db --cases /path/to/prosecuted_cases.json --seed 42 --bootstrap 1000 --clean 200 --profile doj_federal
python code/doj_validation.py --db /path/to/reference.db --cases /path/to/prosecuted_cases.json --seed 42 --bootstrap 1000 --clean 200
```

The historic confusion matrix TP 9, FN 0, FP 18, TN 182 describes the evaluated
sample, not 42,835 independently labeled outcomes. Observing no misses among
nine evaluated positive cases does not establish universal recall. Test results,
evaluation metrics, and operational field performance are different evidence.

This increment changes the output, triage allocation, presentation, fallback
normalization, and supplier feature-extraction paths. It does not change rule
conditions or threshold calibration, but restored source fields can change
which rules fire. The full reference
evaluation is unavailable in this environment and must precede a release claim
that the published floor has been reproduced.

## Mapping corrections and remaining visibility

The audit demonstrated that the fallback normalizer lost `buyer.id`, tender-period
dates, and award-level suppliers without supplier parties. These supplied fields
now populate the normalized dossier. Supplier feature extraction uses the
normalized or award-level identities when supplier parties are unavailable;
richer supplied parties retain precedence. Regression tests verify the mappings
and confirm absent fields remain unknown. No rule threshold was changed.

The new `mapping_gaps` report remains in the output to expose any of these known
handoffs that are supplied but not reflected in normalized fields. It is not
an exhaustive validation of OCDS. Full reference evaluation remains a release
gate for these detection-path corrections.

## Next gates toward a pilot

1. Restore and run the exact reference evaluation; obtain independent execution
   and preserve the run artifacts. Reconcile the charter's open release gates.
2. Validate rule-specific legal applicability with domain reviewers. The current
   citations and profiles are analytical configuration, not legal advice or
   verified applicability to every contract date and exemption.
3. Validate mappings on an institution-approved, bounded dataset. Examine errors,
   false positives, unassessable cases, and analyst workload against its current
   process. Agree the acceptance criteria before running the pilot.
4. Establish secure integration, data-sharing, retention, corrections,
   protection-sensitive disclosure, and accountable case routing.
5. Demonstrate an end-to-end review handoff with a named owner and recorded
   disposition. Claims about prevented loss, recovered money, and improved
   outcomes require observed evidence from the corresponding operational stages.

The wider watch should earn coverage category by category. Presentation can make
the value inspectable; adoption must be established through those results.
