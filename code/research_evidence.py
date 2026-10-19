"""Deterministic, bounded retrieval. Facts remain separate from model interpretation."""
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
from functools import lru_cache
import json
import heapq
from pathlib import Path
import re
import unicodedata

from operations import FlowRevision, compare
from watch_procurement import SNAPSHOT as PROCUREMENT
from watch_materials import SNAPSHOT as MATERIALS
from watch_arms import SNAPSHOT as ARMS
from watch_conflicts import SNAPSHOT as CONFLICTS

COUNTRIES=json.loads(Path(__file__).with_name('research_countries.json').read_text())
BY_CODE={c['code']:c for c in COUNTRIES}
BY_ALPHA3={c['alpha3']:c for c in COUNTRIES}
BY_NUMERIC={int(c['numeric']):c for c in COUNTRIES if c['numeric']}
SOURCE_LABELS={'procurement':'Published procurement','materials':'Material exports','arms':'Arms declarations','conflicts':'Recorded violence','operations':'Operational cases','goods_trade':'Goods trade preview','delivery_assurance':'Delivery obligations & arrival evidence'}
STOP=set('the a an in on at to of for and or is are was were be been how why what where when which with from between about investigate investigation analyze analyse community economic economics economy movement flow procurement trade global world show explain please document documents evidence'.split())


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text).casefold() if not unicodedata.combining(c)).translate(str.maketrans({'’':"'",'‘':"'",'–':'-','‑':'-'}))


def tokens(text):
    return {w for w in re.findall(r'\w+',normalized(text)) if len(w)>2 and w not in STOP}


def infer_scope(question,requested_codes,start,end):
    inferred=[];ambiguous=[]
    names={}
    for c in COUNTRIES:
        for name in [c['name'],c['official'],*c['aliases']]:
            if len(name)>=4:
                names.setdefault(normalized(name),set()).add(c['code'])
    text=normalized(question)
    hits=[]
    common={normalized(c['name']):c['code'] for c in COUNTRIES}
    for name,codes in names.items():
        for match in re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',text):
            hits.append((match.start(),match.end(),name,{common[name]} if name in common else codes))
    occupied=[]
    for start_at,end_at,name,matches in sorted(hits,key=lambda h:-(h[1]-h[0])):
        if any(start_at<right and end_at>left for left,right in occupied):continue
        occupied.append((start_at,end_at))
        if len(matches)==1:inferred.extend(matches)
        else:ambiguous.append(name)
    for alpha3 in re.findall(r'\b[A-Z]{3}\b',question):
        if alpha3 in BY_ALPHA3:inferred.append(BY_ALPHA3[alpha3]['code'])
    codes=list(dict.fromkeys(requested_codes or inferred))
    # An ambiguous short alias cannot override an explicit/unambiguous country selection.
    years=sorted({int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b',question) if 1992<=int(y)<=datetime.now(timezone.utc).year})
    inferred_years=not(start or end) and bool(years)
    if inferred_years:start,end=min(years),max(years)
    return {'countries':codes,'country_names':[BY_CODE[c]['name'] for c in codes],
            'country_inference':'explicit selection' if requested_codes else 'unambiguous full-name/alias match' if codes else 'no country filter',
            'ambiguous_names':sorted(set(ambiguous)), 'year_start':start,'year_end':end,'years_inferred_from_question':bool(inferred_years)}


def period_matches(year,scope):
    return (scope['year_start'] is None or year>=scope['year_start']) and (scope['year_end'] is None or year<=scope['year_end'])


def fact(fid,source,title,text,values,url,**extra):
    return {'id':fid,'source':source,'title':title,'text':text,'values':values,'source_url':url,**extra}


def selected(code,scope):
    return not scope['countries'] or code in scope['countries']


def public_facts(scope):
    rows=[r for r in PROCUREMENT['rows'] if selected(r['code'],scope) and period_matches(r['year'],scope)]
    latest={}
    for r in rows:
        if r['code'] not in latest or r['year']>latest[r['code']]['year']:latest[r['code']]=r
    source=PROCUREMENT['source_files'][0]['url']
    output=[]
    if not scope['countries']:
        year=scope['year_end'] or PROCUREMENT['default_year']
        annual=[r for r in rows if r['year']==year]
        if annual:
            total=sum(r['usd'] for r in annual);count=sum(r['contracts'] for r in annual)
            output.append(fact(f'procurement:covered:{year}','procurement',f'Covered procurement, {year}',f'Publisher coverage totals USD {total:,} across {count:,} contracts in {len(annual)} countries for {year}. This is partial published coverage, not all worldwide procurement or verified delivery.',{'usd':total,'contracts':count,'countries':len(annual),'year':year},source))
    for r in sorted(latest.values(),key=lambda r:-r['usd']):
        output.append(fact(f'procurement:{r["code"]}:{r["year"]}','procurement',f'{r["name"]} published procurement / {r["year"]}',f'Published procurement: USD {r["usd"]:,}; {r["contracts"]:,} source contracts in {r["year"]}. Aggregate records contain no independent completion evidence.',{'usd':r['usd'],'contracts':r['contracts'],'year':r['year'],'categories':r['categories']},source,country=r['code']))
    return output


def material_facts(scope):
    if not period_matches(MATERIALS['year'],scope):return
    products={p['code']:p for p in MATERIALS['products']}
    files={f['name']:f['url'] for f in MATERIALS['source_files']};totals={}
    for alpha3,code,exports,imports in MATERIALS['rows']:
        c=BY_ALPHA3.get(alpha3)
        if not c or not selected(c['code'],scope):continue
        totals[c['code']]=totals.get(c['code'],0)+exports
        product=products[code]['name'];source=files[f'hs4/years/{MATERIALS["year"]}/{code[:2]}.json']
        yield fact(f'material:{alpha3}:{code}:{MATERIALS["year"]}','materials',f'{c["name"]}: {product} (HS {code})',f'{MATERIALS["year"]}: national exports USD {exports:,}, imports USD {imports:,}, HS {code} ({product}). Gross trade includes possible re-exports and processed forms; this is not extraction, GDP or net benefit.',{'exports_usd':exports,'imports_usd':imports,'hs4':code,'year':MATERIALS['year']},source,country=c['code'],ranking_value=exports)
    for ccode,total in totals.items():
        yield fact(f'material:country:{ccode}:{MATERIALS["year"]}','materials',f'{BY_CODE[ccode]["name"]} / selected material basket',f'{MATERIALS["year"]}: USD {total:,} exports across SUNLIGHT’s selected raw-material/primary-input basket. Not domestic extraction or GDP.',{'exports_usd':total,'year':MATERIALS['year']},MATERIALS['mirror_url'],country=ccode,summary=True,ranking_value=total)
    if not scope['countries']:
        yield fact('material:covered:2023','materials','Selected material exports / covered world total',f'2023: USD {MATERIALS["total_usd"]:,}; {MATERIALS["country_count"]} exporting economies, {len(products)} selected HS4 headings. This is a selected basket of gross exports and overlaps goods trade; do not add the totals.',{'exports_usd':MATERIALS['total_usd'],'economies':MATERIALS['country_count'],'hs4_headings':len(products),'year':MATERIALS['year']},MATERIALS['mirror_url'],summary=True,ranking_value=MATERIALS['total_usd'])
    for alpha3,partner,code,share,direction,total in MATERIALS['routes']:
        a,b=BY_ALPHA3.get(alpha3),BY_ALPHA3.get(partner)
        if not a or not b or not(selected(a['code'],scope) or selected(b['code'],scope)):continue
        product=products[code]['name'];basis=f'{a["name"]} exports' if direction==1 else f'{b["name"]} imports'
        yield fact(f'material:route:{alpha3}:{partner}:{code}:{direction}','materials',f'{a["name"]} → {b["name"]}: {product}',f'2023: leading-partner share {Decimal(share)/100}% of {basis} for HS {code}. Rounded partner share only; exact bilateral USD, shipment paths and extraction origin are unavailable.',{'share_basis_points':share,'reference_direction':'exporter exports' if direction==1 else 'importer imports','reference_total_usd':total,'hs4':code,'year':MATERIALS['year']},files[f'routes/{MATERIALS["year"]}/{code[:2]}.json'],origin=a['code'],destination=b['code'],ranking_value=total*share)


@lru_cache(maxsize=1)
def arms_groups():
    groups={}
    for r in ARMS['rows']:
        key=(r['year'],r['exporter'],r['importer'],r['family'],r['category'])
        g=groups.setdefault(key,{'year':r['year'],'origin':r['exporter'],'destination':r['importer'],'origin_name':r['exporter_name'],'destination_name':r['importer_name'],'family':r['family'],'category':r['category'],'export':[],'import':[]})
        g[r['direction']].append(r)
    result=[]
    for g in groups.values():
        def side(rows):
            return None if not rows or any(r['quantity'] is None or r['duplicate_count']>1 for r in rows) else sum(r['quantity'] for r in rows)
        ex,im=side(g['export']),side(g['import'])
        g={**g,'export_quantity':ex,'import_quantity':im,'difference':ex-im if ex is not None and im is not None else None}
        result.append(g)
    return result


def arms_facts(scope):
    output=[]
    groups=sorted(arms_groups(),key=lambda g:(g['difference'] in (None,0),-g['year']))
    for g in groups:
        if not period_matches(g['year'],scope) or not(selected(g['origin'],scope) or selected(g['destination'],scope)):continue
        ex,im,difference=g['export_quantity'],g['import_quantity'],g['difference']
        source_rows=g['export']+g['import'];source_urls=list(dict.fromkeys(r['source_url'] for r in source_rows))
        output.append(fact(f'arms:{g["year"]}:{g["origin"]}:{g["destination"]}:{g["family"]}:{g["category"]}','arms',f'{g["origin_name"]} → {g["destination_name"]}: {g["category"]}',f'{g["year"]} {g["family"]}, {g["category"]}: export declaration {ex if ex is not None else "unknown/unassessable"}; import declaration {im if im is not None else "unknown/unassessable"}; signed export-minus-import difference {difference if difference is not None else "not comparable"}. A reporting difference is not a missing/diverted-weapon count.',{'export_items':ex,'import_items':im,'signed_difference':difference,'family':g['family'],'category':g['category'],'year':g['year']},source_urls[0],source_urls=source_urls,origin=g['origin'],destination=g['destination']))
    return output


def conflict_facts(scope):
    names={normalized(BY_CODE[c]['name']) for c in scope['countries']}|{normalized(BY_CODE[c]['official']) for c in scope['countries']}
    output=[]
    for e in CONFLICTS['events']:
        if not period_matches(int(e['start'][:4]),scope):continue
        if names and normalized(e['reporting_area']) not in names:continue
        output.append(fact(f'conflict:{e["id"]}','conflicts',f'{e["place"]} / source event {e["id"]}',f'Recorded interval {e["start"]} to {e["end"]}; place {e["place"]}; publisher reporting area {e["reporting_area"]}; location-precision code {e["location_precision"]}, violence type {e["type"]}. Preliminary partial UCDP candidate extract; not a real-time front line or causal link to procurement.',{'event_id':e['id'],'start':e['start'],'end':e['end'],'reporting_area':e['reporting_area'],'location_precision':e['location_precision'],'type':e['type'],'reported_parties':e['sides']},CONFLICTS['source_file']['url']))
    return output


def operations_facts(db,scope):
    rows=db.execute('SELECT r.* FROM op_revisions r JOIN (SELECT case_id,MAX(revision) revision FROM op_revisions GROUP BY case_id) c ON r.case_id=c.case_id AND r.revision=c.revision ORDER BY r.received_at DESC LIMIT 500')
    output=[]
    for row in rows:
        p=json.loads(row['payload'])
        if not(selected(p['origin_country'],scope) or selected(p['destination_country'],scope)) or not period_matches(int(p['expected']['period_end'][:4]),scope):continue
        e=FlowRevision.model_validate(p);c=compare(e)
        review=db.execute('SELECT payload FROM op_reviews WHERE case_id=?',(row['case_id'],)).fetchone()
        analysis=json.loads(row['analysis']);proc=analysis.get('procurement') or {};delivery=analysis.get('delivery') or {}
        rules=((proc.get('structure') or {}).get('contradictions') or [])+(delivery.get('fired_rules') or [])
        findings=[{'rule_id':r.get('rule_id'),'evidence':str(r.get('evidence') or r.get('description') or '')[:400],'legal_citation':str(r.get('legal_basis') or r.get('legal_citation') or '')[:300]} for r in rules[:6]]
        raw=p.get('procurement_record') or {};entities=[str((raw.get('buyer') or {}).get('name') or '')]
        entities.extend(str(s.get('name') or '') for a in (raw.get('awards') or []) if isinstance(a,dict) for s in (a.get('suppliers') or []) if isinstance(s,dict))
        entities=[n[:160] for n in entities[:10] if n]
        engine_text=' Engine findings on supplied input: '+ '; '.join(str(f['rule_id'] or 'unlabeled')+': '+f['evidence'] for f in findings) if findings else ' No engine finding is asserted by this excerpt.'
        output.append(fact(f'case:{row["case_id"]}:v{row["revision"]}','operations',p['title'],f'{p["origin_country"]} → {p["destination_country"]}; {p["category"]}, source {row["source_id"]}, revision {row["revision"]}. Expected {c["expected"]}, observed {c["observed"] if c["observed"] is not None else "unknown"} {c["currency"] or c["unit"]}; state {c["state"]}; measured shortfall {c["gap"] if c["gap"] is not None else "not calculable"}. {c["reason"]} Supplied entity labels: {", ".join(entities)}.{engine_text}',{'engine_findings':findings,'entity_labels':entities,'comparison':c,'contract_id':p['contract_id'],'item_id':p['item_id'],'source_id':row['source_id'],'revision':row['revision'],'expected':p['expected'],'observed':p['observed'],'review':json.loads(review['payload']) if review else {}},f'/operations/cases/{row["case_id"]}/export',case_id=row['case_id'],payload_hash=row['payload_hash'],origin=p['origin_country'],destination=p['destination_country']))
    return output


def trade_facts(snapshot,scope):
    if not snapshot or not period_matches(int(snapshot.get('period','2023')),scope):return []
    output=[]
    for r in snapshot.get('routes',[]):
        a,b=BY_NUMERIC.get(r['reporter']),BY_NUMERIC.get(r['partner'])
        if not a or not b or not(selected(a['code'],scope) or selected(b['code'],scope)):continue
        url=f'https://comtradeapi.un.org/public/v1/preview/C/A/HS?period={r["period"]}&reporterCode={r["source_reporter"]}&partnerCode={r.get("source_partner",r["partner"])}&cmdCode=TOTAL&flowCode=X'
        output.append(fact(f'trade:{r["reporter"]}:{r["partner"]}:{r["period"]}','goods_trade',f'{a["name"]} → {b["name"]}: total goods exports',f'{r["period"]}: USD {r["usd"]:,} exports reported in the UN Comtrade preview. Status {snapshot["status"]}; retrieved {snapshot.get("fetched_at")}. Selected reporter coverage only; not live shipments, procurement payments or a delivery-loss estimate.',{'usd':r['usd'],'period':r['period'],'reported':r['reported'],'retrieved_at':snapshot.get('fetched_at')},url,origin=a['code'],destination=b['code']))
    return output


def select_balanced(candidates,question,countries,limit=40):
    query=tokens(question);ranked={};counts=Counter()
    for index,f in enumerate(candidates):
        body=tokens(f['title']+' '+f['text']);score=len(query&body)*10
        if len(countries)>1 and f.get('origin') in countries and f.get('destination') in countries:score+=15
        if f['source']=='operations' and f['values']['comparison']['state']=='shortfall':score+=2
        source=f['source']+(':'+f['document_id'] if f['source']=='documents' else '')
        counts[source]+=1
        entry=(score,bool(f.get('summary')),f.get('ranking_value',0),-index,f)
        heap=ranked.setdefault(source,[])
        if len(heap)<10:heapq.heappush(heap,entry)
        elif entry[:4]>heap[0][:4]:heapq.heapreplace(heap,entry)
    for source,rows in ranked.items():ranked[source]=sorted(rows,key=lambda r:r[:4],reverse=True)
    picked=[];round_index=0
    while len(picked)<limit:
        changed=False
        for source,rows in ranked.items():
            if round_index<len(rows):
                # Ranking proxies never leave retrieval or become source measurements.
                picked.append({k:v for k,v in rows[round_index][-1].items() if k not in ('ranking_value','summary')});changed=True
                if len(picked)>=limit:break
        if not changed:break
        round_index+=1
    return picked,dict(counts)
