import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import app
from connectivity import state_directory
from offline_workspace import router
from portable_checkpoint import create_checkpoint, restore_checkpoint, verify_checkpoint
from watch_trade import TradeFeed


@pytest.fixture
def local(tmp_path,monkeypatch):
    monkeypatch.setenv('SUNLIGHT_CALIBRATION_DIR',str(tmp_path/'state'))
    monkeypatch.setenv('SUNLIGHT_OPERATIONS_DB',str(tmp_path/'state/operations.sqlite3'))
    monkeypatch.setenv('SUNLIGHT_OFFLINE','1')
    return TestClient(app)


def seed(client):
    r=client.post('/operations/sources',json={'source_id':'offline-test','name':'Offline validation publisher','publisher_url':'https://example.org','profile':'us_federal'})
    assert r.status_code==201,r.text
    measure={'metric':'delivery','unit':'kit','period_start':'2025-01-01','period_end':'2025-02-01','value':'100','document_url':'https://example.org/record'}
    r=client.post('/operations/ingest',json={'source_id':'offline-test','events':[{'event_id':'event-1','contract_id':'contract-1','item_id':'kits','category':'medical','revision':1,'title':'Offline medical kits','origin_country':'NL','destination_country':'GH','published_at':'2025-03-03T00:00:00Z','expected':{**measure,'due_at':'2025-03-01T00:00:00Z'},'observed':{**measure,'value':'73','observed_at':'2025-03-02T00:00:00Z'}}]})
    assert r.status_code==200,r.text
    return r.json()['results'][0]['case_id']


def test_offline_work_and_checkpoint_preserve_records_audit_and_document_blobs(local,tmp_path,monkeypatch):
    case=seed(local)
    before=local.get('/operations/cases/'+case+'/export').json()
    assert before['integrity']['chain_and_content_valid']
    r=local.post('/research/inquiries',json={'question':'Investigate Ghana remittances and reporting coverage in 2023','country_codes':['GH'],'year_start':2023,'year_end':2023,'sources':['monetary','operations']})
    assert r.status_code==201,r.text
    # SQLite stores document originals as blobs; exercise exact opaque-byte fidelity
    # without depending on a parser implementation in a checkpoint unit test.
    db=sqlite3.connect(state_directory()/'operations.sqlite3')
    db.execute('CREATE TABLE checkpoint_blob_test(original BLOB)')
    original=b'%PDF-original-opaque\x00\xff';db.execute('INSERT INTO checkpoint_blob_test VALUES(?)',(original,));db.commit();db.close()
    sidecar=state_directory()/'empirical_us_federal.json';sidecar.write_text('{"validation":true}')
    (state_directory()/'do-not-copy.env').write_text('private=value')
    output=tmp_path/'checkpoint.zip';manifest=create_checkpoint(output)
    assert manifest['runtime']['packages']['numpy'] and manifest['runtime']['python']
    assert set(manifest['entries'])=={'operations.sqlite3','empirical_us_federal.json'}
    assert verify_checkpoint(output)['entries']==manifest['entries']
    restored=tmp_path/'restored';restore_checkpoint(output,restored)
    monkeypatch.setenv('SUNLIGHT_OPERATIONS_DB',str(restored/'operations.sqlite3'))
    monkeypatch.setenv('SUNLIGHT_CALIBRATION_DIR',str(restored))
    after=local.get('/operations/cases/'+case+'/export').json()
    assert after['integrity']['chain_and_content_valid']
    assert after['audit']==before['audit'] and after['revisions']==before['revisions']
    with sqlite3.connect(restored/'operations.sqlite3') as db:
        assert db.execute('SELECT original FROM checkpoint_blob_test').fetchone()[0]==original
    assert (restored/'empirical_us_federal.json').read_text()=='{"validation":true}'
    assert local.get('/offline/status').json()['records']['investigations']==1
    assert local.get('/watch-data/money/analysis?measure=goods_exports&countries=GH&year=2023').status_code==200


def rewrite(source,target,change):
    with zipfile.ZipFile(source) as z:files={name:z.read(name) for name in z.namelist()}
    change(files)
    with zipfile.ZipFile(target,'w') as z:
        for name,body in files.items():z.writestr(name,body)


def test_checkpoint_tampering_traversal_and_existing_destination_are_rejected(local,tmp_path):
    seed(local);good=tmp_path/'good.zip';create_checkpoint(good)
    changed=tmp_path/'changed.zip';rewrite(good,changed,lambda files:files.update({'operations.sqlite3':files['operations.sqlite3']+b'changed'}))
    with pytest.raises(ValueError):verify_checkpoint(changed)
    traversal=tmp_path/'traversal.zip'
    def add(files):
        m=json.loads(files['manifest.json']);m['entries']['../escape']={'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}
        files['manifest.json']=json.dumps(m).encode();files['../escape']=b'x'
    rewrite(good,traversal,add)
    with pytest.raises(ValueError):restore_checkpoint(traversal,tmp_path/'new')
    assert not (tmp_path/'escape').exists() and not (tmp_path/'new').exists()
    existing=tmp_path/'existing';existing.mkdir();(existing/'keep').write_text('keep')
    with pytest.raises(ValueError):restore_checkpoint(good,existing)
    assert (existing/'keep').read_text()=='keep'


def test_source_version_change_requires_explicit_maintenance_decision(local,tmp_path):
    seed(local);good=tmp_path/'good.zip';create_checkpoint(good)
    changed=tmp_path/'version.zip'
    def change(files):
        m=json.loads(files['manifest.json']);m['source_files']={'code/api.py':'0'*64};files['manifest.json']=json.dumps(m).encode()
    rewrite(good,changed,change)
    with pytest.raises(ValueError,match='version differs'):restore_checkpoint(changed,tmp_path/'new')
    restore_checkpoint(changed,tmp_path/'explicit',allow_different_version=True)


def test_offline_status_and_checkpoint_follow_existing_access_gate(local):
    from access_gate import configure_access_gate
    protected=FastAPI();protected.include_router(router)
    configure_access_gate(protected,{'SUNLIGHT_ACCESS_PASSWORD':'local-test-only'})
    c=TestClient(protected)
    assert c.get('/offline/checkpoint').status_code==401
    assert c.get('/offline/status').status_code==401
    result=c.get('/offline/status',auth=('sunlight','local-test-only'))
    assert result.status_code==200 and result.json()['offline_policy']
    assert local.get('/offline/guide').status_code==200


def test_offline_trade_cache_survives_new_feed_without_changing_retrieval_time(local,monkeypatch):
    calls=[]
    def source(request):
        calls.append(request.url)
        return httpx.Response(200,json={'data':[{'period':2023,'reporterCode':842,'partnerCode':156,'flowCode':'X','cmdCode':'TOTAL','primaryValue':1000000,'partner2Code':0,'customsCode':'C00','motCode':0,'isReported':True}]})
    monkeypatch.setenv('SUNLIGHT_OFFLINE','0')
    feed=TradeFeed(transport=httpx.MockTransport(source),reporters=(842,),persist=True)
    online=asyncio.run(feed.get());assert len(calls)==1
    monkeypatch.setenv('SUNLIGHT_OFFLINE','1')
    restarted=TradeFeed(transport=httpx.MockTransport(lambda r:pytest.fail('Network attempted in offline mode')),reporters=(842,),persist=True)
    retained=asyncio.run(restarted.get())
    assert retained['status']=='offline_cached' and retained['routes']==online['routes']
    assert retained['fetched_at']==online['fetched_at'] and not retained['refresh_performed']
    restarted.cache_path().write_text('{"payload":{},"sha256":"invalid"}')
    unavailable=asyncio.run(TradeFeed(reporters=(842,),persist=True).get())
    assert unavailable['routes']==[] and unavailable['fetched_at'] is None


def test_remote_ai_is_disabled_even_when_credentials_are_configured(local,monkeypatch):
    from research_ai import provider_status,synthesize
    monkeypatch.setenv('SUNLIGHT_RESEARCH_MODEL','test-model')
    monkeypatch.setenv('SUNLIGHT_RESEARCH_API_KEY','test-placeholder')
    assert not provider_status()['configured']
    result=asyncio.run(synthesize('test',[],{},[],transport=httpx.MockTransport(lambda r:pytest.fail('Remote model attempted'))))
    assert result['status']=='offline_disabled' and result['sent_evidence_ids']==[]


def test_socket_guard_fails_before_external_network_and_leaves_loopback_resolution(local):
    script='''import socket
from connectivity import install_offline_guard
install_offline_guard()
for target in [('example.org',443),('203.0.113.7',443)]:
    try:socket.create_connection(target,timeout=0.1)
    except OSError as e:assert 'offline policy' in str(e)
    else:raise AssertionError('external connection permitted')
assert socket.getaddrinfo('127.0.0.1',8000)
print('offline network guard passed')
'''
    result=subprocess.run([sys.executable,'-c',script],env={**__import__('os').environ,'PYTHONPATH':str(Path(__file__).parents[1]/'code')},capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
