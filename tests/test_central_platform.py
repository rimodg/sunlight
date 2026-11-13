"""Synthetic protection, identity, paging and frozen-replay tests for FTS."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from watch_capture import policy, project_page, records_from_projection, frozen_records
from watch_identity import canonical, digest
from watch_journal import Journal

SOURCE={'id':'fts-test','adapter':'central_platform','organisation_only_reviewed':True,'interval_seconds':900,
        'url':'https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?updatedFrom=2026-11-12T00:00:00&updatedTo=2026-11-13T00:00:00&limit=100'}


def row():
    return {'ocid':'ocds-synthetic-1','id':'123456-2026','date':'2026-11-12T12:00:00Z',
      'tender':{'legalBasis':{'scheme':'UKPGA','id':'2023/54'}},
      'contracts':[{'id':'1','awardID':'1','dateSigned':'2026-11-03T00:00:00+00:00','aboveThreshold':True,
       'documents':[{'id':'123456-2026','description':'Contract details notice on Find a Tender','documentType':'contractNotice','datePublished':'2026-11-12T12:00:00Z'}]}]}


def page(r=None,**extra):
    return json.dumps({'version':'1.1','releases':[r if r is not None else row()],**extra}).encode()


def test_project_then_persist_no_personal_fields_or_raw_body(tmp_path):
    r=row(); secret='synthetic-person@example.invalid'
    r['parties']=[{'name':secret,'contactPoint':{'email':secret}}]
    r['tender']['description']=secret
    r['contracts'][0]['documents'].append({'description':secret,'url':secret})
    raw=page(r)
    j=Journal(tmp_path/'journal.sqlite3')
    try:
        cid,records,_=frozen_records(j,SOURCE,SOURCE['url'],'2026-11-13T00:00:00Z',raw,'a'*64)
        stored=j.capture(cid)
        assert stored['sha256']==hashlib.sha256(raw).hexdigest()
        assert 'body' not in stored
        assert secret not in canonical(j.events())
        assert records[0]['parties']==[]
        assert records[0]['record']['contracts'][0]['dateSigned'].startswith('2026-11-03')
        assert 'contractEntry' not in canonical(records)
        replayed,_=records_from_projection(SOURCE,stored['projection'])
        assert replayed==records
        j.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        assert all(secret.encode() not in p.read_bytes() for p in tmp_path.iterdir())
    finally: j.close()


@pytest.mark.parametrize('field', ['ocid','date','contract_id','signature','aboveThreshold','document_id','legal_basis'])
def test_bad_retained_fields_refused_without_echo(field):
    r=row(); bad='synthetic-person@example.invalid'
    if field in ('ocid','date'): r[field]=bad
    elif field=='contract_id':r['contracts'][0]['id']=bad
    elif field=='signature':r['contracts'][0]['dateSigned']=bad
    elif field=='aboveThreshold':r['contracts'][0]['aboveThreshold']='true'
    elif field=='document_id':r['contracts'][0]['documents'][0]['id']=bad
    else:r['tender']['legalBasis']['id']=bad
    p=project_page(SOURCE,page(r))
    assert not p['records'] and len(p['refusals'])==1
    assert bad not in canonical(p)


def test_missing_fields_not_zero_or_default_scope():
    r=row();del r['contracts'][0]['aboveThreshold'];del r['contracts'][0]['dateSigned']
    p=project_page(SOURCE,page(r));item=p['records'][0]
    assert '/contracts/0/aboveThreshold' in item['coverage']['gaps']
    assert '/contracts/0/dateSigned' in item['coverage']['gaps']
    assert 'aboveThreshold' not in item['record']['contracts'][0]


def test_award_marker_is_not_contract_details_marker():
    r=row();r['contracts'][0]['documents'][0]['description']='Contract award notice on Find a Tender'
    p=project_page(SOURCE,page(r))
    assert p['records'][0]['record']['contracts'][0]['documents']==[{}]


def test_document_indexes_remain_source_indexes():
    r=row();r['contracts'][0]['documents'].insert(0,{'description':'attachment','url':'ignored'})
    p=project_page(SOURCE,page(r))
    assert p['records'][0]['record']['contracts'][0]['documents'][0]=={}
    assert '/contracts/0/documents/1/datePublished' in p['records'][0]['coverage']['mapped_fields']


def test_pagination_filter_change_and_external_host_refused():
    for next_url in ('https://evil.invalid/path','https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?limit=100'):
        with pytest.raises(ValueError):project_page(SOURCE,page(links={'next':next_url}))


def test_source_policy_needs_exact_endpoint_review_and_limit():
    for s in ({**SOURCE,'url':'https://evil.invalid/anything?limit=100'},
              {**SOURCE,'url':SOURCE['url'].replace('limit=100','limit=10')},
              {**SOURCE,'organisation_only_reviewed':False}):
        with pytest.raises(ValueError):policy({'schema':'sunlight.watch-source-policy.v1','sources':[s]})
    assert policy({'schema':'sunlight.watch-source-policy.v1','sources':[SOURCE]})


def test_unsupported_package_version_and_oversized_page_refused():
    with pytest.raises(ValueError):project_page(SOURCE,page(version='2.0'))
    with pytest.raises(ValueError):project_page(SOURCE,json.dumps({'releases':[row()]*101}).encode())


def test_wrong_adapter_version_cannot_replay():
    p=project_page(SOURCE,page());p['adapter_version']='changed'
    with pytest.raises(ValueError):records_from_projection(SOURCE,p)


def test_related_notice_timestamp_not_counted_as_current_notice():
    from scripts.measure_section53 import replay
    r=row();r['contracts'][0]['documents'][0]['id']='999999-2026'
    projection=project_page(SOURCE,page(r))
    from scripts.measure_section53 import canonical as evidence_bytes
    captured={'schema':'sunlight.section53-capture.v1','complete':True,'pages':[{'url':SOURCE['url'],'source_sha256':'a'*64,'projection':projection,'projection_sha256':hashlib.sha256(evidence_bytes(projection)).hexdigest()}]}
    assert replay(captured)['counts']['contract_notice_rows']==0


def test_live_frozen_measurement_replays_without_network():
    from scripts.measure_section53 import replay
    root=Path(__file__).resolve().parents[1]/'research/section53_2026-11-13/adapter-run'
    captured=json.loads((root/'capture.json').read_text())
    expected=json.loads((root/'results.json').read_text())
    actual=replay(captured)
    assert actual==expected
    assert actual['counts']['assessable']==0
    assert actual['counts']['states']=={'UNASSESSABLE':150}
    assert actual['counts']['both_dates']==150
    assert all(r['assessment']['contract_entry'] is None for r in actual['results'])


@pytest.mark.parametrize('kind',['transport','http','malformed'])
def test_measurement_preserves_failed_window_without_body_or_completion(monkeypatch,kind):
    import scripts.measure_section53 as m
    secret='synthetic-person@example.invalid'
    def fake(url):
        if kind=='transport': raise OSError(secret)
        return {'status':429 if kind=='http' else 200,'body':secret.encode()}
    monkeypatch.setattr(m,'fetch',fake)
    result=m.capture()
    assert result['complete'] is False
    assert len(result['pages'])==1 and result['pages'][0]['failure']
    assert secret not in json.dumps(result)
    assert not m.replay(result)['capture_complete']
