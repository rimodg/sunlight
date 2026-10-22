"""Run inside an isolated local test appliance; creates fictional validation records.

Pipe to `docker exec -i CONTAINER python -`. Repeat with `python - --resume`
after replacing the container while retaining its validation state volume.
"""
import hashlib
import json
from pathlib import Path
import sys
import uuid

import httpx

client=httpx.Client(base_url='http://127.0.0.1:8000',timeout=60)
state=Path('/app/calibration/offline-verification.json')


def request(method,path,**kwargs):
    response=client.request(method,path,**kwargs)
    assert response.is_success,(path,response.status_code,response.text[:500])
    return response


def pdf():
    text=b'BT /F1 12 Tf 20 700 Td (Offline validation: Ghana accepted 73 kits.) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Count 1 /Kids [3 0 R] >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents 4 0 R >>',
             f'<< /Length {len(text)} >>\nstream\n'.encode()+text+b'\nendstream']
    body=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(body));body+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(body);body+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    for n in offsets[1:]:body+=f'{n:010d} 00000 n \n'.encode()
    return body+f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


status=request('GET','/offline/status').json();assert status['offline_policy']
request('GET','/watch/');request('GET','/watch-data/money/analysis?measure=goods_exports&countries=GH&year=2023')
if '--resume' in sys.argv:
    saved=json.loads(state.read_text())
    report=request('GET','/assurance/obligations/'+saved['obligation']).json()
    assert report['assessment']['transfers'][0]['residual']=='40'
    assert request('GET','/research/inquiries/'+saved['inquiry']).json()['content_valid']
    original=request('GET','/research/documents/'+saved['document']+'/file').content
    assert hashlib.sha256(original).hexdigest()==saved['pdf_sha256']
    print(json.dumps({'replaced_container_records_retained':True,'exact_residual':True,'document_original':True,'saved_inquiry':True}))
    raise SystemExit(0)

stamp=uuid.uuid4().hex
current=request('POST','/assurance/obligations',json={
    'reference':'offline-validation-'+stamp,'title':'Isolated offline medical kit validation','sector':'Health','country':'GH','origin_country':'NL',
    'community':'Fictional validation site','promise':'Accept 100 kits','owner':'Validation operator','recipient':'Validation receiving office',
    'baseline_url':'https://example.org/offline-validation','due_at':'2025-10-01T00:00:00Z','delivery_target':{'value':'100','unit':'kit'},'budget':'1000','currency':'USD'}).json()
oid=current['id']
for kind,value in [('funds_sent','1000'),('funds_received','960'),('accepted','73')]:
    funds=kind.startswith('funds_')
    current=request('POST','/assurance/obligations/'+oid+'/evidence',json={
        'expected_version':current['version'],'kind':kind,'value':value,'unit':'currency' if funds else 'kit','currency':'USD' if funds else None,
        'issuer_id':'sender' if kind=='funds_sent' else 'recipient' if funds else 'inspector','issuer_name':'Validation issuer',
        'note':'Isolated fictional offline verification record.',
        'ledger_reference':stamp+'-'+kind,'document_url':'https://example.org/'+kind,'observed_at':'2025-10-02T00:00:00Z',
        'transfer_id':stamp if funds else None,'sender_id':'sender' if funds else None,'recipient_id':'recipient' if funds else None,
        'settlement_due_at':'2025-10-03T00:00:00Z' if kind=='funds_sent' else None,'covers_through':None if funds else '2025-10-02T00:00:00Z'}).json()
assert current['assessment']['transfers'][0]['residual']=='40'
assert current['assessment']['accepted']['shortfall']=='27'
analysed=request('POST','/assurance/obligations/'+oid+'/delivery-analysis',json={'expected_version':current['version'],'profile':'us_federal'}).json()
assert analysed['analyses']
original=pdf();doc=request('POST','/research/documents?filename=offline-validation.pdf',content=original,headers={'Content-Type':'application/pdf'}).json()
inquiry=request('POST','/research/inquiries',json={'question':'Investigate Ghana kit acceptance and source coverage in this offline validation',
    'country_codes':['GH'],'sources':['monetary','delivery_assurance'],'document_ids':[doc['id']],'obligation_ids':[oid]}).json()
assert inquiry['report']['facts']
request('GET','/assurance/obligations/'+oid+'/report')
checkpoint=Path('/app/calibration/validation-checkpoint.zip');checkpoint.write_bytes(request('GET','/offline/checkpoint').content)
from portable_checkpoint import verify_checkpoint,restore_checkpoint
manifest=verify_checkpoint(checkpoint)
destination=Path('/app/calibration/restored-'+stamp)
restore_checkpoint(checkpoint,destination)
import sqlite3
with sqlite3.connect(destination/'operations.sqlite3') as db:
    stored=db.execute('SELECT original FROM research_documents WHERE id=?',(doc['id'],)).fetchone()[0]
    assert stored==original
state.write_text(json.dumps({'obligation':oid,'document':doc['id'],'inquiry':inquiry['report']['id'],'pdf_sha256':hashlib.sha256(original).hexdigest()}))
print(json.dumps({'offline_policy':True,'money_analysis':True,'exact_funds_reconciliation':True,'acceptance_gap':True,'calibrated_delivery_engine':True,
                  'actual_pdf_extraction':True,'saved_cited_inquiry':True,'readable_brief':True,'checkpoint_and_restore':True,'files_verified':len(manifest['entries'])}))
