import asyncio
import json
from html import unescape
from fastapi.testclient import TestClient
import httpx
import pytest
from api import app
from research import InquiryInput
from research_evidence import infer_scope,fact
from research_tools import make_tool_runner
from research_ai import synthesize
from tests.test_operations import event
from tests.test_research import pdf_bytes

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SUNLIGHT_OPERATIONS_DB',str(tmp_path/'records.sqlite3'))
    monkeypatch.delenv('OPENAI_API_KEY',raising=False);monkeypatch.delenv('SUNLIGHT_RESEARCH_MODEL',raising=False)
    return TestClient(app)

def saved_case(client,**overrides):
    client.post('/operations/sources',json={'source_id':'test','name':'Synthetic publisher','publisher_url':'https://example.org','profile':'us_federal'})
    r=client.post('/operations/ingest',json={'source_id':'test','events':[event(**overrides)]})
    assert r.status_code==200,r.text
    return r.json()['results'][0]['case_id']

def test_readable_case_brief_contains_exact_measures_history_and_escaped_text(client):
    cid=saved_case(client,title='Synthetic <script>alert(1)</script> kits')
    initial=client.get('/operations/cases/'+cid+'/report')
    assert initial.status_code==200 and 'No review note recorded' in initial.text
    packet=client.get('/operations/cases/'+cid+'/export').json()
    c=packet['current'];client.post('/operations/cases/'+cid+'/review',json={'status':'in_review','owner':'Analyst','followed':True,'note':'Obtain <b>independent</b> receipt.','expected_revision':c['revision'],'expected_audit_head':packet['integrity']['audit_head']})
    r=client.get('/operations/cases/'+cid+'/report');assert r.status_code==200,r.text
    assert r.headers['content-type'].startswith('text/html') and 'Print / save as PDF' in r.text
    assert '270 kit' in r.text and '27.00%' in r.text and '1000 kit' in r.text and '730 kit' in r.text
    assert 'Source versions' in r.text and 'Review history' in r.text and 'Analyst' in r.text
    assert '<script>alert' not in r.text and '&lt;script&gt;' in r.text
    assert '<b>independent</b>' not in r.text and '&lt;b&gt;independent' in r.text
    assert client.get('/operations/cases/'+cid+'/export').json()['integrity']['chain_and_content_valid']

def test_readable_research_brief_is_linked_to_page_evidence_review_and_integrity(client):
    r=client.post('/research/documents',content=pdf_bytes(['Receipt A <script>bad()</script>: 73 kits']),headers={'Content-Type':'application/pdf'});doc=r.json()
    data=client.post('/research/inquiries',json={'question':'Investigate this receipt <script>bad()</script>','sources':[],'document_ids':[doc['id']]}).json()
    iid=data['report']['id'];r=client.get('/research/inquiries/'+iid+'/report')
    assert r.status_code==200,r.text
    assert 'page 1' in r.text and 'Receipt A' in r.text and data['report_hash'] in r.text
    assert '<script>bad()' not in r.text and '&lt;script&gt;bad()' in r.text
    assert 'True' in r.text and doc['sha256'] in r.text
    assert client.get('/research/inquiries/missing/report').status_code==404

def test_tools_enforce_selected_documents_country_layers_and_schema(client):
    cid=saved_case(client)
    scope=infer_scope('Investigate Ghana',[],None,None)
    r=InquiryInput(question='Investigate Ghana',sources=['materials'],document_ids=[])
    tool=make_tool_runner(r,scope,[])
    assert 'error' in asyncio.run(tool('inspect_operational_case',{'case_id':cid}))
    assert 'error' in asyncio.run(tool('read_selected_document_page',{'document_id':'a'*32,'page':1,'character_start':0}))
    assert 'error' in asyncio.run(tool('search_selected_evidence',{'query':'Ghana gold','sources':['operations']}))
    assert 'error' in asyncio.run(tool('delete_records',{}))
    r=InquiryInput(question='Investigate Germany',sources=['operations'])
    assert 'error' in asyncio.run(make_tool_runner(r,infer_scope(r.question,[],None,None),[])('inspect_operational_case',{'case_id':cid}))
    r=InquiryInput(question='Investigate Ghana',sources=['operations'])
    result=asyncio.run(make_tool_runner(r,scope,[])('inspect_operational_case',{'case_id':cid}))
    assert result['facts'][0]['values']['comparison']['gap']=='270'

def test_tools_compute_full_selected_material_scope_separately_from_excerpts(client):
    request=InquiryInput(question='Investigate Ghana gold exports',sources=['materials'])
    scope=infer_scope(request.question,[],None,None);tool=make_tool_runner(request,scope,[])
    result=asyncio.run(tool('summarize_selected_evidence',{}))
    f=result['facts'][0];assert f['values']['country_product_rows']>10 and f['values']['economies']==1
    from research_evidence import MATERIALS
    from decimal import Decimal
    expected=sum(Decimal(str(row[2])) for row in MATERIALS['rows'] if row[0]=='GHA')
    assert Decimal(f['values']['exports_usd'])==expected and 'bilateral' in f['text']
    result=asyncio.run(tool('search_selected_evidence',{'query':'Ghana gold'}))
    assert result['facts'] and all(f['source']=='materials' for f in result['facts'])

def test_selected_pdf_page_tool_preserves_original_spans_and_rejects_invalid_offsets(client):
    d=client.post('/research/documents',content=pdf_bytes(['Invoice A 100 kits','Receipt B 73 kits']),headers={'Content-Type':'application/pdf'}).json()
    request=InquiryInput(question='Investigate kits',sources=[],document_ids=[d['id']]);tool=make_tool_runner(request,infer_scope(request.question,[],None,None),[])
    result=asyncio.run(tool('read_selected_document_page',{'document_id':d['id'],'page':2,'character_start':0}))
    f=result['facts'][0];assert f['page']==2 and '73 kits' in f['excerpt']
    assert 'error' in asyncio.run(tool('read_selected_document_page',{'document_id':d['id'],'page':True,'character_start':0}))
    assert 'error' in asyncio.run(tool('read_selected_document_page',{'document_id':d['id'],'page':3,'character_start':0}))

def test_model_tool_loop_sends_results_and_only_accepts_tool_citations(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setenv('SUNLIGHT_RESEARCH_API_KEY','test-key');monkeypatch.setenv('SUNLIGHT_RESEARCH_MODEL','test-model')
    facts=[fact('initial','materials','Initial record','Ghana source context',{},'https://example.org')]
    called=[];requests=[]
    async def runner(name,args):
        called.append((name,args));return {'facts':[fact('stat:1','materials','Computed result','Calculated national exports USD 123; source year 2023.',{'usd':123},'https://example.org')]}
    def handler(request):
        body=json.loads(request.content);requests.append(body)
        if len(requests)==1:
            assert body['tools'] and body['parallel_tool_calls'] is False
            return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','name':'summarize_selected_evidence','call_id':'tool-1','arguments':'{}','id':'fc_1','status':'completed'}]})
        output=body['input'][-1];assert output['type']=='function_call_output' and output['call_id']=='tool-1'
        assert json.loads(output['output'])['evidence_excerpts'][0]['id']=='stat:1'
        text=json.dumps({'interpretations':[{'text':'The retained source reports USD 123 for 2023.','citation_ids':['stat:1']}],'hypotheses':[],'questions_to_resolve':[],'limitations':['Partial source coverage.']})
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]})
    result=asyncio.run(synthesize('Investigate Ghana exports',facts,{},[],httpx.MockTransport(handler),runner))
    assert result['status']=='completed' and called==[('summarize_selected_evidence',{})]
    assert result['work_log'][0]['returned_evidence_ids']==['stat:1']
    assert facts[-1]['id']=='stat:1' and 'stat:1' in result['sent_evidence_ids']

def test_tool_loop_is_bounded_and_retains_failure_status(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-key');monkeypatch.setenv('SUNLIGHT_RESEARCH_MODEL','test-model')
    async def runner(name,args):return {'error':'Unknown tool'}
    def handler(request):return httpx.Response(200,json={'output':[{'type':'function_call','name':'unknown','call_id':'x','arguments':'{}'}]})
    facts=[fact('a','materials','Source','Unverified record',{},'https://example.org')]
    result=asyncio.run(synthesize('Investigate this source',facts,{},[],httpx.MockTransport(handler),runner))
    assert result['status']=='unavailable_or_invalid_response' and len(result['work_log'])==4
