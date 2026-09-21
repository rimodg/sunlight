"""
Claims ledger gate: every number in README.md must be accounted for in CLAIMS.md,
and everything CLAIMS.md points at must exist.

WHAT THIS ENFORCES
    1. Every distinct numeric token in README.md appears in the Number column of
       at least one CLAIMS.md row. A new number in the README with no ledger row
       fails the suite.
    2. Every ledger Number still appears in README.md (no stale rows).
    3. Every `tests/<file>.py::<Class>::<test>` or `tests/<file>.py::<test>`
       reference anywhere in a ledger row resolves to a real test function.
    4. Every `artifact:<path>` reference resolves to a file in the repo.
    5. Every `code:<path>::<symbol>` reference resolves to a file containing
       that symbol text.
    6. Status is one of BACKED / UNBACKED / NOT-A-CLAIM. BACKED rows must cite
       at least one test or artifact. UNBACKED and NOT-A-CLAIM rows must not.

WHAT THIS DOES NOT ENFORCE
    That the ledger's *reading* of a claim is complete. A number can appear in
    the README with two meanings; the ledger lists both, but only a human can
    say whether every meaning was found. The ledger is a screen, not an oracle.

The second class, TestReadmeNumbersMatchArtifactsAndCode, holds the small
assertions that turn "recorded in an artifact" or "defined in code" into a
test the ledger can cite: the evaluation report's metrics, the corpus size,
enum sizes, rule-id counts, the batch limit. Where the measured value differs
from the README, the test asserts the MEASURED value and the ledger row says
UNBACKED; the README is Rim's to change, not this suite's.
"""
import ast
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
README_PATH = os.path.join(REPO_ROOT, 'README.md')
LEDGER_PATH = os.path.join(REPO_ROOT, 'CLAIMS.md')

VALID_STATUSES = {'BACKED', 'UNBACKED', 'NOT-A-CLAIM'}

# A numeric token: comma-grouped integers, decimals, optional trailing percent.
# Lookarounds keep identifiers like "v0.1" or "3.14" inside words out, but let
# ranges such as "1-8" yield both ends.
_NUMBER_RE = re.compile(r'(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(%?)(?![\w])')
_TEST_REF_RE = re.compile(r'tests/[A-Za-z0-9_]+\.py::[A-Za-z0-9_:\[\]\-]+')
_ARTIFACT_REF_RE = re.compile(r'artifact:([A-Za-z0-9_./\-]+)')
_CODE_REF_RE = re.compile(r'code:([A-Za-z0-9_./\-]+)::([A-Za-z0-9_."\'<>=() ]+?)(?=[;|]|$)')


def extract_readme_numbers(text=None):
    """Distinct numeric tokens in the README, as written (e.g. '33.3%', '42,835').

    Leading-zero tokens ('001' from the rule id TIME-001) are identifier
    fragments, not numbers, and are skipped.
    """
    text = open(README_PATH, encoding='utf-8').read() if text is None else text
    tokens = set()
    for m in _NUMBER_RE.finditer(text):
        tok = m.group(1) + m.group(2)
        if re.match(r'^0\d', tok):
            continue
        tokens.add(tok)
    return tokens


def parse_ledger(text=None):
    """Rows of the first markdown table in CLAIMS.md whose header has 'Number'."""
    text = open(LEDGER_PATH, encoding='utf-8').read() if text is None else text
    lines = text.splitlines()
    header = None
    rows = []
    for line in lines:
        if not line.strip().startswith('|'):
            if header is not None and rows:
                break  # table ended
            continue
        cells = [c.strip().strip('`').strip() for c in line.strip().strip('|').split('|')]
        if header is None:
            if 'Number' in cells:
                header = cells
            continue
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
            continue  # separator row
        if len(cells) != len(header):
            raise AssertionError(f"CLAIMS.md row has {len(cells)} cells, header has {len(header)}: {line!r}")
        rows.append(dict(zip(header, cells)))
    assert header is not None, "CLAIMS.md has no table with a 'Number' column"
    return rows


def _test_function_exists(ref):
    """tests/file.py::Class::name or tests/file.py::name -> bool."""
    parts = ref.split('::')
    path = os.path.join(REPO_ROOT, parts[0])
    if not os.path.exists(path):
        return False, f"file missing: {parts[0]}"
    tree = ast.parse(open(path, encoding='utf-8').read())
    names = [re.sub(r'\[.*\]$', '', p) for p in parts[1:]]  # drop parametrize ids
    if len(names) == 1:
        found = any(isinstance(n, ast.FunctionDef) and n.name == names[0] for n in tree.body)
        return found, f"module-level test not found: {names[0]}"
    if len(names) == 2:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == names[0]:
                found = any(isinstance(f, ast.FunctionDef) and f.name == names[1] for f in node.body)
                return found, f"test not found in class {names[0]}: {names[1]}"
        return False, f"class not found: {names[0]}"
    return False, f"unsupported reference shape: {ref}"


class TestClaimsLedgerCoverage:

    def test_ledger_parses_and_has_rows(self):
        rows = parse_ledger()
        assert len(rows) >= 10
        for col in ('Number', 'Claim', 'Backing', 'Status'):
            assert col in rows[0], f"CLAIMS.md table lacks column {col}"

    def test_every_readme_number_is_in_ledger(self):
        readme = extract_readme_numbers()
        ledger = {r['Number'] for r in parse_ledger()}
        missing = sorted(readme - ledger, key=lambda t: (len(t), t))
        assert not missing, (
            f"README.md numbers with no CLAIMS.md row: {missing}. "
            f"Add a row for each (BACKED with its test/artifact, or UNBACKED)."
        )

    def test_every_ledger_number_is_in_readme(self):
        readme = extract_readme_numbers()
        stale = sorted({r['Number'] for r in parse_ledger()} - readme)
        assert not stale, f"CLAIMS.md rows whose Number no longer appears in README.md: {stale}"

    def test_every_referenced_test_exists(self):
        problems = []
        for r in parse_ledger():
            for ref in _TEST_REF_RE.findall(' '.join(r.values())):
                ok, why = _test_function_exists(ref)
                if not ok:
                    problems.append(f"row {r.get('#')} ({r['Number']}): {ref} -> {why}")
        assert not problems, "\n".join(problems)

    def test_every_referenced_artifact_exists(self):
        problems = []
        for r in parse_ledger():
            for path in _ARTIFACT_REF_RE.findall(' '.join(r.values())):
                if not os.path.exists(os.path.join(REPO_ROOT, path)):
                    problems.append(f"row {r.get('#')} ({r['Number']}): artifact missing: {path}")
        assert not problems, "\n".join(problems)

    def test_every_referenced_code_symbol_exists(self):
        problems = []
        for r in parse_ledger():
            for path, symbol in _CODE_REF_RE.findall(r['Backing'] + ';' + r.get('Note', '')):
                full = os.path.join(REPO_ROOT, path)
                if not os.path.exists(full):
                    problems.append(f"row {r.get('#')}: code file missing: {path}")
                elif symbol.strip() not in open(full, encoding='utf-8').read():
                    problems.append(f"row {r.get('#')}: symbol {symbol.strip()!r} not in {path}")
        assert not problems, "\n".join(problems)

    def test_status_values_are_valid_and_consistent(self):
        problems = []
        for r in parse_ledger():
            status = r['Status']
            backing = r['Backing']
            has_test_or_artifact = bool(_TEST_REF_RE.search(backing) or _ARTIFACT_REF_RE.search(backing))
            if status not in VALID_STATUSES:
                problems.append(f"row {r.get('#')}: bad status {status!r}")
            elif status == 'BACKED' and not has_test_or_artifact:
                problems.append(f"row {r.get('#')} ({r['Number']}): BACKED but Backing cites no test or artifact")
            elif status != 'BACKED' and has_test_or_artifact:
                problems.append(f"row {r.get('#')} ({r['Number']}): {status} but Backing cites a test/artifact; "
                                f"put measurement references in Note, or mark BACKED")
        assert not problems, "\n".join(problems)

    def test_unbacked_rows_are_listed_in_the_summary_section(self):
        """The UNBACKED list at the top of CLAIMS.md must match the table."""
        text = open(LEDGER_PATH, encoding='utf-8').read()
        table_unbacked = {r['#'] for r in parse_ledger() if r['Status'] == 'UNBACKED'}
        m = re.search(r'UNBACKED rows:\**\s*([0-9,\s]+)', text)
        assert m, "CLAIMS.md needs a line 'UNBACKED rows: <comma-separated row numbers>'"
        listed = {x.strip() for x in m.group(1).split(',') if x.strip()}
        assert listed == table_unbacked, f"summary lists {sorted(listed)} but table has {sorted(table_unbacked)}"


@pytest.fixture(scope='module')
def evaluation_report():
    return json.load(open(os.path.join(REPO_ROOT, 'docs', 'evaluation_report.json')))


class TestReadmeNumbersMatchArtifactsAndCode:
    """Backing tests the ledger cites. Each asserts a MEASURED value."""

    def test_evaluation_artifact_metrics_match_readme(self, evaluation_report):
        """README table: 33.3% / 100% / 9.0% / 0.746 / 129.2 per 1,000 — as recorded 2026-06-11."""
        m = evaluation_report['classification_metrics']
        assert m['precision'] == pytest.approx(0.3333, abs=5e-5)
        assert m['recall'] == 1.0
        assert m['false_positive_rate'] == pytest.approx(0.090, abs=5e-4)
        assert evaluation_report['pr_curve']['pr_auc'] == pytest.approx(0.746, abs=5e-4)
        assert evaluation_report['review_workload']['flags_per_1000_contracts'] == pytest.approx(129.2, abs=0.05)
        assert evaluation_report['evaluation_date'].startswith('2026-06-11')

    def test_evaluation_artifact_scored_nine_positives_not_thirty_two(self, evaluation_report):
        """The recorded 100% recall is over 9 US DOJ price-fraud cases, not 32."""
        comp = evaluation_report['dataset_composition']
        assert comp['positives'] == 9
        assert comp['negatives'] == 200
        assert comp['excluded'] == 1

    def test_evaluation_artifact_records_seed_and_clean_count(self, evaluation_report):
        cfg = evaluation_report['evaluation_config']
        assert cfg['run_seed'] == 42
        assert cfg['n_clean_contracts'] == 200
        assert cfg['calibration_profile'] == 'doj_federal'
        assert cfg['n_bootstrap_iterations'] == 1000

    def test_corpus_has_32_cases_in_4_jurisdictions(self):
        corpus = json.load(open(os.path.join(REPO_ROOT, 'research', 'corpus', 'prosecuted_cases_global_v0.1.json')))
        cases = corpus['cases']
        assert len(cases) == 32
        assert {c['jurisdiction'] for c in cases} == {'US_DOJ', 'UK_SFO', 'FR_PNF', 'WB_INT'}

    def test_pipeline_stage_count_is_measured(self):
        """README says '16-stage pipeline'. The PipelineStage enum has 12 members."""
        from sunlight_core import PipelineStage
        assert len(PipelineStage) == 12

    def test_tca_rule_id_count_is_measured(self):
        """README says '16 rules across 5 layers (procurement 5, entity 3, financial 3,
        temporal 3, network 2)'. Rule ids in code/: 14 across 4 prefixes, no NET ids."""
        src = open(os.path.join(REPO_ROOT, 'code', 'tca_rules.py'), encoding='utf-8').read()
        ids = set(re.findall(r'"((?:PROC|ENT|FIN|TIME|NET)-\d{3})"', src))
        by_prefix = {p: sum(1 for i in ids if i.startswith(p + '-')) for p in ('PROC', 'ENT', 'FIN', 'TIME', 'NET')}
        assert by_prefix == {'PROC': 5, 'ENT': 3, 'FIN': 3, 'TIME': 3, 'NET': 0}
        assert len(ids) == 14

    def test_delivery_rule_ids_are_12_across_4_layers(self):
        src = open(os.path.join(REPO_ROOT, 'code', 'delivery_rules.py'), encoding='utf-8').read()
        ids = set(re.findall(r'rule_id="(DEL-[A-Z]+-\d{3})"', src))
        layers = {i.split('-')[1] for i in ids}
        assert len(ids) == 12
        assert len(layers) == 4

    def test_batch_endpoint_rejects_1001_contracts(self):
        """README: 'Batch analysis, up to 1,000 contracts per request'."""
        os.environ.setdefault('SUNLIGHT_AUTH_ENABLED', 'false')
        from fastapi.testclient import TestClient
        from api import app
        client = TestClient(app)
        ok = client.post('/batch', json={'contracts': [{'ocid': f'ocds-ledger-{i}'} for i in range(2)]})
        too_many = client.post('/batch', json={'contracts': [{'ocid': f'ocds-ledger-{i}'} for i in range(1001)]})
        assert ok.status_code == 200
        assert too_many.status_code == 413

    def test_api_registers_two_of_the_four_readme_profiles(self):
        """README's profile table lists four; the API registry carries two.
        Not a numeric token in the README, recorded here so it is a checked fact."""
        os.environ.setdefault('SUNLIGHT_AUTH_ENABLED', 'false')
        from fastapi.testclient import TestClient
        from api import app
        names = {p['name'] for p in TestClient(app).get('/profiles').json()['profiles']}
        assert names == {'us_federal', 'uk_central_government'}
