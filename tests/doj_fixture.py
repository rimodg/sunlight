"""
DOJ reference-case fixture: location, pinned digest, fail-closed loader.

Shared by tests/conftest.py (the doj_cases fixture), tests/test_doj_calibration.py
(the integrity test) and tests/test_doj_blind_e2e.py (the engine gate), so all
three fail the same way from the same check.

History: the 10-case file lived at the repo root until commit 3866a49
(2026-06-12) untracked it as a "development artifact". From then until
2026-09-21 the DOJ case tests ERRORED on every clean clone and CI never passed.
"""
import hashlib
import os

import pytest

DOJ_CASES_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'prosecuted_cases.json')
DOJ_CASES_SHA256 = 'f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f'
DOJ_CASES_EXPECTED_COUNT = 10


def verify_doj_cases_file() -> bytes:
    """Return the raw bytes of the DOJ fixture, or pytest.fail() with a reason.

    Missing file and altered file are both hard failures. There is no skip
    path and no fallback source.
    """
    if not os.path.exists(DOJ_CASES_PATH):
        pytest.fail(
            f"DOJ fixture missing: {DOJ_CASES_PATH}. The recall gate cannot run "
            f"without it. Restore with: git show 3866a49~1:prosecuted_cases.json "
            f"> tests/fixtures/prosecuted_cases.json"
        )
    raw = open(DOJ_CASES_PATH, 'rb').read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != DOJ_CASES_SHA256:
        pytest.fail(
            f"DOJ fixture altered: sha256 {digest} != pinned {DOJ_CASES_SHA256}. "
            f"Changing the reference cases changes the recall claim; update the "
            f"pin deliberately in tests/doj_fixture.py and CLAIMS.md together."
        )
    return raw
