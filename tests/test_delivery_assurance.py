"""Financial arrival, delivery scope, corrections and accountable follow-up invariants."""
import asyncio
from fastapi.testclient import TestClient
import pytest
from api import app
from delivery_assurance import assurance_connection
from research import InquiryInput
from research_evidence import infer_scope
from research_tools import make_tool_runner


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('SUNLIGHT_OPERATIONS_DB', str(tmp_path/'assurance.sqlite3'))
    return TestClient(app)


def obligation(client, **changes):
    body = dict(reference='water-001', title='Water equipment obligation', sector='Water', country='GH', origin_country='NL',
                community='Five fictional communities', promise='Deliver and accept 100 usable water kits.', owner='Programme lead',
                recipient='Receiving authority', baseline_url='https://example.org/contract', due_at='2025-10-01T00:00:00Z',
                delivery_target={'value':'100','unit':'kit'}, outcome_target={'value':'5','unit':'community'}, budget='1000', currency='USD')
    body.update(changes)
    response = client.post('/assurance/obligations', json=body)
    assert response.status_code == 200, response.text
    return response.json()


def evidence(client, current, kind='funds_sent', **changes):
    financial = kind in ('funds_sent', 'funds_received', 'settlement_deduction')
    body = dict(expected_version=current['version'], kind=kind, value='1000' if financial else '73',
                unit='currency' if financial else 'community' if kind=='outcome' else 'kit', currency='USD' if financial else None,
                issuer_id='treasury' if kind=='funds_sent' else 'recipient-bank' if kind=='funds_received' else 'inspector',
                issuer_name='Attributable issuer', ledger_reference=kind+'-001', document_url='https://example.org/'+kind,
                observed_at='2025-10-02T00:00:00Z', note='Supplied record for investigation.',
                transfer_id='transfer-001' if financial else None, sender_id='treasury' if financial else None,
                recipient_id='recipient' if financial else None, settlement_due_at='2025-10-03T00:00:00Z' if kind=='funds_sent' else None,
                covers_through=None if financial else '2025-10-02T00:00:00Z')
    body.update(changes)
    return client.post('/assurance/obligations/'+current['id']+'/evidence', json=body)


def added(client, current, kind='funds_sent', **changes):
    r = evidence(client, current, kind, **changes)
    assert r.status_code == 200, r.text
    return r.json()


def test_unknown_arrival_is_never_zero_and_budget_is_not_an_executed_transfer(client):
    current = obligation(client)
    assert current['assessment']['transfers'] == []
    assert current['assessment']['accepted']['observed'] is None
    current = added(client, current)
    t = current['assessment']['transfers'][0]
    assert t['state']=='arrival_unobserved' and t['sent']=='1000'
    assert t['received'] is None and t['residual'] is None


def test_partial_credits_precredit_fees_and_exact_decimal_residual(client):
    c = obligation(client)
    c = added(client, c, value='999999999999999999.123456')
    c = added(client, c, 'funds_received', value='999999999999999900.123455')
    c = added(client, c, 'funds_received', value='50.000001', ledger_reference='credit-002')
    c = added(client, c, 'settlement_deduction', value='5')
    t=c['assessment']['transfers'][0]
    assert t['raw_difference']=='49.000000' and t['residual']=='44.000000'
    assert t['state']=='unexplained_difference' and t['distinct_declared_issuers']
    assert all(e['assurance']=='unverified_submission' for e in c['evidence'])


def test_explicit_zero_receipt_and_same_issuer_do_not_establish_independence(client):
    c=added(client,obligation(client))
    c=added(client,c,'funds_received',value='0',issuer_id='treasury')
    t=c['assessment']['transfers'][0]
    assert t['received']=='0' and t['state']=='issuer_separation_missing' and t['residual'] is None


def test_currency_mismatch_and_open_settlement_are_not_loss(client):
    c=added(client,obligation(client))
    c=added(client,c,'funds_received',value='960',currency='EUR')
    assert c['assessment']['transfers'][0]['state']=='not_comparable'
    assert c['assessment']['transfers'][0]['residual'] is None
    c2=obligation(client,reference='second')
    c2=added(client,c2,transfer_id='transfer-002',ledger_reference='sent-002',settlement_due_at='2099-01-01T00:00:00Z')
    c2=added(client,c2,'funds_received',value='100',transfer_id='transfer-002',ledger_reference='credit-002')
    assert c2['assessment']['transfers'][0]['state']=='awaiting_settlement'
    assert c2['assessment']['transfers'][0]['residual'] is None


def test_receipt_without_debit_and_wrong_identity_are_unmatched(client):
    c=obligation(client)
    c=added(client,c,'funds_received',value='960')
    assert c['assessment']['transfers'][0]['state']=='sender_unobserved'
    assert c['assessment']['transfers'][0]['received']=='960'
    c=added(client,c,recipient_id='different-recipient')
    assert {t['state'] for t in c['assessment']['transfers']}=={'sender_unobserved','arrival_unobserved'}
    assert all(t['residual'] is None for t in c['assessment']['transfers'])


def test_replay_and_cross_obligation_double_count_are_rejected(client):
    c=added(client,obligation(client))
    assert evidence(client,c).status_code==409
    c2=obligation(client,reference='second')
    assert evidence(client,c2,issuer_id='other-source',ledger_reference='newref').status_code==409
    assert evidence(client,c2,transfer_id='second-transfer').status_code==409


def test_correction_retains_old_claim_and_recomputes_without_double_count(client):
    c=added(client,obligation(client))
    c=added(client,c,'funds_received',value='960')
    old=next(e for e in c['evidence'] if e['kind']=='funds_received')
    c=added(client,c,'funds_received',value='1000',supersedes=old['id'])
    assert c['assessment']['transfers'][0]['state']=='reconciled_claims'
    assert len(c['evidence'])==3 and sum(bool(e['superseded_by']) for e in c['evidence'])==1
    export=client.get('/assurance/obligations/'+c['id']+'/export').json()
    assert export['integrity']['local_chain_and_content_valid']
    assert evidence(client,c,'funds_received',value='900',supersedes=old['id']).status_code==409
    # Hash checking must cover actual payloads, supersession links and actions.
    with assurance_connection() as db:
        db.execute('UPDATE assurance_evidence SET superseded_by=NULL WHERE id=?',(old['id'],))
    assert not client.get('/assurance/obligations/'+c['id']+'/export').json()['integrity']['local_chain_and_content_valid']


def test_latest_cumulative_delivery_is_not_added_and_outcomes_stay_separate(client):
    c=obligation(client)
    c=added(client,c,'accepted',value='60',observed_at='2025-09-30T00:00:00Z',covers_through='2025-09-30T00:00:00Z')
    assert c['assessment']['accepted']['state']=='deadline_evidence_needed'
    c=added(client,c,'accepted',value='73',ledger_reference='accepted-002')
    assert c['assessment']['accepted']['shortfall']=='27' and c['assessment']['accepted']['observed']=='73'
    assert c['assessment']['outcome']['state']=='evidence_missing'
    c=added(client,c,'outcome',value='3')
    assert c['assessment']['outcome']['shortfall']=='2' and c['assessment']['outcome']['target']['unit']=='community'


def test_conflicting_sources_units_and_supplier_self_acceptance_require_review(client):
    c=added(client,obligation(client),'accepted')
    c=added(client,c,'accepted',issuer_id='other-inspector',ledger_reference='other-record',value='75')
    assert c['assessment']['accepted']['state']=='conflicting_observations'
    assert c['assessment']['accepted']['shortfall'] is None
    c2=added(client,obligation(client,reference='second'),'accepted',unit='box',ledger_reference='boxes')
    assert c2['assessment']['accepted']['state']=='not_comparable'
    c3=added(client,obligation(client,reference='third'),'dispatched',issuer_id='supplier',ledger_reference='d-003')
    c3=added(client,c3,'accepted',issuer_id='supplier',ledger_reference='a-003',value='100')
    assert any(s['key']=='acceptance:issuer' for s in c3['assessment']['signals'])


def test_future_scope_does_not_declare_due_shortfall(client):
    c=added(client,obligation(client,due_at='2099-01-01T00:00:00Z'),'accepted',value='0')
    assert c['assessment']['accepted']['state']=='not_due' and c['assessment']['accepted']['shortfall'] is None


def test_version_conflict_preserves_evidence_and_blocks_stale_action(client):
    c=obligation(client)
    added(client,c)
    assert evidence(client,c,'funds_received').status_code==409
    assert client.post('/assurance/obligations/'+c['id']+'/actions',json=dict(expected_version=c['version'],title='Obtain receiving credit',kind='evidence_request',owner='Analyst',due_at='2025-10-10T00:00:00Z',note='Contact receiving finance team.')).status_code==409


def test_followup_requires_retained_completion_evidence_and_does_not_erase_gap(client):
    c=added(client,obligation(client),'accepted',value='73')
    path='/assurance/obligations/'+c['id']
    r=client.post(path+'/actions',json=dict(expected_version=c['version'],title='Inspect missing kits',kind='inspection',owner='Field team',due_at='2025-10-10T00:00:00Z',note='Request clinic inspection.',signal_key='stage:accepted'))
    assert r.status_code==200,r.text
    c=r.json();action=c['actions'][0]
    data=dict(expected_version=c['version'],status='completed',note='Inspection performed.')
    assert client.post(path+'/actions/'+action['id'],json=data).status_code==422
    data['completion_evidence_id']='a'*32
    assert client.post(path+'/actions/'+action['id'],json=data).status_code==422
    data['completion_evidence_id']=c['evidence'][0]['id']
    c=client.post(path+'/actions/'+action['id'],json=data).json()
    assert c['assessment']['accepted']['shortfall']=='27' and c['assessment']['open_actions']==0
    assert client.get(path+'/export').json()['integrity']['local_chain_and_content_valid']
    old=c['evidence'][0]
    c=added(client,c,'accepted',value='74',supersedes=old['id'])
    assert any(s['key']=='actions:superseded' for s in c['assessment']['signals'])


def test_example_is_explicit_isolated_and_has_exact_chain(client):
    c=client.post('/assurance/example').json()
    assert c['obligation']['synthetic'] and c['assessment']['transfers'][0]['residual']=='30000'
    assert c['assessment']['accepted']['shortfall']=='270' and c['assessment']['outcome']['shortfall']=='7'
    assert client.get('/assurance/obligations').json()['total']==0
    assert client.get('/assurance/obligations?synthetic=true').json()['total']==1
    assert client.post('/assurance/example').json()['id']==c['id']
    assert client.get('/assurance/obligations/'+c['id']+'/export').json()['integrity']['local_chain_and_content_valid']


def test_validation_rejects_impossible_clocks_and_missing_identity(client):
    c=obligation(client)
    assert evidence(client,c,observed_at='2099-01-01T00:00:00Z',settlement_due_at='2099-01-02T00:00:00Z').status_code==422
    assert evidence(client,c,transfer_id=None).status_code==422
    assert evidence(client,c,'accepted',covers_through='2099-01-01T00:00:00Z').status_code==422
    assert evidence(client,c,'funds_received',issuer_authenticated=True).status_code==422
    assert evidence(client,c,'funds_received',sender_id='recipient').status_code==422
    assert evidence(client,c,value=0.123456).status_code==422
    assert evidence(client,c,value=True).status_code==422


def test_existing_calibrated_engine_is_retained_and_corrections_mark_old_basis(client):
    c=added(client,obligation(client),'accepted',value='73')
    path='/assurance/obligations/'+c['id']
    r=client.post(path+'/delivery-analysis',json={'expected_version':c['version'],'profile':'us_federal'})
    assert r.status_code==200,r.text
    c=r.json();run=c['analyses'][0]
    assert run['basis_current'] and run['result']['rules_fired']>0
    assert any(f['rule_id']=='DEL-OUT-001' for f in run['result']['fired_rules'])
    assert client.get(path+'/export').json()['integrity']['local_chain_and_content_valid']
    old=next(e for e in c['evidence'] if e['kind']=='accepted')
    c=added(client,c,'accepted',value='100',supersedes=old['id'])
    assert not c['analyses'][0]['basis_current']
    assert client.get(path+'/export').json()['integrity']['local_chain_and_content_valid']
    empty=obligation(client,reference='no-acceptance')
    assert client.post('/assurance/obligations/'+empty['id']+'/delivery-analysis',json={'expected_version':empty['version'],'profile':'us_federal'}).status_code==422


def test_readable_report_escapes_claims_and_includes_exact_finance_delivery_and_history(client):
    c=obligation(client,title='Water <script>bad()</script>')
    c=added(client,c)
    c=added(client,c,'funds_received',value='960')
    c=added(client,c,'accepted',value='73')
    r=client.get('/assurance/obligations/'+c['id']+'/report')
    assert r.status_code==200,r.text
    assert 'Print / save as PDF' in r.text and 'Origin-to-arrival' in r.text
    assert '<script>bad()' not in r.text and '&lt;script&gt;' in r.text
    assert '960' in r.text and '40' in r.text and '27' in r.text
    assert 'True' in r.text and 'Evidence and follow-up history' in r.text


def test_saved_inquiry_and_readonly_tools_respect_obligation_scope_and_example_isolation(client):
    c=added(client,obligation(client),'accepted',value='73')
    other=obligation(client,reference='other-obligation',country='DE',origin_country=None)
    example=client.post('/assurance/example').json()
    req=InquiryInput(question='Investigate the delivery chain in Ghana',country_codes=['GH'],sources=['delivery_assurance'],obligation_ids=[c['id']])
    r=client.post('/research/inquiries',json=req.model_dump(mode='json'))
    assert r.status_code==201,r.text
    facts=r.json()['report']['facts']
    assert len(facts)==1 and facts[0]['values']['stages'][2]['shortfall']=='27'
    assert facts[0]['values']['obligation_id']==c['id'] and not facts[0]['values']['synthetic']
    tool=make_tool_runner(req,infer_scope(req.question,req.country_codes,None,None),[])
    assert asyncio.run(tool('inspect_delivery_obligation',{'obligation_id':other['id']})).get('error')
    assert asyncio.run(tool('inspect_delivery_obligation',{'obligation_id':c['id']}))['facts'][0]['values']['obligation_id']==c['id']
    default=InquiryInput(question='Investigate Ghana',sources=['delivery_assurance'])
    tool=make_tool_runner(default,infer_scope(default.question,[],None,None),[])
    assert asyncio.run(tool('inspect_delivery_obligation',{'obligation_id':example['id']})).get('error')
    r=client.post('/research/inquiries',json={'question':'Investigate this worked example','sources':['delivery_assurance'],'obligation_ids':[example['id']]})
    assert r.status_code==201 and r.json()['report']['facts'][0]['values']['synthetic']
    r=client.post('/research/inquiries',json={'question':'Investigate Ghana','sources':['delivery_assurance']})
    assert all(not f['values']['synthetic'] for f in r.json()['report']['facts'])


def test_equal_reports_in_different_timezones_are_not_false_conflicts(client):
    c=added(client,obligation(client),'accepted',value='73.0')
    c=added(client,c,'accepted',value='73.00',issuer_id='second-inspector',ledger_reference='a-002',covers_through='2025-10-02T01:00:00+01:00')
    assert c['assessment']['accepted']['shortfall']=='27.0'
