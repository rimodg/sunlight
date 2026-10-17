import asyncio
import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('snapshot_builder', ROOT / 'scripts/build_public_procurement_snapshot.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_published_snapshot_has_reconciled_years_not_repeated_indicators():
    from watch_procurement import SNAPSHOT
    assert SNAPSHOT['country_count'] == 59
    assert len(SNAPSHOT['rows']) == 447
    assert all(row['code'] not in {'EU', 'UK'} for row in SNAPSHOT['rows'])
    for annual in SNAPSHOT['annual']:
        rows = [r for r in SNAPSHOT['rows'] if r['year'] == annual['year']]
        assert len({r['code'] for r in rows}) == annual['countries'] == len(rows)
        assert sum(r['contracts'] for r in rows) == annual['contracts']
        assert sum(r['usd'] for r in rows) == annual['usd']
    latest = SNAPSHOT['annual'][0]
    assert latest == {'year': 2024, 'countries': 52, 'contracts': 10617058, 'usd': 4301531960000}
    assert len(SNAPSHOT['source_files']) == 2
    assert all(len(s['sha256']) == 64 and SNAPSHOT['source_revision'] in s['url'] for s in SNAPSHOT['source_files'])


def test_indicator_duplicates_and_regions_do_not_multiply_contracts(tmp_path):
    path = tmp_path / 'source.csv'
    fields = ['Country', 'Country_code_ISO_2', 'Year', 'Contract_value', 'All_contracts(Country-Year-Contract_value_group)', 'Total_contract_value_million_usd(Country-Year-Contract_value_group)']
    def row(code='UK', count='10', amount='1.23'):
        return dict(zip(fields, ['United Kingdom', code, '2024', 'ALL', count, amount]))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        writer.writerows([row(), row(), row('EU', '999', '999')])
    values, _, excluded = builder.unique_rows(path)
    assert values == {('GB', 2024): (10, 1230000)}
    assert excluded == {'EU'}
    with path.open('a', newline='') as stream:
        csv.DictWriter(stream, fieldnames=fields).writerow(row(count='11'))
    with pytest.raises(ValueError, match='Conflicting'):
        builder.unique_rows(path)


def test_snapshot_pins_are_enforced_before_build(tmp_path):
    (tmp_path / 'tab_1.csv').write_text('changed source')
    with pytest.raises(ValueError, match='checksum'):
        builder.build(tmp_path)


def test_source_endpoint_returns_bundle_without_external_network():
    from fastapi.testclient import TestClient
    from api import app
    result = TestClient(app).get('/watch-data/procurement')
    assert result.status_code == 200
    assert result.json()['status'] == 'bundled_snapshot'
    assert result.json()['annual'][0]['contracts'] == 10617058


def test_each_recognized_country_can_request_its_trade_source(monkeypatch):
    import watch_trade
    calls = []
    class FakeFeed:
        def __init__(self, reporters):
            self.reporters = reporters
        async def get(self):
            calls.append(self.reporters)
            return {'status': 'partial', 'reporters_requested': list(self.reporters), 'routes': []}
    monkeypatch.setattr(watch_trade, 'TradeFeed', FakeFeed)
    monkeypatch.setattr(watch_trade, 'country_feeds', {})
    result = asyncio.run(watch_trade.trade_preview(reporter=356))
    assert result['reporters_requested'] == [699]
    assert asyncio.run(watch_trade.trade_preview(reporter=288))['reporters_requested'] == [288]
    assert asyncio.run(watch_trade.trade_preview(reporter=840))['reporters_requested'] == [842]
    assert len(watch_trade.country_feeds) == 3
    with pytest.raises(Exception) as exc:
        asyncio.run(watch_trade.trade_preview(reporter=0))
    assert exc.value.status_code == 422
