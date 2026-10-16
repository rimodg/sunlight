# Evidence workspace validation, 16 October 2026

Base checkout: `92c8ec0`. Results below describe the working-tree changes, not a
published release. Runtime: Python 3.12.14, Node 24.19.0, npm 11.9.0.

## Executed checks

| Check | Result |
|---|---|
| Non-Docker suite: `PYTHONPATH=code python -m pytest tests/ -q --ignore=tests/test_docker_live.py` | 1,988 passed, 3 skipped, one upstream deprecation warning |
| Focused receipt, normalization, API, and completeness tests | 56 passed |
| Dashboard: `npm run build` | Passed |
| Chromium, default development workflow | Live API connection, actual PROC-001 finding, corrected normalized inputs, single and batch downloads, offline hash verification, readiness tab, mobile layout, prototype disclosure; no browser exceptions |
| Additional browser checks | Sparse record, malformed JSON, and tamper rejection passed |
| 1,000-record synthetic batch, capacity five | 1,000 results, exactly five recommendations, 5.77 seconds in the current process, approximately 23.9 MiB response |
| `git diff --check` | Passed |

The batch timing is one synthetic local measurement, not a production benchmark
or service-level commitment. Repeated per-record manifests make large responses
substantial; shared batch manifests are a possible future optimization.

## Reference artifact recovery

The ignored root `prosecuted_cases.json` was absent from the initial checkout.
Its last tracked contents were recovered from Git blob
`b0043dca177daffb6bce8c05363efba617ce31d4`, before the root-cleanup commit removed
it from tracking. File SHA-256:
`f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f`.

This is the existing ten-record root reference file, not the separate 32-record
global research corpus or the differently shaped knowledge-base file. It remains
ignored and is not added to the change set. The restoration helper preserves
existing local files. The five fixture tests that originally errored now pass.

## Remaining release gates

- The 42,835-contract SQLite reference database was not located in the checkout
  or the available Git histories, including the two substantive remote development
  branches inspected. GitHub release-asset metadata could not be inspected because
  the API request returned Forbidden. No substitute database was manufactured.
- Both complete reference validators were therefore not run. No claim that the
  historical floor is preserved is made. Normalization and supplier-feature
  corrections can change rule activation even though thresholds are unchanged.
- Docker live tests were not run as part of this increment.
- Independent execution, security review, institutional acceptance, private-system
  integrations, and protection-sensitive disclosure workflows remain outside this
  validation.

See [the institutional review brief](INSTITUTIONAL_REVIEW.md) for reproduction,
interpretation limits, and the next pilot gates.
