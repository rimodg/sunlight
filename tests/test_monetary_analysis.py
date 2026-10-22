import csv
import io
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from monetary_analysis import analyse
from watch_money import COUNTRY_CATALOG, SNAPSHOT, router


def client():
    app=FastAPI();app.include_router(router)
    return TestClient(app)


def sample():
    return {**SNAPSHOT,'layers':[{**SNAPSHOT['layers'][0],'year':2023,'rows':[
        {'country':'GH','year':2022,'value':'9007199254740993.01'},
        {'country':'GH','year':2023,'value':'9007199254740993.03'},
        {'country':'US','year':2023,'value':'0'},
    ]}]}


def test_exact_change_and_no_mixed_coverage_world_residual():
    result=analyse(sample(),COUNTRY_CATALOG,'goods_exports','GH,US',2022,2023)
    world,ghana,us=result['series']
    assert world['change']['status']=='coverage_changed'
    assert world['change']['difference'] is None
    assert ghana['change']['difference']=='0.02'
    assert us['baseline']['value'] is None and us['current']['value']=='0'
    assert us['change']['status']=='missing_observation'
    assert len(ghana['points'])==8 and ghana['points'][-1]['value'] is None
    assert all('_coverage' not in p for s in result['series'] for p in s['points'])


def test_nonpositive_baseline_has_signed_difference_without_percent_and_same_year_no_change():
    s=sample();s['layers'][0]['rows']=[{'country':'GH','year':2022,'value':'-10'},{'country':'GH','year':2023,'value':'0'}]
    result=analyse(s,COUNTRY_CATALOG,'goods_exports','GH',2022,2023)
    assert result['series'][1]['change']=={'status':'comparable','difference':'10','percent':None,'percent_basis':'nonpositive_baseline'}
    assert analyse(s,COUNTRY_CATALOG,'goods_exports','GH',2023,2023)['series'][1]['change']['status']=='same_period'


def test_aid_roles_preserve_signed_entries_and_check_pair_coverage():
    s=sample();s['aid']={**s['aid'],'rows':[
        {'from':'US','to':'GH','year':2022,'usd':'100'},
        {'from':'US','to':'GH','year':2023,'usd':'90'},
        {'from':'GH','to':'US','year':2023,'usd':'-5'},
    ]}
    incoming=analyse(s,COUNTRY_CATALOG,'aid','GH',2022,2023)
    assert incoming['series'][0]['current']['value']=='85'
    assert incoming['series'][0]['change']['status']=='coverage_changed'
    assert incoming['series'][1]['current']['value']=='90'
    assert incoming['series'][1]['change']['difference']=='-10'
    outgoing=analyse(s,COUNTRY_CATALOG,'aid','GH',2022,2023,'outward')
    assert outgoing['series'][1]['current']['value']=='-5'
    assert outgoing['series'][1]['change']['status']=='missing_observation'


def test_real_publisher_world_and_stock_basis_are_retained():
    result=analyse(SNAPSHOT,COUNTRY_CATALOG,'goods_exports','GH,US',2024,2025)
    world=result['series'][0]
    assert world['current']['basis']=='publisher_world' and world['change']['status']=='comparable'
    assert Decimal(world['change']['difference'])==Decimal(world['current']['value'])-Decimal(world['baseline']['value'])
    assert analyse(SNAPSHOT,COUNTRY_CATALOG,'external_debt','GH',2023,2024)['measure']['kind']=='stock'


def test_api_rejects_invalid_or_misordered_scope_and_never_substitutes_2026():
    c=client()
    for query in ['measure=bad','measure=aid&direction=both','measure=goods_exports&countries=GH,GH',
                  'measure=goods_exports&countries=GH,US,FR,DE,GB','measure=goods_exports&countries=WLD',
                  'measure=goods_exports&baseline=2025&year=2024','measure=goods_exports&year=2027']:
        assert c.get('/watch-data/money/analysis?'+query).status_code==422
    data=c.get('/watch-data/money/analysis?measure=goods_exports&countries=GH&year=2026').json()
    assert all(s['current']['value'] is None and s['change']['difference'] is None for s in data['series'])


def test_readable_and_csv_exports_keep_scope_exact_values_source_and_unknowns(monkeypatch):
    import watch_money
    s=sample();s['layers'][0]['label']='<script>test</script>'
    monkeypatch.setattr(watch_money,'SNAPSHOT',s)
    c=client();query='?measure=goods_exports&countries=GH&baseline=2022&year=2023'
    report=c.get('/watch-data/money/analysis/report'+query)
    assert report.status_code==200 and '<script>test</script>' not in report.text
    assert '&lt;script&gt;' in report.text and '9007199254740993.03' in report.text
    assert 'Print / save as PDF' in report.text and SNAPSHOT['source_revision'] in report.text
    exported=c.get('/watch-data/money/analysis.csv'+query)
    rows=list(csv.DictReader(io.StringIO(exported.text)))
    ghana=[r for r in rows if r['country']=='GH']
    assert len(ghana)==8
    assert next(r for r in ghana if r['year']=='2023')['exact_current_usd']=='9007199254740993.03'
    assert next(r for r in ghana if r['year']=='2026')['exact_current_usd']==''
