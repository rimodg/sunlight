import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_conflict_snapshot_preserves_source_time_window_and_precision_without_inventing_total_coverage():
    from watch_conflicts import SNAPSHOT as s
    assert s['version'] == 'Candidate 26.0.8' and s['preliminary'] is True
    assert s['record_count'] == len(s['events']) == 1500
    assert s['earliest_start'] == min(e['start'] for e in s['events']) == '2026-08-05'
    assert s['latest_start'] == max(e['start'] for e in s['events']) == '2026-08-31'
    assert s['latest_end'] == max(e['end'] for e in s['events']) == '2026-09-10'
    assert len({e['id'] for e in s['events']}) == len(s['events'])
    plotted = [e for e in s['events'] if e['location_precision'] in (1,2)]
    assert s['plottable_count'] == len(plotted) == 1018
    assert s['omitted_location_count'] == 482
    assert s['location_count'] == len({tuple(e['coordinates']) for e in plotted}) == 658
    assert all(e['start'].startswith('2026') and 1 <= e['type'] <= 3 for e in s['events'])
    assert 'Capped' in s['coverage'] and 'not a live alert' in s['dates']
    assert not any('source_article' in e or 'best' in e for e in s['events'])


def test_conflict_build_rejects_a_changed_public_mirror(tmp_path):
    spec = importlib.util.spec_from_file_location('conflict_builder', ROOT/'scripts/build_conflict_snapshot.py')
    builder = importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    source = tmp_path/'source.json';source.write_text('{}')
    with pytest.raises(ValueError, match='checksum mismatch'):
        builder.build(source)


def test_conflict_endpoint_is_bundled_and_discloses_reporting_area_caveats():
    from fastapi.testclient import TestClient
    from api import app
    result = TestClient(app).get('/watch-data/conflicts')
    assert result.status_code == 200
    snapshot = result.json()
    assert snapshot['record_count'] == 1500
    assert snapshot['mirror_revision'] in snapshot['source_file']['url']
    assert len(snapshot['source_file']['sha256']) == 64
    assert 'Gaza' in snapshot['reporting_areas']
    assert 'No conflict variable enters' in snapshot['interpretation']
