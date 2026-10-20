"""Read-only institutional work queue, derived from current registered evidence.

No geographic risk score, cross-currency loss total or automatic intervention.
Review state and evidence condition are deliberately separate.
"""
from collections import Counter
from datetime import datetime
from decimal import Decimal
from html import escape
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from delivery_assurance import assurance_connection, bundle
from operations import format_case, utcnow
from watch_money import COUNTRIES

router=APIRouter(prefix='/workbench',tags=['Institutional review'])
PRIORITIES={'reconcile':0,'overdue_followup':1,'evidence':2,'planned':3,'reviewed':4}
PRIORITY_LABELS={'reconcile':'Reconcile a measured difference','overdue_followup':'Follow up an overdue action','evidence':'Obtain or reconcile evidence','planned':'Prepare the next check','reviewed':'Review recorded · source condition retained'}
RULE='Measured comparable differences first, then overdue follow-ups, evidence issues and planned checks; within a tier, earliest due time then stable record ID. No ranking by country, wealth, conflict or cross-currency amount.'


def instant(value):
    return datetime.fromisoformat(value)


def delivery_item(record,now):
    o=record['obligation'];a=record['assessment'];signals=a['signals']
    open_actions=[action for action in record['actions'] if action['status']!='completed']
    if not signals and not open_actions:return None
    measurements=[]
    for transfer in a['transfers']:
        if transfer['residual'] is not None and Decimal(transfer['residual'])!=0:
            measurements.append({'label':'Settled claim residual','value':transfer['residual'],'unit':'currency','currency':transfer['currency'],'reference':transfer['transfer_id']})
    for stage in [a['accepted'],a['outcome']]:
        if stage['shortfall'] is not None and Decimal(stage['shortfall'])>0:
            measurements.append({'label':stage['kind'].capitalize()+' shortfall','value':stage['shortfall'],'unit':stage['target']['unit'],'currency':None,'reference':o['reference']})
    overdue=[action for action in open_actions if instant(action['due_at'])<now]
    pending_settlement=bool(a['transfers']) and all(t['state']=='awaiting_settlement' for t in a['transfers']) and all(s['stage']=='funds' for s in signals)
    priority='reconcile' if measurements else 'overdue_followup' if overdue else 'planned' if instant(o['due_at'])>now or pending_settlement else 'evidence'
    current=[run for run in record['analyses'] if run['basis_current']]
    engine='current' if current else 'stale' if record['analyses'] else 'not_run'
    next_step=signals[0]['next_step'] if signals else 'Review the assigned follow-up and retain evidence supporting completion.'
    return {'id':record['id'],'kind':'delivery','version':record['version'],'title':o['title'],'reference':o['reference'],
        'country':o['country'],'origin_country':o.get('origin_country'),'community':o['community'],
        'priority':priority,'priority_label':PRIORITY_LABELS[priority],'due_at':min((action['due_at'] for action in overdue),key=instant) if overdue else o['due_at'],
        'condition':a['state'],'issues':signals,'issue_count':len(signals),'next_step':next_step,'measurements':measurements,
        'programme_owner':o['owner'],'owners':sorted({action['owner'] for action in open_actions}),
        'assigned':bool(open_actions),'open_actions':len(open_actions),'overdue_actions':len(overdue),
        'review_state':'followups_open' if open_actions else 'no_followup_assigned' if signals else 'no_open_followup',
        'engine_state':engine,'engine_note':'Latest checks use the current acceptance basis.' if current else 'Acceptance evidence changed; rerun the calibrated check.' if record['analyses'] else 'Calibrated acceptance check has not been run.',
        'evidence_basis':'Submitted references; issuer identity and bank/field evidence are not independently authenticated.',
        'updated_at':record['updated_at'],'synthetic':o['synthetic'],'report_url':'/assurance/obligations/'+record['id']+'/report',
        'record_url':'/watch/?obligation='+record['id']+'#delivery',
        'lenses':sorted({'oversight',*('finance' for s in signals if s['stage']=='funds'),*('delivery' for s in signals if s['stage']!='funds'),*('finance' if action['kind']=='financial_review' else 'delivery' for action in open_actions)})}


def operational_item(case,now):
    r=case['record'];c=case['comparison'];review=case['review'];analysis=case['analysis']
    engines=[analysis[k] for k in ('procurement','delivery') if analysis.get(k) is not None]
    findings=sum(len(e.get('fired_rules') or (e.get('structure') or {}).get('contradictions',[])) for e in engines)
    errors=any(e.get('errors') for e in engines)
    recommended=any(e.get('recommended_for_investigation') is True for e in engines)
    gate_review=any(e.get('gate_verdict') in ('yellow','red') for e in engines)
    exceptional=recommended or gate_review or c['state'] not in ('matched','not_due') or findings or errors or case['baseline_change']
    if not exceptional and review['status'] not in ('in_review','awaiting_evidence'):return None
    reviewed=review['status']=='resolved'
    priority='reviewed' if reviewed else 'reconcile' if c['state'] in ('shortfall','overage') else 'planned' if c['state']=='not_due' else 'evidence'
    instructions={
      'not_comparable':'Reconcile metric, unit, currency and covered period before subtracting any values.',
      'missing_observation':'Obtain an attributed cumulative observation covering the deadline; missing is not zero.',
      'awaiting_due_observation':'Obtain an updated cumulative observation covering the deadline.',
      'shortfall':'Inspect the source baseline and receiving/acceptance record, then record the review owner and next evidence required.',
      'overage':'Check scope, amendments, returns and classification before interpreting the reported overage.',
      'not_due':'Prepare the receiving and inspection evidence required at the stated deadline.',
      'matched':'Inspect engine findings and the current source revision; matching reported values do not verify delivery.'}
    measured=[]
    for name,key in [('Comparable shortfall','gap'),('Reported overage','overage')]:
        if c.get(key) is not None and Decimal(c[key])>0:measured.append({'label':name,'value':c[key],'unit':c['unit'],'currency':c['currency'],'reference':r['item_id']})
    issues=[{'key':'comparison','title':c['state'].replace('_',' ').capitalize(),'reason':c['reason'],'next_step':instructions[c['state']],'stage':'comparison'}]
    if case['baseline_change']:issues.append({'key':'baseline','title':'Baseline amended','reason':'The source changed the expected measure or classification. Review the retained earlier revision.','next_step':'Inspect the amendment and previous baseline in the case history.','stage':'baseline'})
    if recommended or gate_review:issues.append({'key':'engine_decision','title':'Attached engine recommendation or evidence gate needs review','reason':'The stored statistical recommendation or yellow/red evidence gate requests examination. It is not a theft finding or a worldwide priority score.','next_step':'Inspect the applicable profile, structural verdict, supplied evidence and gate dimensions in the dossier.','stage':'engine'})
    if findings or errors:issues.append({'key':'engine','title':f'{findings} attached engine findings'+(' · engine errors need review' if errors else ''),'reason':'Inspect actual rules and applicable profile in the dossier. A finding is a review lead, not an allegation.','next_step':'Review source inputs, rule evidence and calibration basis.','stage':'engine'})
    return {'id':case['case_id'],'kind':'operations','version':case['revision'],'title':r['title'],'reference':r['contract_id']+' / '+r['item_id'],
       'country':r['destination_country'],'origin_country':r['origin_country'],'community':'','priority':priority,'priority_label':PRIORITY_LABELS[priority],
       'due_at':r['expected']['due_at'],'condition':c['state'],'issues':issues,'issue_count':len(issues),'next_step':issues[0]['next_step'],'measurements':measured,
       'programme_owner':'','owners':[review['owner']] if review.get('owner') else [],'assigned':bool(review.get('owner')),
       'open_actions':0,'overdue_actions':0,'review_state':review['status'],
       'engine_state':'errors' if errors else 'current' if engines else 'inputs_missing',
       'engine_note':f'{len(engines)} engine output(s) attached to source revision {case["revision"]}; {findings} findings.' if engines else 'No eligible calibrated inputs were supplied. No clean verdict is inferred.',
       'evidence_basis':'Source-declared expectation and observation; independent attribution remains to be checked.',
       'updated_at':case['received_at'],'synthetic':False,'source_id':case['source_id'],
       'report_url':'/operations/cases/'+case['case_id']+'/report','record_url':'/watch/?case='+case['case_id']+'#operations',
       'lenses':sorted({'oversight','finance' if c['metric']=='payment' else 'delivery' if c['metric']=='delivery' else 'procurement',*('procurement' for _ in [1] if analysis.get('procurement') is not None),*('delivery' for _ in [1] if analysis.get('delivery') is not None)})}


def queue(country='',q='',lens='all',source='all',include_reviewed=False,unassigned=False,synthetic=False,limit=30,offset=0,now=None):
    if country and country not in COUNTRIES:raise HTTPException(422,'Recognized country ISO code required')
    now=now or utcnow();items=[];registered={'delivery':0,'operations':0};condition_counts=Counter()
    # Both ledgers use the same SQLite file. Hold one read snapshot while deriving
    # the queue; source writers cannot create a mixed-revision response.
    with assurance_connection() as db:
        db.execute('BEGIN')
        if source in ('all','delivery'):
            rows=db.execute('SELECT * FROM assurance_obligations WHERE json_extract(payload,\'$.synthetic\')=? ORDER BY id',(int(synthetic),)).fetchall()
            for row in rows:
                o=json.loads(row['payload'])
                if country and country not in (o['country'],o.get('origin_country')):continue
                registered['delivery']+=1
                record=bundle(db,row,now);condition_counts[record['assessment']['state']]+=1
                item=delivery_item(record,now)
                if item:items.append(item)
        if not synthetic and source in ('all','operations'):
            rows=db.execute('SELECT r.* FROM op_revisions r JOIN (SELECT case_id,MAX(revision) revision FROM op_revisions GROUP BY case_id) c ON r.case_id=c.case_id AND r.revision=c.revision ORDER BY r.case_id').fetchall()
            for row in rows:
                r=json.loads(row['payload'])
                if country and country not in (r['origin_country'],r['destination_country']):continue
                registered['operations']+=1
                case=format_case(db,row,now);condition_counts[case['comparison']['state']]+=1
                item=operational_item(case,now)
                if item:items.append(item)
    items=[i for i in items if (lens=='all' or lens in i['lenses']) and (not q or q.casefold() in json.dumps(i,ensure_ascii=False).casefold()) and (not unassigned or not i['assigned'])]
    review_complete=sum(i['priority']=='reviewed' for i in items)
    if not include_reviewed:items=[i for i in items if i['priority']!='reviewed']
    items.sort(key=lambda i:(PRIORITIES[i['priority']],instant(i['due_at']),i['kind'],i['id']))
    return {'as_of':now.isoformat(),'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit,
       'priority_counts':dict(Counter(i['priority'] for i in items)),'unassigned':sum(not i['assigned'] for i in items),
       'overdue_actions':sum(i['overdue_actions'] for i in items),'reviewed_source_conditions':review_complete,'registered':registered,
       'condition_counts':dict(condition_counts),'ranking_rule':RULE,'synthetic':synthetic,'country':country,
       'coverage':'All currently registered records in the selected deployment/country and record-type scope are assessed before pagination. This is not worldwide spending coverage. Review labels and completed actions do not authenticate or erase source conditions.',
       'aggregate_loss':None,'authority':'Read-only triage. Assignments are labels, not authenticated institutional roles; no payment, sanction, external referral or stop order is executed.'}


@router.get('/review-queue')
def review_queue(country:str='',q:str=Query('',max_length=200),lens:Literal['all','finance','delivery','procurement','oversight']='all',
                 source:Literal['all','delivery','operations']='all',include_reviewed:bool=False,unassigned:bool=False,synthetic:bool=False,
                 limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0)):
    return queue(country,q,lens,source,include_reviewed,unassigned,synthetic,limit,offset)


@router.get('/review-queue/report',response_class=HTMLResponse)
def queue_report(country:str='',q:str=Query('',max_length=200),lens:Literal['all','finance','delivery','procurement','oversight']='all',
                 source:Literal['all','delivery','operations']='all',include_reviewed:bool=False,unassigned:bool=False,synthetic:bool=False):
    data=queue(country,q,lens,source,include_reviewed,unassigned,synthetic,500,0)
    e=lambda value:escape(str(value))
    body=f'<h1>Institutional review work</h1><p>Assessed {e(data["as_of"])} · country {e(country or "all registered countries")} · work focus {e(lens)} · record type {e(source)} · synthetic examples {synthetic}.</p>'
    body+=f'<p>{data["total"]} matching review records; {data["unassigned"]} without an assigned follow-up/reviewer; {data["overdue_actions"]} overdue follow-ups. Showing {len(data["items"])} of {data["total"]} records, up to 500; refine country/task filters if more are required.</p><p>{e(data["ranking_rule"])}</p>'
    for item in data['items']:
        body+=f'<article><p>{e(item["priority_label"])} · {e(item["kind"])} · record version {item["version"]}</p><h2>{e(item["title"])}</h2><p>{e(item["reference"])} · {e(item["country"])}</p><p><strong>Next evidence:</strong> {e(item["next_step"])}</p><p>Deadline: {e(item["due_at"])}. Assigned owner(s): {e(", ".join(item["owners"]) or "Unassigned")}. Programme owner: {e(item["programme_owner"] or "Not recorded")}.</p><p>{e(item["engine_note"])} Review: {e(item["review_state"])}. {e(item["evidence_basis"])}</p>'
        for m in item['measurements']:body+=f'<p>{e(m["label"])}: {e(m["value"])} {e(m["currency"] or m["unit"])} · {e(m["reference"])}. Claim-based comparison; no cross-record sum.</p>'
        body+=f'<p><a href="{e(item["report_url"])}">Full source and review brief</a> · <a href="{e(item["record_url"])}">Open working dossier</a></p></article>'
    body+=f'<h2>Scope and authority</h2><p>{e(data["coverage"])}</p><p>{e(data["authority"])}</p><p>Work-focus filters do not grant access roles. A completed review does not erase an underlying source discrepancy. No combined loss or global theft total is computed.</p>'
    css='body{font:14px/1.65 system-ui;color:#17313e;max-width:960px;padding:30px;margin:auto}article{border-top:1px solid #b6c9d0;padding:16px 0}h1{font-size:28px}h2{font-size:19px}a{color:#176778}button{padding:9px}p{overflow-wrap:anywhere}@media print{@page{size:A4;margin:18mm}body{padding:0;font-size:10pt}button{display:none}h2{break-after:avoid}}'
    return HTMLResponse(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SUNLIGHT review work brief</title><style>{css}</style><strong>SUNLIGHT / REVIEW WORK</strong><button onclick="window.print()">Print / save as PDF</button>{body}</html>',headers={'Cache-Control':'no-store'})
