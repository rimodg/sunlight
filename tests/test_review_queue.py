from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from api import app
from review_queue import queue
from tests.test_delivery_assurance import obligation, added
from tests.test_operations import event


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SUNLIGHT_OPERATIONS_DB',str(tmp_path/'review.sqlite3'))
    return TestClient(app)


def test_queue_is_deployment_scoped_unknown_is_not_loss_and_examples_are_isolated(client):
    assert client.get('/workbench/review-queue').json()['total']==0
    c=obligation(client)
    result=client.get('/workbench/review-queue').json()
    assert result['registered']=={'delivery':1,'operations':0}
    assert result['total']==1 and result['aggregate_loss'] is None
    item=result['items'][0]
    assert item['measurements']==[] and item['priority']=='evidence'
    assert not item['assigned'] and item['programme_owner']=='Programme lead'
    client.post('/assurance/example')
    assert client.get('/workbench/review-queue').json()['total']==1
    examples=client.get('/workbench/review-queue?synthetic=true').json()
    assert examples['total']==1 and examples['items'][0]['synthetic']
    assert c['id'] not in [r['id'] for r in examples['items']]


def test_priorities_use_comparability_and_due_time_not_budget_or_country(client):
    huge=obligation(client,reference='huge-missing',budget='999999999999999999')
    c=added(client,obligation(client,reference='actual-residual',country='KE'))
    c=added(client,c,'funds_received',value='960')
    result=client.get('/workbench/review-queue').json()
    assert result['items'][0]['id']==c['id'] and result['items'][0]['priority']=='reconcile'
    assert result['items'][0]['measurements']==[{'label':'Settled claim residual','value':'40','unit':'currency','currency':'USD','reference':'transfer-001'}]
    assert next(i for i in result['items'] if i['id']==huge['id'])['measurements']==[]
    assert [i['id'] for i in client.get('/workbench/review-queue?country=KE').json()['items']]==[c['id']]
    assert client.get('/workbench/review-queue?country=ZZ').status_code==422


def test_followup_assignment_and_overdue_state_refresh_without_erasing_conditions(client):
    c=obligation(client)
    first=client.get('/workbench/review-queue').json()['items'][0]
    r=client.post('/assurance/obligations/'+c['id']+'/actions',json={'expected_version':c['version'],'title':'Obtain arrival evidence','kind':'financial_review','owner':'Finance controller','due_at':'2025-10-10T00:00:00Z','note':'Obtain an attributed recipient credit.','signal_key':first['issues'][0]['key']})
    assert r.status_code==200,r.text
    result=client.get('/workbench/review-queue').json();item=result['items'][0]
    assert item['assigned'] and item['owners']==['Finance controller']
    assert item['overdue_actions']==1 and item['priority']=='overdue_followup'
    assert item['issue_count']==first['issue_count'] and item['measurements']==[]
    assert client.get('/workbench/review-queue?unassigned=true').json()['total']==0


def test_future_deadlines_and_currency_mismatch_do_not_become_measured_losses(client):
    c=obligation(client,due_at='2099-01-01T00:00:00Z')
    assert client.get('/workbench/review-queue').json()['items'][0]['priority']=='planned'
    c=added(client,c)
    c=added(client,c,'funds_received',value='960',currency='EUR')
    item=client.get('/workbench/review-queue').json()['items'][0]
    assert item['measurements']==[]


def test_operations_latest_revision_review_and_comparison_are_separate(client):
    assert client.post('/operations/sources',json={'source_id':'test','name':'Test publisher','publisher_url':'https://example.org','profile':'us_federal'}).status_code==201
    payload=event()
    submitted=client.post('/operations/ingest',json={'source_id':'test','events':[payload]}).json()
    cid=submitted['results'][0]['case_id']
    result=client.get('/workbench/review-queue').json();item=result['items'][0]
    assert item['kind']=='operations' and item['priority']=='reconcile'
    assert item['measurements'][0]['value']=='270' and item['engine_state']=='current'
    case=client.get('/operations/cases/'+cid).json()
    reviewed=client.post('/operations/cases/'+cid+'/review',json={'expected_revision':1,'expected_audit_head':case['audit'][-1]['hash'],'status':'resolved','followed':False,'owner':'Reviewer','note':'Review completed; source shortfall remains pending receiving documentation.'})
    assert reviewed.status_code==200,reviewed.text
    result=client.get('/workbench/review-queue').json()
    assert result['total']==0 and result['reviewed_source_conditions']==1
    retained=client.get('/workbench/review-queue?include_reviewed=true').json()['items'][0]
    assert retained['priority']=='reviewed' and retained['condition']=='shortfall'
    assert retained['measurements'][0]['value']=='270'
    payload.update(event_id='e2',revision=2)
    assert client.post('/operations/ingest',json={'source_id':'test','events':[payload]}).status_code==200
    assert client.get('/workbench/review-queue').json()['items'][0]['version']==2


def test_pagination_counts_and_task_lenses_cover_all_registered_records(client):
    for i in range(4):obligation(client,reference='scope-'+str(i),country='GH' if i<3 else 'KE')
    result=client.get('/workbench/review-queue?country=GH&limit=1&offset=1').json()
    assert len(result['items'])==1 and result['total']==3 and result['registered']['delivery']==3
    assert client.get('/workbench/review-queue?lens=finance').json()['total']==4
    assert client.get('/workbench/review-queue?lens=unknown').status_code==422
    assert client.get('/workbench/review-queue?q=scope-3').json()['total']==1


def test_changed_acceptance_marks_calibrated_check_stale(client):
    c=added(client,obligation(client),'accepted')
    path='/assurance/obligations/'+c['id']
    response=client.post(path+'/delivery-analysis',json={'expected_version':c['version'],'profile':'us_federal'})
    assert response.status_code==200,response.text
    c=response.json()
    assert client.get('/workbench/review-queue').json()['items'][0]['engine_state']=='current'
    c=added(client,c,'accepted',value='80',supersedes=c['evidence'][0]['id'])
    item=client.get('/workbench/review-queue').json()['items'][0]
    assert item['engine_state']=='stale' and item['measurements'][0]['value']=='20'


def test_readable_queue_brief_has_scope_versions_next_evidence_and_escaped_text(client):
    obligation(client,title='<script>Review me</script>')
    response=client.get('/workbench/review-queue/report?lens=finance&country=GH')
    assert response.status_code==200
    assert 'text/html' in response.headers['content-type']
    assert 'Print / save as PDF' in response.text and 'record version 1' in response.text
    assert '&lt;script&gt;Review me&lt;/script&gt;' in response.text and '<script>' not in response.text
    assert 'Next evidence:' in response.text and 'Showing 1 of 1 records' in response.text
    assert response.headers['cache-control']=='no-store'


def test_invalid_engine_output_is_a_review_issue_not_a_clean_verdict(client):
    from review_queue import operational_item
    from operations import utcnow
    case={'case_id':'test','source_id':'test','revision':1,'record':event(),'comparison':{'state':'matched','reason':'Values match','gap':'0','overage':'0','unit':'kit','currency':None,'metric':'delivery'},'review':{'status':'open','owner':'','followed':False},'analysis':{'procurement':{'structure':None,'errors':['missing inputs']},'delivery':None},'baseline_change':None,'received_at':utcnow().isoformat()}
    item=operational_item(case,utcnow())
    assert item['engine_state']=='errors' and 'procurement' in item['lenses']
    assert item['issue_count']==2 and item['measurements']==[]


def test_attached_engine_recommendation_is_not_lost_when_quantities_match(client):
    from review_queue import operational_item
    from operations import utcnow
    case={'case_id':'test','source_id':'test','revision':1,'record':event(),'comparison':{'state':'matched','reason':'Values match','gap':'0','overage':'0','unit':'kit','currency':None,'metric':'delivery'},'review':{'status':'open','owner':'','followed':False},'analysis':{'procurement':{'structure':{'verdict':'CONCERN','contradictions':[]},'recommended_for_investigation':True,'gate_verdict':'yellow','errors':[]},'delivery':None},'baseline_change':None,'received_at':utcnow().isoformat()}
    item=operational_item(case,utcnow())
    assert item and item['priority']=='evidence' and item['measurements']==[]
    assert any(i['key']=='engine_decision' for i in item['issues'])
