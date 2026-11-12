# Task 7: measured reference protocols, November 12, 2026

Read the reference-input manifest and verifier, exact case restoration script,
institutional review protocol and both evaluator CLIs first. Verify both files
before each evaluator, preserve distinct fresh outputs, and verify both inputs
again after each run without changing any scoring rule or threshold.

## Corpus admission and source identity

The [committed location of record](REFERENCE_INPUTS.md) records both absolute
paths, SHA-256 hashes, byte sizes and the exact required verification command.
That record was committed and pushed as `40c5dd7` before either evaluator ran.
The database measured 169,349,120 bytes; the restored cases file measured 6,821
bytes. Both admission receipts and post-run receipts passed, so the original
input bytes remained unchanged. A read-only SQLite count measured 42,835 rows
in the contracts table.

Both evaluators ran on commit `40c5dd742e4e2e7d557a8247040e8b5905c8832c`,
CPython 3.12.14, with the exact 35 locked distributions. The saved receipts
include the source and environment fingerprints. The source remained frozen
while the two independent processes read the same verified files.

## Newly measured results

Both processes exited 0 on November 12, 2026, finishing at approximately
17:58:04 UTC (12:58 p.m. Eastern). Each used seed 42, 1,000 bootstrap iterations
and 200 comparison contracts. The general evaluator used `doj_federal`; the DOJ
validator has no profile argument. Nine synthesized positive examples and 200
presumed negatives were evaluated; one non-price reference was excluded.

| Measurement | General evaluator | DOJ validator |
|---|---:|---:|
| True positive | 9 | 9 |
| False negative | 0 | 0 |
| False positive | 18 | 18 |
| True negative | 182 | 182 |
| Precision | 33.33% | 33.33% |
| Recall | 100% | 100% |
| F1 | 50% | 50% |
| Specificity | 91% | 91% |
| False-positive rate | 9% | 9% from the measured matrix |
| PR-AUC | 0.7456 | Not reported |
| Flags per 1,000 evaluated records | 129.2 | Not reported |

The general evaluator's precision, recall and flag-volume gates all passed.
The DOJ validator's measured recall satisfies its 90% criterion. Neither CLI
used `--ci`, which redirects outputs into historical report paths; the saved
gate values and measured recall establish the result without overwriting them.
These are newly executed constructed-reference results, not field accuracy or
independently observed prosecutions. Configured analyst-time scenarios are not
reported as measured institutional savings.

## Published-report discrepancy

The new general metrics match `docs/evaluation_report.json`, the copy used by
the README. They differ from `reports/evaluation_report.json`, and the new DOJ
metrics differ from `reports/validation_report.json`. Those reports record the
same run settings. This is a real inconsistency among published artifacts; the
cause is not established by this run and must not be attributed to sampling
settings or a scoring regression without evidence. Historical values have not
been substituted for the new measurements or silently overwritten.

The authoritative new aggregate is
[the dated summary](../reports/reference-2026-11-12/summary.json), including
both execution receipts, input admissions, exact output digests and fresh
metrics. Full new JSON/Markdown outputs and logs remain under the chat workspace's
`outputs/task7/evaluation/`, `outputs/task7/doj/`, and `outputs/task7/`.

## Exact evaluator commands

Run the admission command in REFERENCE_INPUTS.md immediately before each.
The first process explicitly removed SUNLIGHT_DB_PATH from its environment;
otherwise that variable can override the supplied database path. Its shell
representation below includes the equivalent environment removal.

```bash
env -u SUNLIGHT_DB_PATH /Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/runtime-3.12.14/bin/python '/Users/rimodg/Documents/ChatGPT/Sunlight(the new SIGI)/code/evaluation.py' --db /Users/rimodg/brain/SUNLIGHT/data/sunlight.db --cases '/Users/rimodg/Documents/ChatGPT/Sunlight(the new SIGI)/prosecuted_cases.json' --seed 42 --bootstrap 1000 --clean 200 --profile doj_federal --out-dir /Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/outputs/task7/evaluation
```

```bash
/Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/runtime-3.12.14/bin/python '/Users/rimodg/Documents/ChatGPT/Sunlight(the new SIGI)/code/doj_validation.py' --db /Users/rimodg/brain/SUNLIGHT/data/sunlight.db --cases '/Users/rimodg/Documents/ChatGPT/Sunlight(the new SIGI)/prosecuted_cases.json' --seed 42 --bootstrap 1000 --clean 200 --out-json /Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/outputs/task7/doj/validation_report.json --out-md /Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/outputs/task7/doj/validation_report.md
```

## Backend and supplier verification

The full backend suite with SUNLIGHT_DB_PATH pointing to the verified database
measured **2,087 passed, 10 skipped, 0 failed**, 17 passing subtests in 18.43s.
All three previously skipped production-database invariance tests passed.
Remaining skips are nine unavailable live-Docker tests and one non-Mac-only
host test. Two dependency deprecation warnings remain.

The [supplier-only October recount](TASK5_IDENTITY_2026-11-12.md) and its
[aggregate artifact](../reports/reference-2026-11-12/october-supplier-summary.json)
separate supplier occurrences, distinct registry identifiers and nonjoinable
internal identifiers. No buyer identifiers or names were used as supplier joins.

## Task 6 remains open

The native verifier confirmed the original PID/build was still running. At the
pre-reboot snapshot the journal had 36 completed ticks and three source-failure
ticks, with subsequent recovery. Each source had six captures; admitted
occurrences totaled 490 for Contracts Finder and 54 for d-portal, with no record
refusals. These are repeated occurrences, not 544 distinct organizations.
The longest observed reach gap was approximately 46 minutes 11 seconds.
No completed full-day period or strict before/after change proof was claimed.

The explicit --after-reboot check still refused with
`Reboot after installation has not been demonstrated` and exit 2. The saved
pre-reboot boot epoch is 1794493394. Do not close Task 6 until a real reboot,
login and automatic scheduled completion produce a passing native receipt with
a later boot epoch and the live process's matching journal PID/build. A
launchctl restart or manual tick is not a reboot proof. Reinstallation would
reset the install boot baseline and must not be substituted for this check.

After the owner is ready to restart and has saved their work, reboot and log
in. Then run this from the immutable installed checkout, not the newer branch:

```bash
'/Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/sunlight-watch-service-5a224c8/scripts/watch-service' verify \
  --python '/Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/runtime-3.12.14/bin/python' \
  --data-dir '/Users/rimodg/Library/Application Support/SUNLIGHT/watch-live-sources-20261112' \
  --after-reboot
```

## EVAL-001 follow-up, November 12

The subsequent [history investigation](EVAL001_HISTORY_2026-11-12.md) identifies
the pre-April unseeded SQL sample selection and exactly reproduces the archived
general report from its stored sample on the verified corpus. Both reports/
copies are now marked stale with current measurements beside them. The DOJ
negative draw and original execution receipt remain unavailable, so that narrow
provenance gap is still open.
