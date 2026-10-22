"""Saved, source-cited investigations with optional model synthesis and bounded PDFs."""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
from itertools import chain
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from typing import Literal
from urllib.parse import unquote,quote
import uuid

from fastapi import APIRouter,HTTPException,Query,Request
from fastapi.responses import Response
from pydantic import Field,model_validator
from starlette.concurrency import run_in_threadpool

from operations import StrictModel,connection,canonical,digest,append_audit,utcnow
from research_ai import provider_status,synthesize
from research_evidence import (BY_CODE,COUNTRIES,SOURCE_LABELS,PROCUREMENT,MATERIALS,ARMS,CONFLICTS,
    infer_scope,public_facts,material_facts,arms_facts,conflict_facts,operations_facts,trade_facts,monetary_facts,select_balanced,fact)

router=APIRouter(prefix='/research',tags=['Evidence research'])
WORK_SLOT=threading.BoundedSemaphore(1)
MAX_PDF_BYTES=8*1024*1024
MAX_DOCUMENTS=200
MAX_ARCHIVE_BYTES=128*1024*1024
LAYERS=Literal['procurement','materials','arms','conflicts','operations','goods_trade','delivery_assurance','monetary']


@contextmanager
def research_connection():
    with connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS research_documents(id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, filename TEXT NOT NULL, received_at TEXT NOT NULL, extraction TEXT NOT NULL, original BLOB NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS research_inquiries(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, report TEXT NOT NULL, report_hash TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL)')
        yield db


class InquiryInput(StrictModel):
    question:str=Field(min_length=8,max_length=12000)
    country_codes:list[str]=Field(default_factory=list,max_length=10)
    community:str=Field(default='',max_length=200)
    year_start:int|None=Field(default=None,ge=1992,le=2100)
    year_end:int|None=Field(default=None,ge=1992,le=2100)
    sources:list[LAYERS]=Field(default_factory=lambda:list(SOURCE_LABELS),max_length=8)
    document_ids:list[str]=Field(default_factory=list,max_length=5)
    obligation_ids:list[str]=Field(default_factory=list,max_length=10)
    use_ai:bool=False
    share_evidence_with_ai:bool=False
    refresh_trade:bool=False
    parent_inquiry_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def valid_scope(self):
        if not self.question.strip():raise ValueError('Inquiry text is required')
        self.country_codes=list(dict.fromkeys(c.upper() for c in self.country_codes))
        if any(c not in BY_CODE for c in self.country_codes):raise ValueError('Select recognized country/territory ISO codes')
        self.document_ids=list(dict.fromkeys(self.document_ids));self.sources=list(dict.fromkeys(self.sources))
        if any(not __import__('re').fullmatch('[a-f0-9]{32}',d) for d in self.document_ids):raise ValueError('Invalid document ID')
        self.obligation_ids=list(dict.fromkeys(self.obligation_ids))
        if any(not __import__('re').fullmatch('[a-f0-9]{32}',d) for d in self.obligation_ids):raise ValueError('Invalid obligation ID')
        if self.obligation_ids and 'delivery_assurance' not in self.sources:raise ValueError('Selected obligations require the delivery assurance layer')
        if self.year_start and self.year_end and self.year_start>self.year_end:raise ValueError('Year range is reversed')
        if not self.sources and not self.document_ids:raise ValueError('Select an evidence layer or a document')
        if self.use_ai and not self.share_evidence_with_ai:raise ValueError('AI mode requires explicit authorization to send the inquiry and selected excerpts to the provider')
        return self


class InquiryUpdate(StrictModel):
    expected_version:int=Field(ge=1)
    status:Literal['open','in_review','closed']
    followed:bool
    note:str=Field(min_length=1,max_length=4000)

    @model_validator(mode='after')
    def nonblank_note(self):
        if not self.note.strip():raise ValueError('A meaningful review note is required')
        return self


def catalog():
    return [
        {'id':'monetary','label':SOURCE_LABELS['monetary'],'years':list(range(2019,2027)),'coverage':'27 annual USD indicators, stocks and economic context kept separate; dated country observations and partial bilateral net aid. Pinned third-party WDI mirror, not authenticated settlement. Overlapping measures are never added.','url':'/watch-data/money','revision':'4252d91d988efc0f116d4fa48e92357b778729e5'},
        {'id':'procurement','label':SOURCE_LABELS['procurement'],'years':PROCUREMENT['years'],'coverage':PROCUREMENT['coverage'],'url':PROCUREMENT['source_repository'],'revision':PROCUREMENT['source_revision']},
        {'id':'materials','label':SOURCE_LABELS['materials'],'years':[MATERIALS['year']],'coverage':MATERIALS['definition']+' '+MATERIALS['route_precision'],'url':MATERIALS['mirror_url'],'revision':MATERIALS['source_revision']},
        {'id':'arms','label':SOURCE_LABELS['arms'],'years':ARMS['years'],'coverage':ARMS['coverage']+' '+ARMS['gap_limit'],'url':ARMS['mirror_url'],'revision':ARMS['source_revision']},
        {'id':'conflicts','label':SOURCE_LABELS['conflicts'],'years':[CONFLICTS['year']],'coverage':CONFLICTS['coverage']+' Country filters use publisher reporting-area labels, not sovereign boundaries or procurement jurisdictions; Gaza may be coded under Israel.','url':CONFLICTS['mirror_url'],'revision':CONFLICTS['mirror_revision']},
        {'id':'operations','label':SOURCE_LABELS['operations'],'years':[],'coverage':'Latest 500 operational case revisions scanned, then scope-filtered. Declared source claims and existing engine findings only. Source push pilot, not a live UN feed.','url':'/operations/status'},
        {'id':'delivery_assurance','label':SOURCE_LABELS['delivery_assurance'],'years':[],'coverage':'Registered obligations, separately attributed debit/credit entries and cumulative delivery/service reports. Latest 200 scoped obligations, or explicitly selected IDs; year filter uses obligation deadline. Synthetic examples excluded unless explicitly selected. Submitted claims are not authenticated financial or field feeds.','url':'/assurance/status'},
        {'id':'goods_trade','label':SOURCE_LABELS['goods_trade'],'years':[2023],'coverage':'Only already cached UN Comtrade preview responses unless you request a bounded refresh. Selected reporters, annual values, no live shipment tracking.','url':'https://comtradeapi.un.org/'}]


@router.get('/status')
def status():
    return {'mode':'evidence_research_pilot','ai':provider_status(),'sources':catalog(),
            'document_limits':{'bytes':MAX_PDF_BYTES,'pages':64,'characters':250000,'archive_documents':MAX_DOCUMENTS,'archive_bytes':MAX_ARCHIVE_BYTES,'ocr':False},
            'storage_note':'Uses the operations SQLite filesystem and deployment access gate. Persistent volume and institutional identity/tenant controls remain required. Uploaded originals and extracted text are retained locally.',
            'research_limit':'No complete global economic census, causal model of societies or authenticated publisher/ground-truth feed is supplied by this feature.'}


@router.get('/countries')
def countries():
    return {'countries':[{k:c[k] for k in ('name','code','alpha3')} for c in COUNTRIES],
            'attribution':'world-countries 5.1.0 / mledoze contributors; derived ODbL database, not evidence of economic coverage or sovereignty.',
            'license_url':'https://opendatacommons.org/licenses/odbl/1-0/'}


def document_metadata(row):
    extraction=json.loads(row['extraction'])
    return {'id':row['id'],'sha256':row['sha256'],'extraction_sha256':digest(extraction),'filename':row['filename'],'received_at':row['received_at'],
            **{k:v for k,v in extraction.items() if k!='pages'},'original_url':f'/research/documents/{row["id"]}/file'}


def extract_pdf(data):
    with tempfile.TemporaryDirectory(prefix='sunlight-pdf-') as folder:
        path=Path(folder)/'document.pdf';path.write_bytes(data)
        try:
            completed=subprocess.run([sys.executable,str(Path(__file__).with_name('research_pdf.py')),str(path)],
                stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=15,env={'LANG':'C.UTF-8'})
            if completed.returncode or len(completed.stdout)>2000000:raise ValueError('Parser failed')
            result=json.loads(completed.stdout)
        except (subprocess.TimeoutExpired,ValueError,OSError):
            raise HTTPException(422,'PDF extraction exceeded limits or failed. Split the document or provide a text-readable PDF.')
    if result.get('error')=='page_limit':raise HTTPException(413,'PDF exceeds the 64-page limit. Split it into smaller documents.')
    if result.get('error'):raise HTTPException(422,'PDF is unreadable, encrypted, empty, or exceeds extraction resources. No OCR or password bypass is performed.')
    return result


@router.post('/documents',status_code=201)
async def upload_document(request:Request):
    if request.headers.get('content-type','').split(';')[0] not in ('application/pdf','application/octet-stream'):
        raise HTTPException(415,'Upload a PDF as application/pdf')
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>MAX_PDF_BYTES:raise HTTPException(413,'PDF exceeds 8 MB')
    if b'%PDF-' not in data[:1024]:raise HTTPException(422,'File does not have a PDF header')
    checksum=hashlib.sha256(data).hexdigest();doc_id=checksum[:32]
    with research_connection() as db:
        existing=db.execute('SELECT id,sha256,filename,received_at,extraction FROM research_documents WHERE sha256=?',(checksum,)).fetchone()
        if existing:return {**document_metadata(existing),'duplicate':True}
    if not WORK_SLOT.acquire(blocking=False):raise HTTPException(429,'Another document or investigation is processing; retry shortly')
    try:
        extraction=await run_in_threadpool(extract_pdf,bytes(data))
        filename=Path(unquote(request.headers.get('x-filename','document.pdf'))[:300]).name.replace('\x00','') or 'document.pdf'
        with research_connection() as db:
            db.execute('BEGIN IMMEDIATE')
            quota=db.execute('SELECT COUNT(*) n,COALESCE(SUM(length(original)),0) bytes FROM research_documents').fetchone()
            if quota['n']>=MAX_DOCUMENTS or quota['bytes']+len(data)>MAX_ARCHIVE_BYTES:raise HTTPException(413,'Pilot document archive quota reached; ask the deployment operator to manage retention')
            db.execute('INSERT INTO research_documents VALUES(?,?,?,?,?,?)',(doc_id,checksum,filename,utcnow().isoformat(),canonical(extraction),bytes(data)))
            row=db.execute('SELECT id,sha256,filename,received_at,extraction FROM research_documents WHERE id=?',(doc_id,)).fetchone()
            return {**document_metadata(row),'duplicate':False}
    finally:WORK_SLOT.release()


@router.get('/documents')
def list_documents(limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    with research_connection() as db:
        total=db.execute('SELECT COUNT(*) n FROM research_documents').fetchone()['n']
        rows=db.execute('SELECT id,sha256,filename,received_at,extraction FROM research_documents ORDER BY received_at DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
    return {'documents':[document_metadata(r) for r in rows],'total':total}


@router.get('/documents/{doc_id}')
def get_document(doc_id:str):
    with research_connection() as db:
        row=db.execute('SELECT id,sha256,filename,received_at,extraction FROM research_documents WHERE id=?',(doc_id,)).fetchone()
    if not row:raise HTTPException(404,'Document not found')
    return {**document_metadata(row),'pages':json.loads(row['extraction'])['pages']}


@router.get('/documents/{doc_id}/file')
def original_document(doc_id:str):
    with research_connection() as db:
        row=db.execute('SELECT filename,original FROM research_documents WHERE id=?',(doc_id,)).fetchone()
    if not row:raise HTTPException(404,'Document not found')
    return Response(bytes(row['original']),media_type='application/pdf',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['filename']), 'Cache-Control':'no-store'})


def document_facts(rows):
    for row in rows:
        metadata=document_metadata(row);extraction=json.loads(row['extraction'])
        for page in extraction['pages']:
            text=page['text']
            for start in range(0,len(text),1350):
                excerpt=text[start:start+1500]
                if not excerpt.strip():continue
                yield fact(f'doc:{row["id"]}:p{page["page"]}:c{start}','documents',f'{row["filename"]} / page {page["page"]}',
                    'User-uploaded document excerpt, not independently verified: '+excerpt,
                    {'document_sha256':row['sha256'],'page':page['page'],'character_start':start,'character_end':start+len(excerpt)},
                    metadata['original_url'],document_id=row['id'],page=page['page'],excerpt=excerpt,
                    page_text_truncated=page['truncated'])


async def cached_trade(request,scope):
    from watch_trade import feed,country_feeds,trade_preview
    from connectivity import offline_enabled
    fresh=None
    if (request.refresh_trade or offline_enabled()) and 'goods_trade' in request.sources:
        first=BY_CODE[scope['countries'][0]] if scope['countries'] else None
        fresh=await trade_preview(int(first['numeric']) if first and first['numeric'] else None)
    snapshots=[s for s in [feed.load_cached(),*[f.load_cached() for f in country_feeds.values()],fresh] if s]
    unique={}
    for snapshot in snapshots:
        for f in trade_facts(snapshot,scope):
            if f['id'] not in unique or str(f['values']['retrieved_at'])>str(unique[f['id']]['values']['retrieved_at']):unique[f['id']]=f
    return list(unique.values()),{'cached_snapshots':len(snapshots),'statuses':sorted({s['status'] for s in snapshots}),
                                 'refresh_requested':request.refresh_trade,'limit':'Refresh uses the first selected reporter or the bounded global preview; no worldwide census is implied.'}


def research_gaps(scope,community,sources,counts,documents):
    gaps=[]
    for source in sources:
        if not counts.get(source):gaps.append({'kind':'coverage','source':source,'text':'No matching evidence retrieved from this selected layer and scope. This does not establish zero activity, peace or absence of wrongdoing.'})
    for d in documents:
        if d['status']=='ocr_required':gaps.append({'kind':'document','source':d['id'],'text':'No searchable PDF text was extracted. OCR is required; no document claims or numerical gaps were inferred.'})
        if d['truncated_pages']:gaps.append({'kind':'document','source':d['id'],'text':'PDF text was truncated on pages '+', '.join(map(str,d['truncated_pages']))+'. Retrieve the original before drawing completeness conclusions.'})
    if community:gaps.append({'kind':'geography','text':f'Community/place under study: {community}. Country-level totals and publisher reporting-area labels do not measure local conditions. No automatic community-to-country, social-condition or causal inference is made.'})
    gaps.extend([
        {'kind':'causation','text':'Trade patterns, conflict events and procurement discrepancies alone do not establish why a society trades as it does. Competing hypotheses require local, temporal and independent evidence.'},
        {'kind':'comparability','text':'Goods trade overlaps material trade; aid, institutional financing and other income subsets can overlap too. Export/import views are not additive. Net flows can be negative; stocks and GDP are not payments. Published procurement and monetary statistics have no independently verified recipient credit or delivery amount. Currencies, units, stock/flow concepts and different periods must not be subtracted to invent a global theft gap.'},
        {'kind':'coverage','text':'Retrieval is lexical and source-balanced, capped at 40 excerpts and 10 per layer/document. A result is a bounded evidence dossier, not an exhaustive worldwide investigation or a validated answer to every part of the inquiry.'}])
    return gaps


def retrieve_evidence(request,scope,trade):
    from delivery_assurance import research_facts as assurance_facts
    with research_connection() as db:
        if request.parent_inquiry_id and not db.execute('SELECT id FROM research_inquiries WHERE id=?',(request.parent_inquiry_id,)).fetchone():raise HTTPException(404,'Parent investigation not found')
        documents=[]
        for doc_id in request.document_ids:
            row=db.execute('SELECT id,sha256,filename,received_at,extraction FROM research_documents WHERE id=?',(doc_id,)).fetchone()
            if not row:raise HTTPException(404,'A selected document was not found')
            documents.append(row)
        factories={'monetary':lambda:monetary_facts(scope),'procurement':lambda:public_facts(scope),'materials':lambda:material_facts(scope),'arms':lambda:arms_facts(scope),
                   'conflicts':lambda:conflict_facts(scope),'operations':lambda:operations_facts(db,scope),'goods_trade':lambda:trade,
                   'delivery_assurance':lambda:assurance_facts(scope,request.obligation_ids)}
        candidates=chain.from_iterable([*(factories[s]() for s in request.sources),document_facts(documents)])
        facts,counts=select_balanced(candidates,request.question,scope['countries'])
        metadata=[document_metadata(d) for d in documents]
    return facts,counts,metadata


@router.post('/inquiries',status_code=201)
async def create_inquiry(request:InquiryInput):
    if not WORK_SLOT.acquire(blocking=False):raise HTTPException(429,'Another document or investigation is processing; retry shortly')
    try:
        scope=infer_scope(request.question,request.country_codes,request.year_start,request.year_end)
        if len(scope['countries'])>10:raise HTTPException(422,'More than ten countries matched; select an explicit scope')
        if scope['ambiguous_names'] and not scope['countries']:
            raise HTTPException(422,'Ambiguous country name; select the country codes explicitly: '+', '.join(scope['ambiguous_names']))
        scope['community']=request.community
        scope['obligation_ids']=request.obligation_ids
        trade,trade_status=await cached_trade(request,scope) if 'goods_trade' in request.sources else ([],{'status':'not_selected'})
        facts,counts,metadata=await run_in_threadpool(retrieve_evidence,request,scope,trade)
        gaps=research_gaps(scope,request.community,request.sources,counts,metadata)
        from research_tools import make_tool_runner
        ai=await synthesize(request.question,facts,scope,[g['text'] for g in gaps],tool_runner=make_tool_runner(request,scope,trade)) if request.use_ai else {'status':'not_requested','synthesis':None,'sent_evidence_ids':[]}
        inquiry_id=uuid.uuid4().hex;created_at=utcnow().isoformat()
        report={'schema_version':'sunlight.research.dossier.v1','id':inquiry_id,'created_at':created_at,'request':request.model_dump(mode='json'),
                'scope':scope,'facts':facts,'candidate_counts':counts,'documents':metadata,'sources':[s for s in catalog() if s['id'] in request.sources],
                'trade_status':trade_status,'gaps':gaps,'ai':ai,
                'review_plan':['Confirm the covered period, classification, reporting basis and baseline version before comparing values.',
                               'Trace relevant contract/release/item identifiers to invoices, dispatch, receipt, inspection, payment and custody records.',
                               'Separate reported differences from missing evidence and require independent corroboration before alleging theft.',
                               'For community or causal questions, test competing explanations using dated local observations; national aggregates are context only.']}
        fingerprint=digest(report);state={'status':'open','followed':False,'note':''}
        with research_connection() as db:
            db.execute('INSERT INTO research_inquiries VALUES(?,?,?,?,?,?)',(inquiry_id,created_at,canonical(report),fingerprint,canonical(state),1))
            append_audit(db,'research:'+inquiry_id,'research_created',{'report_hash':fingerprint,'ai_status':ai['status'],'documents':[d['sha256'] for d in metadata]})
        return {'report':report,'report_hash':fingerprint,'state':state,'version':1,'review_history':[]}
    finally:WORK_SLOT.release()


@router.get('/inquiries')
def list_inquiries(q:str=Query('',max_length=200),followed:bool=False,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0)):
    with research_connection() as db:
        where="WHERE instr(lower(json_extract(report,'$.request.question')),lower(?))>0"+(' AND json_extract(state,\'$.followed\')=1' if followed else '')
        total=db.execute('SELECT COUNT(*) n FROM research_inquiries '+where,(q,)).fetchone()['n']
        rows=db.execute("SELECT id,created_at,json_extract(report,'$.request.question') question,json_extract(report,'$.ai.status') ai_status,json_array_length(json_extract(report,'$.facts')) facts,state,version FROM research_inquiries "+where+' ORDER BY created_at DESC LIMIT ? OFFSET ?',(q,limit,offset)).fetchall()
    return {'inquiries':[{**dict(r),'state':json.loads(r['state'])} for r in rows],'total':total}


@router.get('/inquiries/{inquiry_id}')
def get_inquiry(inquiry_id:str):
    with research_connection() as db:
        row=db.execute('SELECT * FROM research_inquiries WHERE id=?',(inquiry_id,)).fetchone()
        history=[json.loads(r['payload']) for r in db.execute('SELECT payload FROM op_audit WHERE case_id=? ORDER BY seq',('research:'+inquiry_id,))]
    if not row:raise HTTPException(404,'Investigation not found')
    return {'report':json.loads(row['report']),'report_hash':row['report_hash'],'content_valid':digest(json.loads(row['report']))==row['report_hash'],'state':json.loads(row['state']),'version':row['version'],
            'review_history':[{'at':a['at'],**a['detail']} for a in history if a['action']=='research_reviewed']}


@router.post('/inquiries/{inquiry_id}/review')
def update_inquiry(inquiry_id:str,update:InquiryUpdate):
    with research_connection() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT version FROM research_inquiries WHERE id=?',(inquiry_id,)).fetchone()
        if not row:raise HTTPException(404,'Investigation not found')
        if row['version']!=update.expected_version:raise HTTPException(409,'Investigation review changed; reload before saving')
        state=update.model_dump(mode='json');state.pop('expected_version')
        db.execute('UPDATE research_inquiries SET state=?,version=version+1 WHERE id=?',(canonical(state),inquiry_id))
        append_audit(db,'research:'+inquiry_id,'research_reviewed',{'version':row['version']+1,**state})
    return {'state':state,'version':row['version']+1}


@router.get('/inquiries/{inquiry_id}/export')
def export_inquiry(inquiry_id:str):
    result=get_inquiry(inquiry_id)
    with research_connection() as db:
        audit=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM op_audit WHERE case_id=? ORDER BY seq',('research:'+inquiry_id,))]
        originals=[]
        for d in result['report']['documents']:
            row=db.execute('SELECT original,extraction FROM research_documents WHERE id=?',(d['id'],)).fetchone()
            originals.append({'id':d['id'],'sha256':d['sha256'],'content_valid':bool(row and hashlib.sha256(bytes(row['original'])).hexdigest()==d['sha256'] and digest(json.loads(row['extraction']))==d['extraction_sha256']),'original_url':d['original_url']})
    previous='';valid=result['content_valid']
    for a in audit:
        valid=valid and a['previous_hash']==previous and digest({'previous_hash':previous,'payload':a['payload']})==a['hash'];previous=a['hash']
    valid=valid and bool(audit) and audit[0]['payload']['detail']['report_hash']==result['report_hash'] and all(d['content_valid'] for d in originals)
    reconstructed={'status':'open','followed':False,'note':''};version=1
    for a in audit:
        if a['payload']['action']=='research_reviewed':
            reconstructed={k:v for k,v in a['payload']['detail'].items() if k!='version'};version=a['payload']['detail']['version']
    valid=valid and reconstructed==result['state'] and version==result['version']
    return {'schema_version':'sunlight.research.packet.v1',**result,'audit':audit,'documents':originals,
            'integrity':{'content_chain_and_originals_valid':bool(valid),'audit_head':previous,'limit':'Local content integrity, not a publisher signature, certified provenance, verified model reasoning or protection against an owner rewriting the entire ledger.'}}
