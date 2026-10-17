"""Normalize a pinned UNROCA mirror, preserving reporter direction and uncertainty."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import unicodedata

REVISION = '7291ca6a06c4095d0c92e0c544337edff1d621ef'
PINS = {'unroca.json':'e2838562cba1b2476a064ba3cce62528e5fcc502d1c97868629da7b0f20ac0e6', 'years.json':'2eb60658756552280e9795e980effa25754b079b73f173a0e85aae4a0d1ac8a5', 'countries.json':'d3385be7013a5ac69fa584426a7ea813f665ca86bc7e08499b26e12ce39d263f'}
ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFD',value).lower() if c.isalnum())


def build(source_dir):
    files, data = [], {}
    for name, expected in PINS.items():
        content = (source_dir/name).read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        if checksum != expected:
            raise ValueError(f'Source checksum mismatch: {name}')
        data[name] = json.loads(content)
        files.append({'name':name,'sha256':checksum,'url':f'https://raw.githubusercontent.com/Klohto/UNROCA-scraper/{REVISION}/{name}'})
    catalog = json.loads((ROOT/'sunlight-dashboard/src/data/countries.json').read_text())
    names = {}
    for c in catalog:
        for name in [c['name'],c['official'],c['code'],c['alpha3'],*c['aliases']]:
            names.setdefault(normalized(name),set()).add(c['code'])
    aliases = {'Central African Rep.':'CF','Czech Rep.':'CZ','Dem. Rep. of the Congo':'CD','Dominican Rep.':'DO','Guyana':'GY',"Lao People's Dem. Rep.":'LA','Rep. of Korea':'KR','Rep. of Moldova':'MD','Sudan':'SD','Turkey':'TR','United Rep. of Tanzania':'TZ'}
    def code(name):
        if name in aliases:
            return aliases[name]
        matches = names.get(normalized(name),set())
        if len(matches) != 1:
            raise ValueError(f'Unresolved reporting economy: {name}')
        return next(iter(matches))
    rows = [r for r in data['unroca.json'] if r['table'].endswith(('_import','_export')) and int(r['year']) in (2020,2021,2022)]
    signature = lambda r:json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    repeats = Counter(map(signature,rows));seen = set();output=[]
    # Slugs are matched against the mirror's real country list, not generated URLs.
    slugs = {r['country'] for r in data['countries.json']}
    slug_by_code = {}
    for slug in slugs:
        matches = names.get(normalized(slug.replace('-',' ')),set())
        if len(matches)==1:
            slug_by_code[next(iter(matches))]=slug
    slug_by_code.update({'CZ':'czech-republic','CD':'democratic-republic-of-the-congo','DO':'dominican-republic','KR':'republic-of-korea','MD':'republic-of-moldova','TR':'turkey','TZ':'united-republic-of-tanzania','US':'united-states','LA':'lao-peoples-democratic-republic','SD':'sudan','GY':'guyana','CF':'central-african-republic'})
    for row in rows:
        text=signature(row)
        if text in seen:
            continue
        seen.add(text)
        family,direction=row['table'].rsplit('_',1)
        exporter,importer=code(row['exporter']),code(row['importer'])
        reporter=exporter if direction=='export' else importer
        slug=slug_by_code.get(reporter)
        if slug not in slugs:
            raise ValueError(f'No verified source slug for {reporter}: {slug}')
        raw=row['num_items'];quantity=int(raw) if raw.isascii() and raw.isdigit() else None
        output.append({'id':hashlib.sha256(text.encode()).hexdigest()[:20], 'year':int(row['year']),
            'exporter':exporter,'importer':importer,'exporter_name':row['exporter'],'importer_name':row['importer'],
            'reporter':reporter,'direction':direction,'family':family,'category':row['category'],
            'quantity':quantity,'raw_quantity':raw,'duplicate_count':repeats[text],
            'origin':row['state_of_origin'],'intermediate':row['intermediate_locations'],
            'description':row['description'],'comments':row['comments'],
            'source_url':f'https://www.unroca.org/{slug}/report/{row["year"]}/'})
    return {'schema_version':'sunlight.arms-reporting.v1','status':'bundled_snapshot',
        'source':'UN Register of Conventional Arms (UNROCA), state declarations via a public scrape',
        'source_url':'https://www.unroca.org/','mirror_url':f'https://github.com/Klohto/UNROCA-scraper/tree/{REVISION}',
        'source_revision':REVISION,'source_commit_date':'2023-06-16','retrieved_date':'2026-10-17',
        'years':[2022,2021,2020],'default_year':2022,'source_files':files,
        'coverage':'Historical, partial mirror through 2022, captured June 16, 2023. Voluntary state submissions can be late, incomplete, withheld or differently classified. This is not a live or complete global weapons ledger. National holdings and production are excluded.',
        'units':'Declared number of items within each UNROCA family/category. No USD valuation or SIPRI TIV. Do not add category counts into a homogeneous weapons quantity or compare them with commodity-dollar totals.',
        'method':'Match exporter and importer declarations only by year, exporter, importer, family and category. Retain each side separately; never add mirror declarations as two transfers. Any missing quantity or identical duplicate record group makes that side unassessable rather than zero. Broad-category differences still require report-level review for timing, definitions, models, temporary transfers and corrections.',
        'gap_limit':'A declaration difference is not a missing weapon, proven diversion or an official-to-ground shortfall. Field recoveries are selective observations of stocks, while declarations describe annual flows. A global diversion gap is not calculable without matched weapon/batch identities, comparable periods and independently verified custody or inventory evidence.',
        'geography':'Moving blue points connect declared exporting and importing country reference points, not actual transport paths. They are dated schematic relationships, not current shipment locations or live weapons tracking.',
        'mirror_license':'MIT repository license; original UN/state report rights and attribution remain with their publishers. Only factual report fields are normalized; no scraper application code is reused.',
        'rows':output,'source_transfer_rows':len(rows),'normalized_rows':len(output),
        'duplicate_groups':sum(n>1 for n in repeats.values()),'missing_quantities':sum(r['quantity'] is None for r in output),
    }


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-dir',type=Path,required=True);parser.add_argument('--output',type=Path,default=Path('code/arms_snapshot.json'))
    args=parser.parse_args();snapshot=build(args.source_dir);args.output.write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n')
    print({k:snapshot[k] for k in ('normalized_rows','duplicate_groups','missing_quantities')})
