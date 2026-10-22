"""Escaped, self-contained human reports derived from retained evidence packets."""
from html import escape
from urllib.parse import urlsplit
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router=APIRouter(tags=['Readable evidence reports'])

def e(value):
    return escape(str(value if value is not None else 'Unknown'))

def label(value):
    return e(value).replace('_',' ')

def link(url,text='Source document'):
    if not isinstance(url,str):return e(text)
    valid=(urlsplit(url).scheme in ('http','https') and bool(urlsplit(url).netloc)) or (url.startswith('/') and not url.startswith('//') and '\\' not in url)
    return f'<a href="{e(url)}" target="_blank" rel="noreferrer">{e(text)}</a>' if valid else e(text)

def fields(items):
    return '<dl>'+''.join(f'<dt>{e(k)}</dt><dd>{e(v)}</dd>' for k,v in items)+'</dl>'

def table(headers,rows):
    return '<div class="table"><table><thead><tr>'+''.join('<th>'+e(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(cell)+'</td>' for cell in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def page(title,body,reference):
    css='body{background:#edf2f4;color:#18333f;font:15px/1.7 system-ui,sans-serif;margin:0}main{background:white;max-width:1000px;margin:28px auto;padding:38px 5vw}h1{font-size:30px;line-height:1.3}h2{font-size:20px;margin-top:32px;border-top:1px solid #c5d3d9;padding-top:18px}h3{font-size:16px}a{color:#14647b;overflow-wrap:anywhere}p,dd,td,code{overflow-wrap:anywhere}dt{font-weight:600}dd{margin:2px 0 12px}dl{columns:2;column-gap:35px}dl dt,dl dd{break-inside:avoid}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border:1px solid #c5d3d9;padding:10px;text-align:left;vertical-align:top}th{background:#e9f0f3}.table{overflow:auto}.notice{border-left:3px solid #b58b3f;background:#fff9eb;padding:12px 18px}.excerpt{white-space:pre-wrap}button{padding:10px 16px;background:#173d4b;color:white;border:0;border-radius:3px;cursor:pointer}.top{display:flex;justify-content:space-between;align-items:center;gap:16px}.brand{letter-spacing:.16em;font-size:13px}small{color:#536e7a}article{border-bottom:1px solid #d3dfe4;padding:10px 0}code{font-size:10px}@media(max-width:650px){main{margin:0;padding:24px 18px}dl{columns:1}.top{flex-wrap:wrap}}@media print{@page{size:A4;margin:18mm}body,main{background:white;margin:0;padding:0;font-size:10pt}.no-print{display:none}h2,h3{break-after:avoid}tr{break-inside:avoid}.table{overflow:visible}a{color:#18333f;text-decoration:underline}a:after{content:" [" attr(href) "]";font-size:8pt}dl{columns:1}}'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><style>'+css+'</style></head><body><main><div class="top"><strong class="brand">SUNLIGHT / EVIDENCE REVIEW</strong><button class="no-print" onclick="window.print()">Print / save as PDF</button></div><h1>'+e(title)+'</h1><p><small>'+e(reference)+'</small></p>'+body+'<h2>Interpretation</h2><p>This brief describes retained source claims and calculations. A discrepancy is a review lead, not a finding of theft. Hashes check local content integrity; they do not authenticate publishers. Scope and source periods remain part of every conclusion.</p></main></body></html>'


def measurement(value):
    if not value:return 'Unknown — no observation supplied'
    return f"{value['value']} {value['currency'] or value['unit']}"


@router.get('/assurance/obligations/{oid}/report', response_class=HTMLResponse)
def assurance_report(oid: str):
    from delivery_assurance import export_obligation
    packet = export_obligation(oid)
    c = packet['current']; o = c['obligation']; a = c['assessment']
    body = '<p class="notice">' + ('SYNTHETIC WORKED EXAMPLE · ' if o['synthetic'] else '') + e(a['limitations']) + '</p>'
    body += fields([('Obligation', o['reference']), ('Public promise', o['promise']), ('Community / intended recipients', o['community']),
                    ('Recipient organization', o['recipient']), ('Programme owner label', o['owner']), ('Country / origin', o['country']+' / '+str(o['origin_country'] or 'Unspecified')),
                    ('Deadline', o['due_at']), ('Budget context (not a debit)', str(o['budget'])+' '+str(o['currency']) if o['budget'] is not None else 'Not supplied'),
                    ('Evidence / review version', c['version']), ('Assessed at', a['as_of'])])
    body += '<p>' + link(o['baseline_url'], 'Obligation baseline') + ' · ' + link('/watch/?obligation='+oid+'#delivery', 'Open delivery workspace') + '</p>'
    body += '<h2>Origin-to-arrival reconciliation</h2><p>Each row is one declared transfer identity and its attributable ledger entries. Credits may be partial. Pre-credit deductions remain submitted claims. Matching claimed amounts does not authenticate either issuer.</p>'
    body += table(['Transfer / parties', 'Currency', 'Sent', 'Recorded arrival', 'Submitted pre-credit deductions', 'Raw difference', 'Residual / state'],
                  [[t['transfer_id']+' · '+t['sender_id']+' → '+t['recipient_id'], t['currency'], t['sent'], t['received'], t['deductions'], t['raw_difference'], (t['residual'] if t['residual'] is not None else 'Not calculable')+' / '+t['state'].replace('_',' ')] for t in a['transfers']])
    if not a['transfers']: body += '<p>No executed debit or recipient credit is recorded. A budget does not establish release or arrival.</p>'
    body += '<h2>Physical delivery and service outcomes</h2>' + table(['Stage', 'Target / unit', 'Observed', 'Coverage through', 'Shortfall', 'State'],
                  [[s['kind'], str(s['target']['value'])+' '+s['target']['unit'] if s['target'] else 'No target', s['observed'], s['covers_through'], s['shortfall'], s['state']] for s in a['stages']])
    body += '<p>Latest cumulative reports are not added together. Different issuer reports, units and coverage times can block comparison. Payment, receipt, acceptance and service outcomes are separate facts; none establishes causation.</p>'
    body += '<h2>Where to look next</h2>'
    for s in a['signals']:
        body += '<article><h3>'+e(s['title'])+'</h3><p>'+e(s['reason'])+'</p><p>Next evidence: '+e(s['next_step'])+'</p></article>'
    if not a['signals']: body += '<p>Recorded stages meet the configured comparison conditions. Independent issuer authentication and field verification are still required.</p>'
    body += '<h2>Calibrated delivery engine</h2>'
    for run in c['analyses']:
        body += '<article><h3>'+e(run['profile'])+'</h3><p>Evidence basis current: '+e(run['basis_current'])+' · '+e(run['created_at'])+'</p><p>'+e(run['scope'])+'</p>'
        for finding in run['result'].get('fired_rules', []):
            body += '<p><strong>'+e(finding.get('rule_id'))+'</strong> '+e(finding.get('evidence') or finding.get('description'))+'</p>'
        if not run['result'].get('fired_rules'): body += '<p>No rules fired for the supplied comparable dimensions. This does not verify delivery.</p>'
        body += '</article>'
    if not c['analyses']: body += '<p>No calibrated delivery run recorded. Exact comparisons above remain available.</p>'
    body += '<h2>Accountable follow-up</h2>' + table(['Action', 'Responsible label / due', 'Status', 'Latest note / completion evidence'],
                  [[x['title'], x['owner']+' / '+x['due_at'], x['status'], x['note']+' / '+str(x.get('completion_evidence_id'))] for x in c['actions']])
    body += '<p>Follow-ups are local review records. Completing an action does not erase a discrepancy or execute a payment intervention.</p><h2>Evidence register</h2>'
    for x in c['evidence']:
        body += '<article><h3>'+label(x['kind'])+' · '+e(x['value'])+' '+e(x['currency'] or x['unit'])+'</h3>'
        body += fields([('Evidence identifier', x['id']), ('Declared issuer', x['issuer_name']+' / '+x['issuer_id']), ('Ledger entry reference', x['ledger_reference']),
                        ('Observed / value time', x['observed_at']), ('Cumulative coverage', x['covers_through']), ('Received by SUNLIGHT', x['created_at']),
                        ('Superseded by', x['superseded_by'] or 'Current'), ('Note', x['note']), ('Payload SHA-256', x['payload_hash'])])
        body += '<p>'+link(x['document_url'])+'</p></article>'
    body += '<h2>Evidence and follow-up history</h2>' + table(['Version', 'Time', 'Event'], [[i+1, h['payload']['at'], label(h['payload']['action'])] for i,h in enumerate(packet['history'])])
    body += '<h2>Integrity</h2><p>Local history and retained content check: '+e(packet['integrity']['local_chain_and_content_valid'])+'</p><p>'+e(packet['integrity']['meaning'])+'</p><p>'+link('/assurance/obligations/'+oid+'/export', 'Advanced audit packet')+'</p>'
    return HTMLResponse(page(o['title'], body, 'Delivery assurance brief · '+oid), headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


@router.get('/operations/cases/{case_id}/report',response_class=HTMLResponse)
def operation_report(case_id:str):
    from operations import export_case
    packet=export_case(case_id);c=packet['current'];r=c['record'];v=c['comparison']
    body='<p class="notice">'+label(v['state'])+': '+e(v['reason'])+'</p>'
    body+=fields([('Case',case_id),('Source',packet['source']['name']),('Source revision',c['revision']),('Contract / item',r['contract_id']+' / '+r['item_id']),('Origin → destination',r['origin_country']+' → '+r['destination_country']),('Category / metric',r['category']+' / '+r['expected']['metric']),('Covered period',r['expected']['period_start']+' — '+r['expected']['period_end']),('Due',r['expected']['due_at']),('Source published',r['published_at']),('Received by SUNLIGHT',c['received_at']),('Observation date',r['observed']['observed_at'] if r['observed'] else None),('Assessment as of',packet['exported_at'])])
    body+='<h2>Measurement and calculation</h2>'+table(['Measure','Value'],[['Expected baseline',measurement(r['expected'])],['Reported observation',measurement(r['observed'])],['Comparable shortfall',str(v['gap'])+' '+str(v['currency'] or v['unit']) if v['gap'] is not None else 'Not calculable'],['Shortfall percentage',str(v['gap_percent'])+'%' if v['gap_percent'] is not None else 'Not calculable'],['Overage (separate)',v['overage'] if v['overage'] is not None else 'Not calculable']])
    body+='<p>'+link(r['expected']['document_url'],'Baseline document')+(' · '+link(r['observed']['document_url'],'Observation document') if r['observed'] else '')+'</p>'
    body+='<p>Shortfall = max(expected − observed, 0) only when unit, currency, metric, period and deadline conditions permit comparison. Unknown observations remain unknown. Overages do not offset shortfalls.</p><h2>Engine findings on supplied evidence</h2>'
    for name,result in c['analysis'].items():
        if name not in ('procurement','delivery'):continue
        body+='<h3>'+label(name)+'</h3>'
        if not result:body+='<p>Not run for the supplied record and comparable dimensions.</p>';continue
        body+='<p>Stage: '+label(result.get('stage','reported'))+'</p>'
        findings=result.get('fired_rules') or (result.get('structure') or {}).get('contradictions') or []
        if not findings:body+='<p>No rule-level findings reported for these supplied dimensions. Statistical recommendations and evidence-gate outcomes remain separate; missing evidence is not verified.</p>'
        for f in findings:body+='<article><strong>'+e(f.get('rule_id'))+'</strong><p>'+e(f.get('evidence') or f.get('description'))+'</p><small>'+e(f.get('legal_basis') or f.get('legal_citation'))+'</small></article>'
        if name=='procurement':
            body+='<p>Applicable profile: '+e(result.get('profile_used'))+'. Structural verdict: '+e((result.get('structure') or {}).get('verdict'))+'. Investigation recommendation: '+('statistical check recommends examination' if result.get('recommended_for_investigation') else 'no recommendation in this output')+'. Evidence gate: '+e(result.get('gate_verdict'))+'. Single-contract output has no portfolio-capacity context; no probability of theft or independently verified delivery is implied.</p>'
        for error in result.get('errors') or []:body+='<p>Engine limitation: '+e(error)+'</p>'
    review=c['review'];body+='<h2>Review and next evidence</h2>'+fields([('Status',review['status']),('Following',review['followed']),('Analyst label',review['owner']),('Latest note',review.get('note') or 'No review note recorded')])
    body+='<p>Confirm baseline amendments and receipt cut-off dates. Reconcile dispatch, receiving, inspection, invoice, payment and custody records for the same item and period. Obtain independent acceptance evidence before alleging loss or theft.</p>'
    body+='<h2>Source versions</h2>'+table(['Revision','Published','Received','Payload hash'],[[x['revision'],x['published_at'],x['received_at'],x['payload_hash']] for x in packet['revisions']])
    body+='<h2>Review history</h2>'
    for a in packet['audit']:
        p=a['payload'];d=p['detail']
        if p['action'] in ('review_updated','review_reopened'):body+='<article><strong>'+label(p['action'])+'</strong><p>'+e(p['at'])+'</p>'+fields([(label(k),val) for k,val in d.items()])+'</article>'
    body+='<h2>Integrity and technical evidence</h2><p>Local chain and content check: '+e(packet['integrity']['chain_and_content_valid'])+'</p><p>'+link('/operations/cases/'+case_id+'/export','Advanced machine-readable audit packet')+'</p>'
    return HTMLResponse(page(r['title'],body,'Operational case brief · '+case_id),headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@router.get('/research/inquiries/{inquiry_id}/report',response_class=HTMLResponse)
def research_report(inquiry_id:str):
    from research import export_inquiry
    p=export_inquiry(inquiry_id);r=p['report'];s=r['scope']
    body=fields([('Created',r['created_at']),('Countries',', '.join(s['country_names']) or 'No country filter'),('Reference years',str(s['year_start'] or 'Earliest covered')+' — '+str(s['year_end'] or 'Latest covered')),('Community/place',s.get('community') or 'Not specified'),('Review status',p['state']['status']),('Following',p['state']['followed']),('AI status',r['ai']['status']),('Latest review note',p['state']['note'])])
    body+='<h2>Scope and missing evidence</h2><ul>'+''.join('<li>'+e(g['text'])+'</li>' for g in r['gaps'])+'</ul>'
    synthesis=r['ai'].get('synthesis')
    if synthesis:
        body+='<h2>AI interpretation — analyst review required</h2><p>'+e(r['ai'].get('citation_check'))+'</p>'
        for item in synthesis['interpretations']:body+='<article><p>'+e(item['text'])+'</p><small>Citations: '+e(', '.join(item['citation_ids']))+'</small></article>'
        body+='<h3>Hypotheses to test</h3>'
        for item in synthesis['hypotheses']:body+='<article><p>'+e(item['text'])+'</p><p>Alternatives: '+e('; '.join(item['alternative_explanations']))+'</p><p>Evidence needed: '+e('; '.join(item['evidence_needed']))+'</p><small>Citations: '+e(', '.join(item['citation_ids']))+'</small></article>'
        body+='<h3>Open questions and model limitations</h3><ul>'+''.join('<li>'+e(v)+'</li>' for v in synthesis['questions_to_resolve']+synthesis['limitations'])+'</ul>'
    body+='<h2>Evidence and calculated results</h2>'
    for f in r['facts']:
        body+='<article><h3>'+e(f['title'])+'</h3><small>'+label(f['source'])+' · citation '+e(f['id'])+'</small><p class="excerpt">'+e(f['text'])+'</p>'
        body+='<p>'+ ' · '.join(link(url,'Source reference '+str(i+1)) for i,url in enumerate(f.get('source_urls') or [f['source_url']]))+'</p></article>'
    body+='<h2>Documents</h2>'+table(['Document','Pages','Extraction','Original SHA-256'],[[d['filename'],d['page_count'],d['status'],d['sha256']] for d in r['documents']])
    body+='<h2>Next investigative steps</h2><ol>'+''.join('<li>'+e(v)+'</li>' for v in r['review_plan'])+'</ol>'
    body+='<h2>Review history</h2>'+table(['Version','Date','Status','Note'],[[x['version'],x['at'],x['status'],x['note']] for x in p['review_history']])
    body+='<h2>Integrity and technical evidence</h2><p>Report SHA-256: <code>'+e(p['report_hash'])+'</code></p><p>Local content chain and original documents check: '+e(p['integrity']['content_chain_and_originals_valid'])+'</p><p>'+link('/research/inquiries/'+inquiry_id+'/export','Advanced machine-readable evidence packet')+'</p>'
    return HTMLResponse(page(r['request']['question'],body,'Saved investigation brief · '+inquiry_id),headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
