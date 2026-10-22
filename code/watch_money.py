"""Source-dated monetary atlas. Aggregates never imply settlement verification."""
from decimal import Decimal
import json
from pathlib import Path
import csv
import io

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from monetary_analysis import analyse

SNAPSHOT = json.loads(Path(__file__).with_name('monetary_snapshot.json').read_text())
COUNTRY_CATALOG = json.loads(Path(__file__).with_name('research_countries.json').read_text())
COUNTRIES = {c['code'] for c in COUNTRY_CATALOG}
router = APIRouter()

# A researched integration inventory, not a claim that these feeds are connected.
MISSING = [
 ('Humanitarian funding', 'OCHA Financial Tracking Service / IATI', 'https://fts.unocha.org/', 'Separate pledges, commitments and paid contributions; match activity and recipient identifiers. Overlaps ODA.'),
 ('Climate and biodiversity finance', 'OECD climate-related development finance / UNFCCC', 'https://www.oecd.org/en/topics/climate-finance.html', 'Separate commitments, disbursements, grant equivalents and mobilised private finance. Overlaps ODA and loans.'),
 ('Public revenue, tax and expenditure functions', 'IMF Government Finance Statistics / national treasuries', 'https://data.imf.org/', 'Government perimeter, cash/accrual basis, fiscal year and local currency must match. Government consumption is not total public spending.'),
 ('Gross loan disbursements and creditor schedules', 'World Bank International Debt Statistics / IMF', 'https://www.worldbank.org/en/programs/debt-statistics/ids', 'Gross drawdowns, principal repayments, interest and net flows are different measures; debt balances are stocks.'),
 ('Cross-border banking', 'BIS locational and consolidated banking statistics', 'https://data.bis.org/', 'Mostly positions and exchange-rate-adjusted changes; bank residency and nationality measures differ. Not individual payments.'),
 ('Bilateral portfolio holdings', 'IMF Coordinated Portfolio Investment Survey', 'https://data.imf.org/', 'Security holdings are positions, not annual transfers; preserve instrument, counterpart and valuation basis.'),
 ('Bilateral direct investment', 'IMF Coordinated Direct Investment Survey / UNCTAD', 'https://unctadstat.unctad.org/', 'Ultimate investor differs from immediate counterpart. Stocks, flows and announced projects cannot be combined.'),
 ('Bilateral remittance corridors', 'World Bank / national balance of payments', 'https://www.knomad.org/', 'A modelled bilateral matrix cannot stand in for observed settlement. Current national receipts do not identify a sending country.'),
 ('Institutional procurement and project payments', 'UNGM / UNOPS / World Bank Projects / national OCDS publishers', 'https://www.ungm.org/', 'Link awards, amendments, executed payments, recipient credits, acceptance and public service evidence by stable identifiers.'),
 ('Subnational budgets and public enterprises', 'World Bank BOOST / national budget portals', 'https://www.worldbank.org/en/programs/boost-portal', 'Reconcile transfers between levels of government; avoid counting the same appropriation and disbursement twice.'),
 ('Full commodity and services detail', 'UN Comtrade / WTO / UNCTAD', 'https://comtradeplus.un.org/', 'Expand all HS/EBOPS categories with exporter/importer mirror basis, re-exports and freight/insurance valuation kept distinct.'),
 ('Weapons monetary trade and custody', 'UN Comtrade HS93 / UNROCA / SIPRI / published tracing reports', 'https://www.unroca.org/', 'HS93 customs values do not equal all military equipment transfers. SIPRI TIV is not USD; unknown custody requires actual tracing evidence.'),
 ('Health, education and social protection finance', 'WHO expenditure database / UNESCO / IMF COFOG / ILO', 'https://apps.who.int/nha/database', 'Functional spending overlaps public expenditure and aid. Separate funding source, payer, provider and service delivery.'),
 ('Domestic payments and recipient credits', 'Central banks / treasuries / authorised bank and ERP connectors', 'https://www.bis.org/', 'No universal public transaction ledger exists. Authenticated debit and credit evidence must be permissioned and independently reconciled.'),
 ('Insurance, pensions and other financial services', 'OECD / IMF / national regulators', 'https://data-explorer.oecd.org/', 'Premiums, benefits, assets and investment income are different bases; cross-border services overlap services trade.'),
 ('Digital assets and informal finance', 'BIS / national regulators / attributable public chain records', 'https://www.bis.org/', 'A blockchain address does not identify residency or beneficial ownership. Do not infer country-to-country payments from unattributed addresses.'),
 ('Illicit financial flows and recovered assets', 'UNODC / UNCTAD SDG 16.4.1 / published courts', 'https://unctad.org/topic/statistics/illicit-financial-flows', 'Statistical estimates, adjudicated theft and recovered assets are distinct. A trade or reporting discrepancy alone is not stolen money.'),
]


def atlas(year=None, country=None):
    if country and country not in COUNTRIES:
        raise HTTPException(422, 'Recognized country ISO code required')
    layers=[]
    for layer in SNAPSHOT['layers']:
        chosen=year if year is not None else layer['year']
        rows=[r for r in layer['rows'] if r['year']==chosen and r['country']!='WLD']
        world=next((r for r in layer['rows'] if r['year']==chosen and r['country']=='WLD'),None)
        total=world['value'] if world else format(sum((Decimal(r['value']) for r in rows),Decimal(0)),'f') if rows else None
        layers.append({**{k:v for k,v in layer.items() if k!='rows'},'year':chosen,'total':total,
            'total_basis':'publisher_world' if world else 'covered_economies_sum' if rows else 'unavailable',
            'country_count':len(rows),'rows':[r for r in rows if not country or r['country']==country]})
    aid_year=year if year is not None else SNAPSHOT['aid']['year']
    all_aid=[r for r in SNAPSHOT['aid']['rows'] if r['year']==aid_year]
    aid={**{k:v for k,v in SNAPSHOT['aid'].items() if k!='rows'},'year':aid_year,
         'total':format(sum((Decimal(r['usd']) for r in all_aid),Decimal(0)),'f') if all_aid else None,
         'donors':len({r['from'] for r in all_aid}),'recipients':len({r['to'] for r in all_aid}),
         'rows':[r for r in all_aid if not country or country in (r['from'],r['to'])]}
    return {**{k:v for k,v in SNAPSHOT.items() if k not in ('layers','aid')},'layers':layers,'aid':aid,
        'unconnected':[dict(zip(('label','publisher','url','requirement'),r)) for r in MISSING],
        'scope_country':country,'additive_total':None,
        'total_rule':'No combined all-money total: imports/exports are counterpart views; materials, ODA, institutional finance and services subsets overlap. Stocks and GDP are not transfers. Missing is unknown, never zero.'}


@router.get('/watch-data/money')
def monetary_atlas(year: int | None = Query(default=None,ge=2019,le=2026),country: str | None=None):
    return atlas(year,country)


@router.get('/watch-data/money/analysis')
def monetary_analysis(measure: str, countries: str='', baseline: int | None=None, year: int | None=None, direction: str='inward'):
    return analyse(SNAPSHOT,COUNTRY_CATALOG,measure,countries,baseline,year,direction)


@router.get('/watch-data/money/analysis/report', response_class=HTMLResponse)
def monetary_analysis_report(measure: str, countries: str='', baseline: int | None=None, year: int | None=None, direction: str='inward'):
    from readable_reports import e, fields, link, page, table
    result=monetary_analysis(measure,countries,baseline,year,direction)
    m=result['measure']
    body=fields([('Measure',m['label']),('Accounting basis',m['kind'].replace('_',' ')),('Currency','USD · current prices'),
                 ('Publisher aggregation method',m.get('aggregation_method') or ('Covered reported bilateral pairs' if measure=='aid' else 'Not supplied')),
                 ('Baseline / comparison',f"{result['baseline_year']} / {result['year']}"),
                 ('Country selection',', '.join(result['countries']) or 'World / covered total only'),
                 ('Aid role',direction if measure=='aid' else 'Not applicable')])
    body+='<p class="notice">'+e(result['interpretation'])+'</p><h2>Comparison</h2>'
    body+=table(['Scope','Baseline USD','Comparison USD','Change USD','Change %','Comparability'],[
        [s['name'],s['baseline']['value'],s['current']['value'],s['change']['difference'],s['change']['percent'],s['change']['status']]
        for s in result['series']])
    body+='<p>'+e(result['comparison_rule'])+'</p><h2>Retained annual observations</h2>'
    body+=table(['Scope','Year','Exact published / covered USD','Basis','Covered countries or pairs'],[
        [s['name'],p['year'],p['value'],p['basis'],p['coverage_count']] for s in result['series'] for p in s['points']])
    body+='<h2>Definition and provenance</h2><p>'+e(m['definition'])+'</p><p>'+e(m['source'])+' · '+e(m['license'])+'</p>'
    body+=link(m['source_url'],'Publisher definition')+'<p>'+e(result['provenance'])+'</p>'
    body+=fields([('Source revision',result['source_revision']),('Mirror updated',result['mirror_updated_at']),('Retrieved',result['retrieved_at'])])
    body+=link(result['source_repository']+'/tree/'+result['source_revision'],'Pinned source repository')
    return HTMLResponse(page('Monetary analysis · '+m['label'],body,'Source-dated statistics · recipient settlement not verified'),headers={'Cache-Control':'no-store'})


@router.get('/watch-data/money/analysis.csv')
def monetary_analysis_csv(measure: str, countries: str='', baseline: int | None=None, year: int | None=None, direction: str='inward'):
    result=monetary_analysis(measure,countries,baseline,year,direction)
    buffer=io.StringIO(newline='');writer=csv.writer(buffer)
    writer.writerow(['measure','country','country_name','year','exact_current_usd','basis','coverage_count','aid_direction','source_revision'])
    for series in result['series']:
        name=series['name'];name="'"+name if name.lstrip().startswith(('=','+','-','@')) else name
        for point in series['points']:
            writer.writerow([measure,series['country'],name,point['year'],point['value'],point['basis'],point['coverage_count'],result['aid_direction'] or '',result['source_revision']])
    return Response(buffer.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="sunlight-{measure}-{result["year"]}.csv"','Cache-Control':'no-store'})
