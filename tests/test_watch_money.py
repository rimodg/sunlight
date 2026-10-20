from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from watch_money import SNAPSHOT, atlas, router


def test_world_totals_keep_accounting_basis_and_do_not_add_regions():
    current=atlas()
    assert current['additive_total'] is None
    assert len(current['layers'])==27 and len(current['unconnected'])==17
    goods=next(l for l in current['layers'] if l['id']=='goods_exports')
    assert goods['year']==2025 and goods['total_basis']=='publisher_world'
    assert Decimal(goods['total'])==Decimal('26386782360229.6171875000')
    assert len(goods['rows'])==goods['country_count']==205
    assert all(r['country']!='WLD' and r['year']==2025 for r in goods['rows'])
    debt=next(l for l in current['layers'] if l['id']=='external_debt')
    assert debt['kind']=='stock' and debt['total_basis']=='covered_economies_sum'
    assert Decimal(debt['total'])==sum(Decimal(r['value']) for r in debt['rows'])


def test_missing_is_unknown_zero_and_negative_observations_are_retained():
    empty=atlas(2026)
    assert all(l['total'] is None and l['rows']==[] for l in empty['layers'])
    assert empty['aid']['total'] is None
    current=atlas()
    assert any(Decimal(r['value'])<0 for l in current['layers'] for r in l['rows'])
    assert any(Decimal(r['value'])==0 for l in current['layers'] for r in l['rows'])
    assert any(Decimal(r['usd'])<0 for r in current['aid']['rows'])
    with pytest.raises(Exception):atlas(country='INVALID')


def test_country_scope_does_not_change_world_basis_or_fabricate_counterparts():
    ghana=atlas(2023,'GH')
    assert all(r['country']=='GH' and r['year']==2023 for l in ghana['layers'] for r in l['rows'])
    assert all('GH' in [r['from'],r['to']] for r in ghana['aid']['rows'])
    assert ghana['layers'][0]['total']==atlas(2023)['layers'][0]['total']
    assert all('from' not in r and 'to' not in r for l in ghana['layers'] for r in l['rows'])


def test_bilateral_aid_is_a_signed_net_measure_not_an_arrival_or_an_oda_addition():
    aid=atlas()['aid']
    assert aid['year']==2023 and len(aid['rows'])==2870
    assert len({(r['from'],r['to'],r['year']) for r in aid['rows']})==len(aid['rows'])
    assert Decimal(aid['total'])==sum(Decimal(r['usd']) for r in aid['rows'])
    assert aid['donors']==31 and aid['recipients']==136
    assert 'overlaps ODA' in aid['basis']
    assert all(r['from']!=r['to'] for r in aid['rows'])


def test_snapshot_provenance_pins_every_series_and_excludes_noncountry_aggregates():
    countries=__import__('watch_money').COUNTRIES
    import json
    from pathlib import Path
    pins=json.loads((Path(__file__).parents[1]/'scripts/monetary_source_checksums.json').read_text())
    assert {f['path']:f['sha256'] for f in SNAPSHOT['files']}==pins
    assert any(r['country']=='XK' for l in SNAPSHOT['layers'] for r in l['rows'])
    assert SNAPSHOT['mirror_updated_at']=='2026-10-14'
    assert len(SNAPSHOT['files'])==61
    assert all(SNAPSHOT['source_revision'] in f['url'] and len(f['sha256'])==64 for f in SNAPSHOT['files'])
    for l in SNAPSHOT['layers']:
        assert l['license'] in ('CC BY-4.0','SIPRI terms and conditions')
        assert len({(r['country'],r['year']) for r in l['rows']})==len(l['rows'])
        assert all(r['country'] in countries|{'WLD'} for r in l['rows'])


def test_money_api_is_offline_and_rejects_bad_scope():
    app=FastAPI();app.include_router(router);client=TestClient(app)
    assert client.get('/watch-data/money?country=GH&year=2023').status_code==200
    for query in ['year=2018','year=2027','country=WLD','country=unknown']:
        assert client.get('/watch-data/money?'+query).status_code==422


def test_investigative_facts_preserve_country_period_and_signed_amounts():
    from research_evidence import monetary_facts
    scope={'countries':['GH'],'year_start':2023,'year_end':2023}
    facts=list(monetary_facts(scope))
    assert facts and all(f['source']=='monetary' and f['values']['year']==2023 for f in facts)
    assert all(f.get('country')=='GH' or f['values'].get('donor')=='GH' or f['values'].get('basis') in ('covered selected economy sum','covered selected bilateral pairs') for f in facts)
    assert all(f['values']['kind'] in ('stock','annual_flow','net_flow','economic_context') for f in facts if 'kind' in f['values'])


def test_research_statistics_keep_bilateral_aid_separate_from_oda():
    from research_evidence import monetary_facts
    facts=list(monetary_facts({'countries':[],'year_start':2023,'year_end':2023},summaries_only=True))
    aid=next(f for f in facts if f['values']['measure']=='bilateral_aid')
    assert Decimal(aid['values']['usd'])==Decimal(atlas()['aid']['total'])
    assert aid['values']['pairs']==2870 and 'overlaps ODA' in aid['text']
    assert next(f for f in facts if f['values']['measure']=='oda_received')['values']['usd']!=aid['values']['usd']
