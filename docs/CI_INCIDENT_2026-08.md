# CI Incident Diagnosis: Runner Refusal, August 2026

Status: ROOT CAUSE IDENTIFIED, FIX PENDING (account billing page, browser action)
Written: 2026-08-31, during live forensic session. All evidence read, not reasoned.

## Summary

Every GitHub Actions run on this repository since 2026-08-29 has failed in
3 to 5 seconds with jobs created but zero steps executed. The root cause is
not in this repository. GitHub's own job annotation states it verbatim
(job 99550823619, run 33411176502):

> "The job was not started because recent account payments have failed or
> your spending limit needs to be increased. Please check the
> 'Billing & plans' section in your settings"

A failed payment on the account owner's GitHub account has placed the
entire account's private-repository Actions into a blocked state. No job
is assigned a runner regardless of remaining free quota. The repository,
pushes, and releases are unaffected; only runner assignment is refused.

## Timeline of eras

- 2026-03 (commit 621ac52): original CI workflow added ("linting, tests,
  DOJ validation gate"). Targets ubuntu-latest.
- 2026-03 (commit aa84965): workflow revised in credibility-hardening pass.
  Still ubuntu-latest.
- Era 1, March through 2026-07-30: runs execute. The 2026-07-30 run
  (30515471673) lives 58 seconds and dies INSIDE the suite: the fixture's
  `docker compose` invocation hits `docker: command not found` in that
  runner context, and the workflow's `-x` flag halts the entire suite on
  first error. Genuine workflow-era defects, historical, superseded.
- Era 2, 2026-08-29 onward: every run dies in 3 to 5 seconds. Jobs are
  created (parse succeeded) with empty step arrays (no step, including
  checkout, ever starts). No job logs exist. This signature is refusal at
  runner assignment, before repository code is ever fetched.
- 2026-08-31 (commit 90d0243): workflow replaced wholesale, YAML validated
  locally, matrix py3.11 + py3.14, Docker tests isolated, determinism
  double-run proof. The clean replacement fails IDENTICALLY to the rotten
  original: definitive proof the cause is outside the workflow file.
- 2026-08-31: job annotation read. Root cause named by GitHub verbatim.

## Hypotheses tested and their dispositions

1. Workflow-file defect (rot, parse error). FALSIFIED for the current era:
   a locally-validated replacement failed identically. TRUE historically
   for Era 1 (docker-not-found plus -x halt). The replacement was needed
   regardless and stands.
2. Actions disabled or action allowlist. FALSIFIED by API read:
   enabled=true, allowed_actions=all.
3. Free-quota exhaustion by minutes. FALSIFIED: billing timing API reports
   0.0 billable minutes across 168 recorded runs, no hangs over 30
   minutes, no macOS minutes ever, and the fixture is bounded at 60s.
   NOTE: that same 0.0 reading for runs that demonstrably executed on
   hosted runners marks the per-run timing endpoint as unreliable on this
   account (billing-platform migration); it is not evidence in either
   direction and must not be reasoned from.
4. Ghost self-hosted runner (a registered runner that died). FALSIFIED:
   all three workflow generations target ubuntu-latest; no self-hosted
   label ever existed in runs-on history.
5. Account payment failure blocking runner assignment. CONFIRMED by the
   job annotation, verbatim above. Explains every observed fact: the
   empty-steps signature, identical failure of clean and rotten workflows,
   absence of job logs, and the era boundary at the payment failure date.

## Evidence ledger (all reads performed live)

- gh run list: 8 most recent runs, all failure; Era 1 run 58s, Era 2 runs
  3-5s.
- Jobs API for run 33411176502: total_count 4, all four jobs completed
  failure, steps arrays empty.
- Permissions API: enabled true, allowed_actions all, sha_pinning false.
- Timing API sweep: 168 runs on record, 9 since Aug 1, 16 in July,
  billable 0.0 throughout (endpoint deemed unreliable, see above).
- runs-on across 621ac52, aa84965, 90d0243: ubuntu-latest only.
- Check-run annotations for job 99550823619: the payment-failure message,
  verbatim in Summary.

## Fix (browser, two minutes, cannot be done from the terminal)

1. https://github.com/settings/billing/summary : read the banner, identify
   which recurring payment failed.
2. https://github.com/settings/billing/payment_information : update or
   re-add a valid payment method; settle any outstanding balance shown.
3. https://github.com/settings/billing/spending_limit : set the Actions
   spending limit to $0 deliberately. With a healthy payment method and a
   $0 limit, the free 2,000 included minutes work and jobs stop rather
   than bill beyond them. Overage becomes structurally impossible.

## Verification plan once unblocked

    git commit --allow-empty -m "ci: re-trigger after clearing account payment block"
    git push origin main
    gh run watch    # or: gh run list --limit 1 until completed

Expected: three jobs execute real steps. Green on all three establishes,
for the first time, (a) the suite passing on a machine that is not the
development machine, (b) on two interpreter versions (3.11, the
container's, and 3.14, the development machine's), and (c) run-to-run
byte-identical determinism of the DOJ calibration on foreign hardware.

## Permanent armor (applied in the same commit as this document)

- concurrency group with cancel-in-progress: superseded runs cancel
  instead of stacking.
- timeout-minutes on every job (suite 15, container 20, determinism 15):
  no future hang can consume hours of quota.
- Follow-up (CD-5): branch protection requiring the CI check on main, so
  a red default branch is surfaced immediately rather than discovered by
  archaeology. This incident ran unobserved for a month because nothing
  made the red X visible in the daily workflow.

## Lessons, recorded for the next reader

- Empty step arrays on a completed-failure job mean refusal BEFORE step
  one: the cause is never in the repository. Read annotations, not logs;
  refused jobs have no logs but do carry their reason as an annotation.
- The per-run billing timing endpoint cannot be trusted on accounts
  migrated to the new billing platform; the billing summary page is
  authoritative.
- A green CI badge is an institutional artifact. It must be load-bearing
  (branch protection) or it will silently rot, as it did here for a month.
