# Task 1: checkout and runtime verification, 2026-11-10

## Read first and design

Read the owner's code-gap work order and runtime follow-up, requirements.lock,
requirements.txt, the CI workflow, service runtime verifier, reference fixture
restoration script, pytest configuration and native service tests. Use the
requested exact interpreter if updated uv can install it, and preserve a clean
35-package service environment. Run the backend suites in a separate environment
with the same runtime pins plus pytest, with main in a detached worktree.

## Changes and interpreter decision

The registered empty local repository now has origin at rimodg/sunlight.
`watch-live-sources` was created from exactly
`9e692dd4d387a62b9898bdacd43ed49043e48323`.

The original uv 0.9.18 could not find CPython 3.12.14. `uv self update`
installed uv 0.13.7 (316c827e0, 2026-11-03, aarch64-apple-darwin), and
`uv python install 3.12.14` then succeeded:

```text
Installed Python 3.12.14 in 2.69s
 + cpython-3.12.14-macos-aarch64-none (python3.12)
```

The existing installer pin, runtime verification code and requirements.lock
remain unchanged, as the owner explicitly requested for successful installation.
RUNTIME-001 records the accepted future rule: pin the minor version, verify the
selected patch at each start, never require one patch as installation policy.
The policy defect remains open despite today's successful installation.

Provisioning commands below use UV for the installed uv executable, RUNTIME for
the external service environment and TEST_RUNTIME for the separate test one:

```sh
"$UV" venv --python 3.12.14 "$RUNTIME"
"$UV" pip install --python "$RUNTIME/bin/python" --no-deps --only-binary=:all: -r requirements.lock
"$UV" pip check --python "$RUNTIME/bin/python"
"$UV" venv --python 3.12.14 "$TEST_RUNTIME"
"$UV" pip install --python "$TEST_RUNTIME/bin/python" --no-deps --only-binary=:all: -r requirements.lock
"$UV" pip install --python "$TEST_RUNTIME/bin/python" pytest
```

All 35 pins installed. Dependency checking reported all installed packages
compatible. The actual service verifier, `watch_service.pinned(python,
environment=RUNTIME)`, accepted Python 3.12.14 and exactly 35 installed packages.
Its output was retained as runtime-verification.json. This is a runtime probe,
not a service installation receipt: no LaunchAgent was installed.

The separate test environment retained all 35 exact runtime pins and added only
pytest 9.2.0, iniconfig 2.3.1, packaging 26.3, pluggy 1.7.0 and pygments 2.21.0.

## Push proof

The first commit, c2ba06a2833781e4ff91cbc264fac0de34d13088, records the defect.
It was immediately pushed to origin/watch-live-sources before reporting.

An additional branch with no new commits was pushed for the explicit proof:

```sh
git push origin 9e692dd4d387a62b9898bdacd43ed49043e48323:refs/heads/watch-push-proof-20261110
git ls-remote --exit-code --heads origin refs/heads/watch-push-proof-20261110
git push origin --delete watch-push-proof-20261110
git ls-remote --heads origin refs/heads/watch-push-proof-20261110
```

Creation succeeded, the first lookup returned the exact requested SHA, deletion
succeeded, and the final lookup returned no ref. No push to main occurred.

## Backend results

Both runs completed on 2026-11-10 using CPython 3.12.14 on macOS arm64.
The command in each checkout was:

```sh
"$TEST_RUNTIME/bin/python" -m pytest tests/ -q -ra --junitxml="$OUTPUT/<branch>-tests.xml"
```

Complete stdout and stderr were retained in separate logs.

| Checkout | Source commit | Passed | Skipped | Failed | Exit | Duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| main, detached | bd9ebef9c90f32ec097679ee24bc38317ad67fc6 | 1989 | 12 | 0 | 0 | 19.37s |
| watch-live-sources, rebuild code unchanged | c2ba06a2833781e4ff91cbc264fac0de34d13088 | 2054 | 13 | 2 | 1 | 21.40s |

The rebuild also reported 17 passing subtests, separately from the 2054 count.
Both runs emitted two dependency deprecation warnings.

Skipped on both branches: nine live Docker tests because the daemon was
unavailable, and three production-database invariance tests because the database
was absent. The rebuild additionally skipped the non-Mac-host refusal test
because this host is a Mac. No Docker or reference-floor acceptance is claimed.

The two rebuild failures are recorded as RUNTIME-002: unresolved `/var/...`
test expectations differ from the installer's resolved `/private/var/...`
paths. The implementation and assertions were left intact. Task 1 has executed
its requested checks but the rebuild's green-suite gate is not closed.

The cases fixture was restored byte for byte in both checkouts from Git blob
b0043dca177daffb6bce8c05363efba617ce31d4 and verified against SHA-256
f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f.
It was not reconstructed. The reference database remains a separate missing
input; neither reference evaluator was run.

## Evidence identities

Full logs, JUnit XML and environment receipts are retained in the local audit
output directory, not embedded here with machine-specific paths. SHA-256:

```text
main-tests.log 4dbff6c8e26550684672fc68a26b0a69bfd165db0e7f2b18b263db412d83d413
main-tests.xml 24568a1ab111a2e4a858e1a55175492642de7e5d9d0a2a791980d1bdea282629
rebuild-tests.log 6e59037c2c4134e8f55746848d685adf40bc4a8283889bb30ef13e7e20894a81
rebuild-tests.xml 96a3a704ed43aea9ed92fc75e161bc1e1314f8d3523c6c80e4a37cfa56e7c199
runtime-verification.json 61772e3d27f0f61aa1ddcda5a44ae1ed2521fbee0ab19c5d89eecd24a5152a02
test-packages.json b4f3baeafc16e3183ff0e3ac078f1ba39dcacfac34119272ebbdb46b9fc6886a
```

Stop at this checkpoint as instructed. Task 2 has not started, the service is
not installed, and no payment, law, human-layer or deployed Render change was made.

## RUNTIME-002 follow-up, November 10, 2026

At the owner's direction, both sides of path comparisons now use Path.resolve().
The stderr-path assertion checks the exact resolved file, and the failed-install
test still checks membership in the created-path list after resolving both sides.
Production path protection and installer logic are unchanged.

The same complete backend command, after the fix, returned:

```text
2056 passed, 13 skipped, 2 warnings, 17 subtests passed in 17.63s
```

Exit code 0. The skipped tests have the same reasons as the earlier run; this
does not close the Docker, database or native service gates. The initial failed
run remains above as history. The local output directory also retains
rebuild-fixed-tests.log and rebuild-fixed-tests.xml for this follow-up.
The README now distinguishes main's 1989 passing tests from this rebuild's
2056 passing tests and records the date. See the README figure audit for the
remaining numerical claims and their evidence limits.
