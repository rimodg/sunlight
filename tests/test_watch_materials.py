import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_material_values_reconcile_without_adding_imports_or_overlapping_codes():
    from watch_materials import SNAPSHOT as s
    assert s['year'] == 2023 and s['release'] == 'BACI_HS17_V202601'
    assert s['total_usd'] == 3_951_738_847_968 == sum(r[2] for r in s['rows'])
    assert s['country_count'] == 223 == len({r[0] for r in s['rows'] if r[2] > 0})
    assert len(s['products']) == len({p['code'] for p in s['products']}) == 85
    assert len(s['rows']) == len({(r[0],r[1]) for r in s['rows']})
    countries = {c['alpha3'] for c in json.loads((ROOT/'sunlight-dashboard/src/data/countries.json').read_text())}
    assert all(r[0] in countries for r in s['rows'])
    # Major African contributions remain present regardless of procurement coverage.
    assert sum(r[2] for r in s['rows'] if r[0] == 'GHA') == 23_231_917_535
    assert next(r[2] for r in s['rows'] if r[:2] == ['COD','7403']) == 12_405_086_225
    assert sum(r[2] for r in s['rows']) != sum(r[2]+r[3] for r in s['rows'])


def test_partner_share_denominators_and_directions_match_national_product_values():
    from watch_materials import SNAPSHOT as s
    totals = {(r[0],r[1]):r[2:] for r in s['rows']}
    assert len({r[0] for r in s['routes']}) == 204
    for exporter, importer, product, share, direction, base in s['routes']:
        assert exporter != importer
        assert 1 <= share <= 10000
        assert base == totals[(exporter if direction == 1 else importer,product)][0 if direction == 1 else 1]
        assert base >= 1_000_000
    assert 'bilateral dollar value' in s['route_precision']


def test_all_source_files_are_pinned_to_reviewed_checksums():
    from watch_materials import SNAPSHOT as s
    pins = json.loads((ROOT/'scripts/materials_source_checksums.json').read_text())
    assert {f['name']:f['sha256'] for f in s['source_files']} == pins
    assert all(s['source_revision'] in f['url'] for f in s['source_files'])


def test_material_build_rejects_modified_source(tmp_path):
    spec = importlib.util.spec_from_file_location('materials_builder',ROOT/'scripts/build_materials_snapshot.py')
    builder = importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    (tmp_path/'manifest.json').write_text('{}')
    with pytest.raises(ValueError,match='checksum mismatch'):
        builder.build(tmp_path)


def test_bundled_materials_endpoint_needs_no_external_feed():
    from fastapi.testclient import TestClient
    from api import app
    response = TestClient(app).get('/watch-data/materials')
    assert response.status_code == 200
    assert response.json()['total_usd'] == 3_951_738_847_968
