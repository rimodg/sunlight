# Build identity without Git in the runtime image

`GET /version` retains its existing fields and adds `git_commit` and `build`.
The API captures identity once at process startup. Requests cannot relabel a
running process by reading a later Git HEAD or an environment variable.

The image build writes `/app/build_identity.json` after copying application
code, calibration data, dependency declarations and the compiled dashboard.
The file includes a canonical manifest of the actual packaged source hashes,
an environment fingerprint and, when supplied, the full Git revision.
Git metadata does not need to be copied into the image.

Pass the full revision with Docker's `SUNLIGHT_BUILD_COMMIT` build argument.
The generator also accepts a declared `RENDER_GIT_COMMIT` build argument when
the platform supplies it. Conflicting or shortened revision inputs are refused.

```bash
docker build --build-arg SUNLIGHT_BUILD_COMMIT=FULL_GIT_REVISION -t sunlight .
```

The placeholder must be replaced with the checkout's actual full revision.
With no Git metadata and no declared revision, the result is still identifiable
by its actual source SHA-256. `git_commit` remains null and the version label
uses `src.` plus the source fingerprint. No commit is invented.

At startup the API compares the manifest with the packaged files and installed
environment. Missing/changed files, manifest corruption or environment drift
refuse startup. A valid content match reports `state: packaged_files_match`.
A declared revision reports `git_commit_basis: declared_build_input`; that is
an explicit distinction from a locally observed Git HEAD.

For a source checkout without a packaged manifest, the API fingerprints the
working tree and reports its observed Git revision and dirty state. A dirty
checkout is not represented as a clean revision. Restart after changing code.

The digest is not a publisher signature, supply-chain attestation, institutional
approval or proof that an externally declared revision is authentic. It makes
the build's actual content and attribution basis inspectable.

An offline packaging simulation and endpoint tests run with:

```bash
SUNLIGHT_OFFLINE=1 python -m unittest discover -s tests -p 'test_build_identity.py' -v
```

Actual Docker verification requires locally available base images or an
authorized build environment. No image pull or package request is implied by
the offline test command.
