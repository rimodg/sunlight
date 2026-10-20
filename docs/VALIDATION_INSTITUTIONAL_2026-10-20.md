# Institutional workflow validation — 20 October 2026

The update implements the decision-workflow changes described in
[the institutional instrument assessment](INSTITUTIONAL_INSTRUMENT.md).

## Automated checks

- Full backend suite: **2,116 passed, 3 skipped**. Docker live tests excluded.
- Frontend suite: **48 passed**.
- Production Vite build: passed, using `/watch/` as the base.
- `git diff --check`: passed.
- Existing Starlette TestClient deprecation and bundle-size advisory remain.

The ten new queue checks cover deployment scope; exclusion/isolation of synthetic
examples; absence of invented loss from missing evidence or budgets; priorities
based on comparable measurements; no ranking by country or budget magnitude;
assignment and overdue states; unchanged source conditions after administrative
review completion; current source revision selection; complete scoped assessment
before pagination; task filters; current/stale calibrated acceptance basis;
readable report escaping; engine error handling; and preservation of an engine
recommendation when reported quantities match.

Existing ledger calculations, calibrated detection thresholds and transfer
identity rules are reused. No new statistical risk model is introduced.

Commands used:

```sh
/workspace/.venvs/sunlight/bin/python -m pytest -q --ignore=tests/test_docker_live.py
npm --prefix sunlight-dashboard test
npm --prefix sunlight-dashboard run build -- --base=/watch/
git diff --check
```

## Browser journeys

Chromium/Playwright ran against isolated local APIs and SQLite ledgers. These were
synthetic validation records, not actual institutional financial or field data.

The new retained browser script,
`sunlight-dashboard/scripts/smoke-review-queue.cjs`, passed:

1. Register two obligations and two source cases through the real APIs.
2. Display the exact USD 40 settled claim residual and the proper source scope.
3. Assign an evidence follow-up with owner/deadline; simulate a concurrent
   evidence revision, reject the old version and retain the draft; explicitly
   refresh its record version before saving successfully.
4. Open a scope-labelled review meeting brief and inspect its next evidence.
5. Open the exact obligation from the queue, then a second obligation while the
   same delivery desk remains mounted.
6. Open a specific source case and inspect the attached procurement decision
   basis. Retain an unsaved owner/note when another case is requested. Explicitly
   discard the draft before opening the requested case.
7. Reload the working case URL and retain the exact selected case.
8. Filter treasury work, focus Ghana without dismissing the queue, retain the
   same globe canvas across tools, and verify mobile layout without horizontal
   overflow. No page errors were recorded.

The existing world workbench, monetary atlas and delivery-assurance browser
regressions also passed. Those checks cover source tracing and readable briefs,
saved scoped inquiries, the 27-measure country profile, unavailable source years,
aid direction, guided registration, exact financial/acceptance comparisons,
calibrated delivery execution, follow-up completion evidence, retained corrections,
concurrent-review handling, reload, reduced motion and mobile presentation.

The world regression recorded approximately 51.7 frames/second and 33.3 ms p95
frame intervals in this execution environment, with zero SVG mutations during
rotation. These are environment-specific samples, not a guarantee for user
hardware or a measure of live economic movement.

Screenshots: [review queue](interface/Institutional-Review-Queue.png) and
[mobile review](interface/Institutional-Review-Mobile.png). They show isolated
validation data and scope-labelled work, not observed institutional programmes.

## Limits of these results

These checks demonstrate software behavior. They do not establish corruption
accuracy, independent issuer verification, real bank/treasury ingestion, a hosted
persistent volume, tenant permissions, authorised intervention, institutional
approval or a measured institutional pilot benefit. The adoption assessment
separates those requirements from implemented features.

The queue uses one SQLite read snapshot and assesses all scoped registered records
before pagination. Institution-scale ingestion, materialised work queues,
concurrent writer performance and multi-replica deployment remain separate
engineering work. The readable meeting brief explicitly discloses its 500-record
display cap; full source dossiers and historical revisions remain in the ledger.

A successful Git branch push can trigger Render auto-deploy. Remote Render build
completion and hosted rollout are not verified by these local checks. No paid
hosting setting, external institutional record or external notification was changed.
