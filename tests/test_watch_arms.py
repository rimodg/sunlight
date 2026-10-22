import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_arms_context_preserves_reporter_direction_quantities_and_duplicate_uncertainty():
    from watch_arms import SNAPSHOT as s
    assert s['normalized_rows'] == len(s['rows']) == 6832
    assert len({r['id'] for r in s['rows']}) == 6832
    assert sum(r['duplicate_count'] > 1 for r in s['rows']) == s['duplicate_groups'] == 121
    assert sum(r['quantity'] is None for r in s['rows']) == s['missing_quantities'] == 57
    assert s['source_transfer_rows'] == sum(r['duplicate_count'] for r in s['rows']) == 6953
    for r in s['rows']:
        assert r['year'] in (2020, 2021, 2022)
        assert r['reporter'] == r['exporter' if r['direction'] == 'export' else 'importer']
        assert r['quantity'] is None or (isinstance(r['quantity'], int) and r['quantity'] >= 0)
        assert r['source_url'].startswith('https://www.unroca.org/')
    assert 'not calculable' in s['gap_limit']
    assert all(e['coordinates'] is None and e['matched_declaration_ids'] == [] for e in s['field_evidence'])
    assert all('Full report' in e['verification'] for e in s['field_evidence'])


def test_arms_builder_rejects_modified_source(tmp_path):
    spec = importlib.util.spec_from_file_location('arms_builder', ROOT/'scripts/build_arms_snapshot.py')
    builder = importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    (tmp_path/'unroca.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum mismatch'):
        builder.build(tmp_path)


def test_arms_endpoint_is_bundled_and_does_not_claim_live_or_ground_reconciliation():
    from fastapi.testclient import TestClient
    from api import app
    response = TestClient(app).get('/watch-data/arms')
    assert response.status_code == 200
    s = response.json()
    assert s['default_year'] == 2022
    assert len(s['source_files']) == 3
    assert all(len(f['sha256']) == 64 and s['source_revision'] in f['url'] for f in s['source_files'])
    assert 'not current shipment locations' in s['geography']
    assert len(s['field_evidence']) == 2
    assert len(s['audit_provenance']['source_file']['sha256']) == 64
