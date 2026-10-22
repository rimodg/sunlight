"""Build a pinned WDI mirror extract. Network access uses inherited proxy/CA trust."""
import csv
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REVISION = '4252d91d988efc0f116d4fa48e92357b778729e5'
REPOSITORY = 'https://github.com/open-numbers/ddf--world_bank--world_development_indicators'
BASE = f'https://raw.githubusercontent.com/open-numbers/ddf--world_bank--world_development_indicators/{REVISION}/'
# Annual current USD only. Stocks and economic context remain explicitly separate.
SERIES = [
 ('goods_exports','tx_val_mrch_cd_wt','Goods exports','annual_flow','outward'),
 ('goods_imports','tm_val_mrch_cd_wt','Goods imports','annual_flow','inward'),
 ('services_exports','bx_gsr_nfsv_cd','Services exports','annual_flow','outward'),
 ('services_imports','bm_gsr_nfsv_cd','Services imports','annual_flow','inward'),
 ('remittances_received','bx_trf_pwkr_cd_dt','Personal remittances received','annual_flow','inward'),
 ('remittances_paid','bm_trf_pwkr_cd_dt','Personal remittances paid','annual_flow','outward'),
 ('fdi_inflows','bx_klt_dinv_cd_wd','Direct investment · net inflows','net_flow','inward'),
 ('fdi_outflows','bm_klt_dinv_cd_wd','Direct investment · net outflows','net_flow','outward'),
 ('portfolio_equity','bx_pef_totl_cd_wd','Portfolio equity · net inflows','net_flow','inward'),
 ('portfolio_net','bn_klt_ptxl_cd','Portfolio investment · net','net_flow','balance'),
 ('oda_received','dt_oda_odat_cd','Development assistance received · net','net_flow','inward'),
 ('oda_provided','dc_oda_totl_cd','Development assistance provided · net','net_flow','outward'),
 ('debt_service','dt_tds_dect_cd','External debt service paid','annual_flow','outward'),
 ('external_debt','dt_dod_dect_cd','External debt outstanding','stock','position'),
 ('ibrd_flows','dt_nfl_mibr_cd','IBRD financing · net flows','net_flow','inward'),
 ('ida_flows','dt_nfl_mida_cd','IDA financing · net flows','net_flow','inward'),
 ('imf_concessional','dt_nfl_imfc_cd','IMF concessional financing · net','net_flow','inward'),
 ('imf_nonconcessional','dt_nfl_imfn_cd','IMF nonconcessional financing · net','net_flow','inward'),
 ('primary_income_received','bx_gsr_fcty_cd','Primary income received','annual_flow','inward'),
 ('primary_income_paid','bm_gsr_fcty_cd','Primary income paid','annual_flow','outward'),
 ('secondary_income','bx_trf_curr_cd','Secondary income received','annual_flow','inward'),
 ('ip_receipts','bx_gsr_royl_cd','Intellectual property receipts','annual_flow','inward'),
 ('tourism_receipts','st_int_rcpt_cd','International tourism receipts','annual_flow','inward'),
 ('government_consumption','ne_con_govt_cd','Government final consumption','economic_context','domestic'),
 ('military_spending','ms_mil_xpnd_cd','Military expenditure','economic_context','domestic'),
 ('reserves','fi_res_totl_cd','Reserves including gold','stock','position'),
 ('gdp','ny_gdp_mktp_cd','Economic output · GDP','economic_context','domestic'),
]

def build():
    manifest = []
    pins = json.loads((ROOT/'scripts/monetary_source_checksums.json').read_text())
    def fetch(path):
        response = httpx.get(BASE + path, timeout=60, follow_redirects=True)
        response.raise_for_status()
        checksum = hashlib.sha256(response.content).hexdigest()
        if pins.get(path) != checksum:
            raise ValueError(f'Unreviewed source checksum for {path}')
        manifest.append({'path':path,'url':BASE+path,'sha256':checksum,'bytes':len(response.content)})
        return list(csv.DictReader(io.StringIO(response.text)))
    concepts = {r['concept']:r for r in fetch('ddf--concepts--continuous.csv')}
    country_rows = json.loads((ROOT/'code/research_countries.json').read_text())
    countries = {c['alpha3'].lower():c for c in country_rows}
    country_entities = fetch('ddf--entities--economy--country.csv')
    # WDI XKX and the application's UNK both denote the XK catalogue entry.
    countries['xkx'] = next(c for c in country_rows if c['code']=='XK')
    excluded_entities=[{'source_code':r['country'],'name':r['name'],'reason':'Historical entity or combined reporting area without a single catalogue country; not allocated to successor countries.'} for r in country_entities if r['country'] not in countries]
    donors = [r for r in concepts if r.startswith('dc_dac_') and r.endswith('_cd') and r != 'dc_dac_totl_cd']
    # The donor code fragment is its ISO alpha3 except the documented source codes.
    donor_codes = {'ausl':'aus','autl':'aut','bell':'bel','canl':'can','chel':'che','czel':'cze','deul':'deu','dnkl':'dnk','espl':'esp','estl':'est','finl':'fin','fral':'fra','gbrl':'gbr','grcl':'grc','hunl':'hun','irll':'irl','isll':'isl','ital':'ita','jpnl':'jpn','korl':'kor','ltul':'ltu','luxl':'lux','nldl':'nld','norl':'nor','nzll':'nzl','poll':'pol','prtl':'prt','svkl':'svk','svnl':'svn','swel':'swe','usal':'usa'}
    paths = {code:f'datapoints/ddf--datapoints--{code}--by--economy--year.csv' for code in [s[1] for s in SERIES]+donors}
    with ThreadPoolExecutor(max_workers=8) as pool:
        tables = dict(zip(paths,pool.map(fetch,paths.values())))
    def rows_for(code):
        seen=set();rows=[]
        for r in tables[code]:
            year=int(r['year']); economy=r['economy'].lower()
            if year<2019 or year>2026 or (economy not in countries and economy!='wld'):continue
            v=Decimal(r[code])
            if not v.is_finite():raise ValueError('Nonfinite observation')
            key=(economy,year)
            if key in seen:raise ValueError('Duplicate economy/year')
            seen.add(key);rows.append({'country':countries[economy]['code'] if economy!='wld' else 'WLD','year':year,'value':format(v,'f')})
        return rows
    layers=[]
    for ident,code,label,kind,direction in SERIES:
        rows=rows_for(code);meta=concepts[code]
        worlds=[r for r in rows if r['country']=='WLD']
        counts={y:sum(r['year']==y and r['country']!='WLD' for r in rows) for y in sorted({r['year'] for r in rows})}
        year=max((r['year'] for r in worlds),default=max(counts,default=None))
        selected=[r for r in rows if r['year']==year and r['country']!='WLD']
        world=next((r for r in worlds if r['year']==year),None)
        total=world['value'] if world else format(sum((Decimal(r['value']) for r in selected),Decimal(0)),'f') if selected else None
        layers.append({'id':ident,'indicator':meta['series_code'],'label':label,'kind':kind,'direction':direction,'currency':'USD','year':year,
          'total':total,'total_basis':'publisher_world' if world else 'covered_economies_sum','country_count':len(selected),'rows':rows,
          'definition':meta['short_definition'],'source':meta['source'],'license':meta['license_type'],'source_url':'https://data.worldbank.org/indicator/'+meta['series_code'],
          'mirror_url':BASE+paths[code],'aggregation_method':meta['aggregation_method']})
    aid_rows=[]
    for code in donors:
        donor=donor_codes.get(code.split('_')[2])
        if not donor:continue # EU institutions have no invented sovereign origin.
        for r in rows_for(code):
            if r['country']=='WLD' or r['country']==countries[donor]['code']:continue
            aid_rows.append({'from':countries[donor]['code'],'to':r['country'],'year':r['year'],'usd':r['value'],'indicator':concepts[code]['series_code'],'source_url':'https://data.worldbank.org/indicator/'+concepts[code]['series_code'],'mirror_url':BASE+paths[code]})
    counts={y:sum(r['year']==y for r in aid_rows) for y in {r['year'] for r in aid_rows}}
    aid_year=max(counts)
    aid_selected=[r for r in aid_rows if r['year']==aid_year]
    snapshot={'schema_version':'sunlight.monetary-context.v1','retrieved_at':'2026-10-20','source_revision':REVISION,'source_repository':REPOSITORY,
      'mirror_updated_at':'2026-10-14','provenance':'World Bank WDI, retrieved from the Open Numbers transformation mirror. Direct publisher API inaccessible from the build environment. Mirror is not an authenticated bank or settlement feed.',
      'default_period_rule':'Default periods use the latest publisher world aggregate where available; otherwise the latest year with mapped national observations. A world series can stop earlier than country series; choose an explicit year to inspect its coverage.',
      'currency':'USD','years':list(range(2019,2027)),'layers':layers,'aid':{'year':aid_year,'rows':aid_rows,'total':format(sum((Decimal(r['usd']) for r in aid_selected),Decimal(0)),'f'),'basis':'Covered donor-recipient net disbursements; excludes EU institutional origin and unknown endpoints; overlaps ODA received/provided.', 'donors':len({r['from'] for r in aid_selected}),'recipients':len({r['to'] for r in aid_selected})},
      'country_code_aliases':{'xkx':'XK'},'excluded_entities':excluded_entities,
      'files':sorted(manifest,key=lambda f:f['path'])}
    (ROOT/'code/monetary_snapshot.json').write_text(json.dumps(snapshot,separators=(',',':'))+'\n')
    for l in layers:print(l['id'],l['year'],l['total'],l['total_basis'],l['country_count'])
    print('aid',aid_year,len(aid_selected),snapshot['aid']['total'])

if __name__=='__main__':build()
