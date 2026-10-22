from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from api import app
from operations import FlowRevision, compare, digest

NOW = datetime.now(timezone.utc)


def event(**overrides):
    measure = {'value':'1000', 'metric':'delivery', 'unit':'kit', 'currency':None,
               'period_start':(NOW-timedelta(days=30)).date().isoformat(), 'period_end':(NOW-timedelta(days=8)).date().isoformat(),
               'document_url':'https://example.org/plan'}
    payload = {'event_id':'e1','contract_id':'contract-1','item_id':'kits','revision':1,'title':'Synthetic test kits',
               'category':'test:kits','origin_country':'NL','destination_country':'GH','published_at':NOW.isoformat(),
               'expected':{**measure,'due_at':(NOW-timedelta(days=7)).isoformat()},
               'observed':{**measure,'value':'730','observed_at':(NOW-timedelta(minutes=1)).isoformat()}}
    payload.update(overrides);return payload


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('SUNLIGHT_OPERATIONS_DB', str(tmp_path/'ledger.sqlite3'))
    c = TestClient(app)
    response=c.post('/operations/sources',json={'source_id':'test','name':'Synthetic publisher','publisher_url':'https://example.org','profile':'us_federal','expected_refresh_seconds':3600})
    assert response.status_code==201
    return c


def submit(client, events, status=200):
    response=client.post('/operations/ingest',json={'source_id':'test','events':events})
    assert response.status_code==status,response.text
    return response.json()


def test_missing_units_currency_period_and_deadline_are_not_theft_counts():
    e=event()
    assert compare(FlowRevision.model_validate(e),NOW)['gap']=='270'
    assert compare(FlowRevision.model_validate(e),NOW)['gap_percent']=='27.00'
    assert compare(FlowRevision.model_validate(event(observed=None)),NOW)['gap'] is None
    for key,value in [('unit','tonne'),('metric','goods_import'),('period_start',(NOW-timedelta(days=31)).date().isoformat())]:
        e=event();e['observed'][key]=value
        assert compare(FlowRevision.model_validate(e),NOW)['state']=='not_comparable'
    e=event();e['expected'].update(unit='currency',currency='USD');e['observed'].update(unit='currency',currency='EUR')
    assert compare(FlowRevision.model_validate(e),NOW)['gap'] is None
    e=event();e['expected']['due_at']=(NOW+timedelta(days=2)).isoformat()
    assert compare(FlowRevision.model_validate(e),NOW)['state']=='not_due'
    e['observed']=None
    assert compare(FlowRevision.model_validate(e),NOW)['state']=='not_due'
    e=event();e['observed']['observed_at']=(NOW-timedelta(days=7,hours=1)).isoformat()
    assert compare(FlowRevision.model_validate(e),NOW)['state']=='awaiting_due_observation'
    e=event();e['observed']['value']='0'
    assert compare(FlowRevision.model_validate(e),NOW)['gap']=='1000'
    e=event();e['observed']['value']='1200'
    assert compare(FlowRevision.model_validate(e),NOW)['gap']=='0'
    assert compare(FlowRevision.model_validate(e),NOW)['overage']=='200'


def test_real_delivery_engine_runs_and_results_survive_replay_and_new_clients(client):
    result=submit(client,[event()]);cid=result['results'][0]['case_id']
    detail=client.get('/operations/cases/'+cid).json()
    assert detail['comparison']['gap']=='270'
    assert detail['analysis']['delivery']['rules_evaluated']>0
    assert detail['analysis']['procurement'] is None
    original=deepcopy(detail['analysis'])
    assert submit(client,[event()])['results'][0]['state']=='duplicate'
    saved=TestClient(app).get('/operations/cases/'+cid).json()
    assert saved['analysis']==original
    assert len(saved['history'])==1
    packet=client.get('/operations/cases/'+cid+'/export').json()
    assert packet['integrity']['chain_and_content_valid'] is True
    assert packet['revisions'][0]['payload_hash']==digest(packet['revisions'][0]['payload'])


def test_procurement_engine_is_saved_only_for_matching_ocid(client):
    e=event();e['procurement_record']={'ocid':'contract-1','buyer':{'name':'Synthetic'},'tender':{'procurementMethod':'direct','value':{'amount':1000000,'currency':'USD'}}}
    cid=submit(client,[e])['results'][0]['case_id']
    result=client.get('/operations/cases/'+cid).json()['analysis']['procurement']
    assert result['ocid']=='contract-1' and result['analysis_receipt']
    bad=event();bad['procurement_record']={'ocid':'another-contract'}
    submit(client,[bad],422)


def test_conflicts_rollback_atomic_batch_and_duplicates_do_not_run_engine(client,monkeypatch):
    import operations
    calls=[]
    async def engine(e,profile):
        calls.append(e.event_id);return {'procurement':None,'delivery':None,'scope':'test'}
    monkeypatch.setattr(operations,'run_engines',engine)
    cid=submit(client,[event()])['results'][0]['case_id']
    submit(client,[event()]);assert calls==['e1']
    changed=event(title='different immutable content');submit(client,[changed],409)
    new=event(event_id='new-case',contract_id='contract-2')
    submit(client,[new,changed],409)
    assert client.get('/operations/cases').json()['total']==1
    assert len(client.get('/operations/cases/'+cid).json()['history'])==1


def test_latest_revision_wins_late_old_revisions_are_archived_and_baselines_remain_visible(client):
    cid=submit(client,[event(revision=2,event_id='e2')])['results'][0]['case_id']
    late=event(event_id='e1',revision=1);late['observed']['value']='100'
    assert submit(client,[late])['results'][0]['state']=='archived'
    detail=client.get('/operations/cases/'+cid).json()
    assert detail['revision']==2 and detail['comparison']['observed']=='730'
    changed=event(event_id='e3',revision=3);changed['expected']['value']='800'
    assert submit(client,[changed])['results'][0]['baseline_changed'] is True
    assert client.get('/operations/cases').json()['total']==1
    assert len(client.get('/operations/cases/'+cid).json()['history'])==3
    assert client.get('/operations/cases/'+cid).json()['baseline_change']['previous_expected']['value']=='1000'
    conflicting=event(event_id='new-e3',revision=3);submit(client,[conflicting],409)
    previous=event(event_id='e4',revision=4,published_at=(NOW-timedelta(days=1)).isoformat());previous['observed']=None
    submit(client,[previous],409)


def test_review_optimistic_lock_following_and_reopening_on_new_evidence(client):
    cid=submit(client,[event()])['results'][0]['case_id']
    detail=client.get('/operations/cases/'+cid).json()
    review={'expected_revision':1,'expected_audit_head':detail['audit'][-1]['hash'],'status':'resolved','followed':True,'owner':'Test analyst','note':'Synthetic review note'}
    assert client.post(f'/operations/cases/{cid}/review',json=review).status_code==200
    assert client.post(f'/operations/cases/{cid}/review',json=review).status_code==409
    assert client.get('/operations/cases?followed=true').json()['total']==1
    submit(client,[event(event_id='e2',revision=2)])
    current=client.get('/operations/cases/'+cid).json()
    assert current['review']['status']=='open' and current['review']['followed'] is True
    assert client.post(f'/operations/cases/{cid}/review',json=review).status_code==409
    assert client.get(f'/operations/cases/{cid}/export').json()['integrity']['chain_and_content_valid'] is True


def test_exact_totals_keep_sources_categories_currencies_and_periods_separate(client):
    e=event();e['expected']['value']='0.3';e['observed']['value']='0.1'
    f=event(event_id='e-b',contract_id='contract-2');f['observed']['value']='1100'
    g=event(event_id='e-c',contract_id='contract-3',category='another');g['observed']=None
    submit(client,[e,f,g])
    ledger=client.get('/operations/cases').json()
    assert ledger['total']==3 and len(ledger['comparable_groups'])==1
    assert ledger['comparable_groups'][0]['shortfall']=='0.2'
    assert ledger['comparable_groups'][0]['overage']=='100'
    assert ledger['counts']['missing_observation']==1
    assert client.get('/operations/cases?comparison=shortfall').json()['total']==1
    assert client.get('/operations/cases?q=contract-2').json()['total']==1
    assert client.get('/operations/cases?country=GH').json()['total']==3
    assert client.get('/operations/cases?country=US').json()['total']==0
    assert client.get('/operations/cases?limit=1&offset=1').json()['total']==3
    assert len(client.get('/operations/cases?limit=1&offset=1').json()['cases'])==1


def test_schema_fails_closed_on_future_data_nan_ambiguous_units_and_unknown_source(client):
    for change in [event(published_at=(NOW+timedelta(days=1)).isoformat()),event(revision=0)]:
        submit(client,[change],422)
    for value in ['NaN','Infinity','-1']:
        e=event();e['expected']['value']=value;submit(client,[e],422)
    e=event();e['observed']['observed_at']=(NOW+timedelta(seconds=1)).isoformat();submit(client,[e],422)
    e=event();e['expected']['currency']='USD';submit(client,[e],422)
    assert client.post('/operations/ingest',json={'source_id':'unknown','events':[event()]}).status_code==404
    assert client.get('/operations/cases').json()['total']==0
    assert client.get('/operations/status').json()['automatic_external_polling'] is False
    assert client.get('/operations/status').json()['un_connection']=='not_connected'


def test_integrity_detects_edited_analysis_and_deleted_versions(client,monkeypatch):
    from operations import db_path
    cid=submit(client,[event()])['results'][0]['case_id']
    submit(client,[event(event_id='e2',revision=2)])
    with sqlite3.connect(db_path()) as db:
        db.execute('DELETE FROM op_revisions WHERE case_id=? AND revision=1',(cid,))
    assert client.get(f'/operations/cases/{cid}/export').json()['integrity']['chain_and_content_valid'] is False
    with sqlite3.connect(db_path()) as db:
        db.execute("UPDATE op_revisions SET analysis='{}' WHERE case_id=?",(cid,))
    assert client.get(f'/operations/cases/{cid}/export').json()['integrity']['chain_and_content_valid'] is False


def test_operations_endpoints_inherit_deployment_auth_gate(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from access_gate import configure_access_gate
    from operations import router
    monkeypatch.setenv('SUNLIGHT_OPERATIONS_DB',str(tmp_path/'protected.sqlite3'))
    protected=FastAPI();protected.include_router(router)
    configure_access_gate(protected,{'SUNLIGHT_AUTH_REQUIRED':'1','SUNLIGHT_ACCESS_USER':'pilot','SUNLIGHT_ACCESS_PASSWORD':'synthetic-test-password'})
    with TestClient(protected) as c:
        assert c.get('/operations/cases').status_code==401
        assert c.get('/operations/status').status_code==401
        assert c.get('/operations/status',auth=('pilot','synthetic-test-password')).status_code==200
        assert c.post('/operations/sources',json={}).status_code==401


def test_source_configuration_and_freshness_cannot_claim_a_live_connection(client):
    first=client.get('/operations/sources').json()['sources'][0]
    assert first['freshness']=='awaiting_first_submission'
    conflicting={'source_id':'test','name':'Changed name','publisher_url':'https://example.org','profile':'us_federal'}
    assert client.post('/operations/sources',json=conflicting).status_code==409
    e=event(observed=None,published_at=(NOW-timedelta(days=10)).isoformat())
    submit(client,[e])
    source=client.get('/operations/sources').json()['sources'][0]
    assert source['freshness']=='late'
    assert source['last_received_at']!=source['latest_published_at']
    assert client.get('/operations/status').json()['volume_durability']=='not_verified'
