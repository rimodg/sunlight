import asyncio
import math

import httpx
import pytest

import watch_trade
from watch_trade import TradeFeed, country_code, parse_reporter


def row(**overrides):
    result = dict(period=2023, reporterCode=842, partnerCode=156, flowCode='X', cmdCode='TOTAL', primaryValue=1000000, partner2Code=0, customsCode='C00', motCode=0, isReported=True)
    result.update(overrides)
    return result


def test_source_codes_are_not_iso_codes():
    assert country_code(842) == 840
    assert country_code(699) == 356
    assert country_code(251) == 250
    assert country_code(0) is None
    assert country_code(True) is None
    assert country_code(9999) is None


def test_exact_source_rows_and_links_only():
    malformed = [row(period=2022), row(flowCode='M'), row(cmdCode='01'), row(partnerCode=0), row(reporterCode=156), row(primaryValue=math.nan), row(primaryValue=-1), row(primaryValue=True), row(motCode=1), row(customsCode='C01'), row(partner2Code=156)]
    result = parse_reporter({'data': [row(), row(), *malformed]}, 842)
    assert len(result) == 1
    assert result[0]['reporter'] == 840
    assert result[0]['partner'] == 156
    assert result[0]['source_reporter'] == 842
    assert result[0]['usd'] == 1000000


def test_conflicting_duplicate_totals_are_rejected():
    with pytest.raises(ValueError):
        parse_reporter({'data': [row(), row(primaryValue=2)]}, 842)
    with pytest.raises(ValueError):
        parse_reporter({'unexpected': []}, 842)


def test_source_cache_and_query_bounds(monkeypatch):
    monkeypatch.setattr(watch_trade, 'REPORTERS', (842,))
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.params['cmdCode'] == 'TOTAL'
        assert request.url.params['maxRecords'] == '500'
        assert request.url.host == 'comtradeapi.un.org'
        return httpx.Response(200, json={'data': [row()]})
    feed = TradeFeed(httpx.MockTransport(handler))
    async def run():
        first = await feed.get()
        second = await feed.get()
        assert first == second
        assert first['status'] == 'partial'
        assert first['fetched_at']
        assert len(first['routes']) == 1
    asyncio.run(run())
    assert len(calls) == 1


def test_failed_source_never_generates_flows_and_retains_dated_stale_data(monkeypatch):
    monkeypatch.setattr(watch_trade, 'REPORTERS', (842,))
    status = [429]
    def handler(request):
        return httpx.Response(status[0], json={'data': [row()]} if status[0] == 200 else {})
    feed = TradeFeed(httpx.MockTransport(handler))
    async def run():
        empty = await feed.get()
        assert empty['status'] == 'unavailable'
        assert empty['routes'] == []
        assert empty['fetched_at'] is None
        status[0] = 200; feed.expires = 0
        good = await feed.get()
        status[0] = 503; feed.expires = 0
        stale = await feed.get()
        assert stale['status'] == 'stale'
        assert stale['fetched_at'] == good['fetched_at']
        assert stale['routes'] == good['routes']
        assert stale['errors'][0]['reason'] == 'HTTP 503'
    asyncio.run(run())


def test_context_requires_complete_provenance_and_labels_modeled_pace(monkeypatch):
    for key in ['SUNLIGHT_PROCUREMENT_ANNUAL_ESTIMATE', 'SUNLIGHT_PROCUREMENT_ESTIMATE_YEAR', 'SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_URL', 'SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_TITLE']:
        monkeypatch.delenv(key, raising=False)
    assert asyncio.run(watch_trade.procurement_context())['status'] == 'not_configured'

    monkeypatch.setenv('SUNLIGHT_PROCUREMENT_ANNUAL_ESTIMATE', '1000000')
    monkeypatch.setenv('SUNLIGHT_PROCUREMENT_ESTIMATE_YEAR', '2023')
    monkeypatch.setenv('SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_URL', 'https://example.org/test-estimate')
    monkeypatch.setenv('SUNLIGHT_PROCUREMENT_ESTIMATE_SOURCE_TITLE', 'Fictional test estimate')
    configured = asyncio.run(watch_trade.procurement_context())
    assert configured['status'] == 'configured'
    assert 'not observed spending' in configured['note']
    monkeypatch.setenv('SUNLIGHT_PROCUREMENT_ANNUAL_ESTIMATE', 'NaN')
    assert asyncio.run(watch_trade.procurement_context())['status'] == 'not_configured'


def test_analysis_receipt_preserves_release_metadata_and_document_references():
    from fastapi.testclient import TestClient
    from api import app
    from analysis_receipt import content_digest
    request = {'contract': {'ocid': 'metadata-receipt-test', 'date': '2023-01-01T00:00:00Z',
                           'documents': [{'id': 'source', 'documentType': 'completionCertificate', 'url': 'https://example.org/test-certificate'}],
                           'contracts': [{'id': 'contract', 'status': 'complete', 'value': {'amount': 100, 'currency': 'USD'}}]}, 'profile': 'us_federal'}
    response = TestClient(app).post('/analyze', json=request)
    assert response.status_code == 200
    receipt = response.json()['analysis_receipt']
    assert receipt['submitted_request_sha256'] == content_digest(request)
    assert receipt['normalized_request']['contract']['documents'] == request['contract']['documents']
