"""Read-only investigative tools, restricted to the run's selected sources/documents/scope."""
import re
from starlette.concurrency import run_in_threadpool
from research_evidence import fact,period_matches

TOOL_SCHEMAS=[
 {'type':'function','name':'summarize_selected_evidence','description':'Compute source-specific totals/counts across the full matching retained public scope, separate from snippet ranking. Does not combine overlapping domains, weapon quantities, different years or sources. Operations statistics scan latest 500 cases only.','strict':True,'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}},
 {'type':'function','name':'search_selected_evidence','description':'Search the run’s selected evidence layers and PDFs with a more specific query. Original country/year/source permissions remain fixed. Returns a bounded evidence selection and source candidate counts, not exhaustive global coverage.','strict':True,'parameters':{'type':'object','properties':{'query':{'type':'string','minLength':3,'maxLength':1000}},'required':['query'],'additionalProperties':False}},
 {'type':'function','name':'read_selected_document_page','description':'Read up to 6000 characters from an original extracted page of a PDF explicitly selected for this inquiry. Scanned PDFs may have no text.','strict':True,'parameters':{'type':'object','properties':{'document_id':{'type':'string'},'page':{'type':'integer','minimum':1,'maximum':64},'character_start':{'type':'integer','minimum':0,'maximum':12000}},'required':['document_id','page','character_start'],'additionalProperties':False}},
 {'type':'function','name':'inspect_operational_case','description':'Inspect one operational case identifier from case:<identifier>:v<revision>. Runs the existing exact comparison on retained measurements and returns source and deadline basis. Only available if operations was selected and case matches original country/year scope. No writes or external actions.','strict':True,'parameters':{'type':'object','properties':{'case_id':{'type':'string'}},'required':['case_id'],'additionalProperties':False}},
]


def make_tool_runner(request,scope,trade):
    def execute(name,args):
        if not isinstance(args,dict):return {'error':'Tool arguments must be an object'}
        if name=='summarize_selected_evidence':
            if args:return {'error':'This tool uses the original scope and accepts no arguments'}
            from collections import Counter,defaultdict
            from decimal import Decimal
            from operations import digest
            from research import research_connection,catalog
            from research_evidence import public_facts,material_facts,arms_facts,conflict_facts,operations_facts
            facts=[];source_urls={r['id']:r['url'] for r in catalog()}
            if 'procurement' in request.sources:
                groups=defaultdict(lambda:{'usd':Decimal(0),'contracts':0,'countries':0})
                for f in public_facts(scope):
                    if not f.get('country'):continue
                    v=f['values'];g=groups[v['year']];g['usd']+=Decimal(str(v['usd']));g['contracts']+=v['contracts'];g['countries']+=1
                for year,g in groups.items():
                    g['usd']=str(g['usd'])
                    facts.append(fact('statistics:procurement:'+str(year)+':'+digest(scope)[:12],'procurement',f'Covered procurement statistics / {year}',f"{year}: USD {g['usd']}; {g['contracts']} contracts across {g['countries']} matching countries, one latest matching publication year per country. Groups for different years must not be added as one current-year total. Partial publisher coverage, not delivery or all national spending.",{**g,'year':year},source_urls['procurement']))
            if 'materials' in request.sources:
                exports=Decimal(0);imports=Decimal(0);rows=0;countries=set()
                for f in material_facts(scope):
                    if not f.get('country') or 'hs4' not in f['values']:continue
                    v=f['values'];exports+=Decimal(str(v['exports_usd']));imports+=Decimal(str(v['imports_usd']));rows+=1;countries.add(f['country'])
                if rows:facts.append(fact('statistics:materials:'+digest(scope)[:12],'materials','Selected material basket / complete matching national rows',f'2023 selected material basket: exports USD {exports}; imports USD {imports}; {rows} country-product observations in {len(countries)} matching economies. Gross values can include re-exports. Do not add to total goods trade or infer bilateral dollars, extraction, GDP or losses.',{'exports_usd':str(exports),'imports_usd':str(imports),'country_product_rows':rows,'economies':len(countries),'year':2023},source_urls['materials']))
            if 'arms' in request.sources:
                counts=Counter();years=set()
                for f in arms_facts(scope):
                    v=f['values'];years.add(v['year']);counts['pair_categories']+=1
                    if v['signed_difference'] is None:counts['not_comparable']+=1
                    elif v['signed_difference']==0:counts['matching_declarations']+=1
                    else:counts['reporting_differences']+=1
                if counts:facts.append(fact('statistics:arms:'+digest(scope)[:12],'arms','Arms reporting comparison counts',f"Retained matching arms declarations: {'; '.join(str(n)+' '+name.replace('_',' ') for name,n in counts.items())}; source years {sorted(years)}. Counts are year/pair/family/category groups, not weapon quantities or missing weapons. No heterogeneous quantity total is computed.",dict(counts),source_urls['arms']))
            if 'conflicts' in request.sources:
                rows=conflict_facts(scope)
                if rows:facts.append(fact('statistics:conflicts:'+digest(scope)[:12],'conflicts','Recorded conflict-event coverage count',f'{len(rows)} matching records in the retained partial extract, filtered by publisher reporting-area label. This is neither a complete conflict census nor a cause of economic patterns.',{'recorded_events':len(rows)},source_urls['conflicts']))
            if 'goods_trade' in request.sources:
                groups=defaultdict(lambda:{'usd':Decimal(0),'links':0})
                for f in trade:
                    v=f['values'];g=groups[v['period']];g['usd']+=Decimal(str(v['usd']));g['links']+=1
                for year,g in groups.items():
                    g['usd']=str(g['usd']);facts.append(fact('statistics:goods:'+str(year)+':'+digest(scope)[:12],'goods_trade','Cached goods export relationships',f"{year}: USD {g['usd']} across {g['links']} retained matching export relationships. Selected preview coverage; possible source estimates are not live payments, shipment locations or procurement totals.",{**g,'year':year},source_urls['goods_trade']))
            if 'operations' in request.sources:
                with research_connection() as db:rows=operations_facts(db,scope)
                counts=Counter(r['values']['comparison']['state'] for r in rows)
                if counts:facts.append(fact('statistics:operations:'+digest(scope)[:12],'operations','Operational comparison state counts',f"Latest 500 operational cases scanned, then scope-filtered: {'; '.join(str(n)+' '+name.replace('_',' ') for name,n in counts.items())}. Counts are cases, not added monetary shortfalls. Inspect each case for exact units, period, deadline and evidence.",dict(counts),source_urls['operations']))
            return {'facts':facts,'limit':'Source-specific full retained public-scope statistics. Operations are capped at latest 500 cases; partial and unconnected sources remain missing. No global theft total.'}
        if name=='search_selected_evidence':
            if set(args)!={'query'} or not isinstance(args['query'],str) or not 3<=len(args['query'])<=1000:return {'error':'Provide a query of 3–1000 characters only'}
            from research import retrieve_evidence
            subrequest=request.model_copy(update={'question':args['query']})
            facts,counts,_=retrieve_evidence(subrequest,scope,trade)
            return {'facts':facts[:12],'candidate_counts':counts,'limit':'First 12 source-balanced excerpts; original scope and permissions retained.'}
        if name=='read_selected_document_page':
            if set(args)!={'document_id','page','character_start'} or args['document_id'] not in request.document_ids:return {'error':'Only explicitly selected documents can be read'}
            page,start=args['page'],args['character_start']
            if type(page) is not int or type(start) is not int or not 1<=page<=64 or not 0<=start<=12000:return {'error':'Invalid page or character offset'}
            from research import get_document
            d=get_document(args['document_id']);p=next((p for p in d['pages'] if p['page']==page),None)
            if not p:return {'error':'Page not found'}
            text=p['text'][start:start+6000]
            if not text:return {'facts':[],'limit':'No searchable text at this location. No OCR is performed.'}
            f=fact(f'doc:{d["id"]}:p{page}:c{start}:end{start+len(text)}','documents',f'{d["filename"]} / page {page}',
                'Unverified selected document excerpt: '+text,{'document_sha256':d['sha256'],'page':page,'character_start':start,'character_end':start+len(text)},d['original_url'],document_id=d['id'],page=page,excerpt=text,page_text_truncated=p['truncated'])
            return {'facts':[f],'limit':'Extracted text only; not an authenticated publisher claim.'}
        if name=='inspect_operational_case':
            cid=args.get('case_id')
            if set(args)!={'case_id'} or not isinstance(cid,str) or not re.fullmatch('[a-f0-9]{32}',cid) or 'operations' not in request.sources:return {'error':'A valid case identifier and selected operations layer are required'}
            from operations import get_case
            from fastapi import HTTPException
            try:case=get_case(cid)
            except HTTPException:return {'error':'Case is unavailable in the authorized scope'}
            p=case['record'];c=case['comparison']
            if scope['countries'] and not ({p['origin_country'],p['destination_country']}&set(scope['countries'])):return {'error':'Case is outside the inquiry country scope'}
            if not period_matches(int(p['expected']['period_end'][:4]),scope):return {'error':'Case is outside the inquiry year scope'}
            text=f"{p['title']}; source {case['source']['name']}; {p['origin_country']} → {p['destination_country']}; {p['expected']['metric']}, period {p['expected']['period_start']} to {p['expected']['period_end']}; expected {c['expected']}, observed {c['observed']}, unit/currency {c['currency'] or c['unit']}; due {p['expected']['due_at']}; comparison {c['state']}; calculated shortfall {c['gap']}; percentage {c['gap_percent']}; overage {c['overage']}. {c['reason']}"
            f=fact(f'case-inspection:{cid}:v{case["revision"]}','operations',p['title'],text,{'comparison':c,'source_id':case['source_id'],'revision':case['revision'],'expected':p['expected'],'observed':p['observed']},f'/operations/cases/{cid}/report',case_id=cid,payload_hash=case['payload_hash'],origin=p['origin_country'],destination=p['destination_country'])
            return {'facts':[f],'limit':'Exact comparison of retained claims only, not verified delivery or a theft determination.'}
        return {'error':'Unknown tool; no action performed'}
    async def run(name,args):return await run_in_threadpool(execute,name,args)
    return run
