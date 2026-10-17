"""Derive a bounded primary-input basket from pinned, public BACI partitions.

No application code or design from the mirror is reused. Route partitions contain
rounded partner shares, not bilateral dollar values: never invent the latter.
"""
import argparse
import hashlib
import json
from pathlib import Path

REVISION = 'd63f2c7ba9e3639d9904da7f490bc69e96468188'
MIRROR = 'https://github.com/Lucas-Speciale/trade-atlas'
RAW = f'https://raw.githubusercontent.com/Lucas-Speciale/trade-atlas/{REVISION}/'
YEAR = 2023
# SUNLIGHT operational basket, not a claim of a universal raw-material standard.
# Own labels; selected HS4 headings include processing explicitly described below.
GROUPS = {
 'Energy feedstocks': {'2701':'Coal', '2702':'Lignite', '2703':'Peat', '2709':'Crude petroleum', '2711':'Petroleum gases'},
 'Ores and concentrates': dict(zip([f'26{i:02}' for i in range(1,18)], ['Iron ores','Manganese ores','Copper ores','Nickel ores','Cobalt ores','Aluminium ores','Lead ores','Zinc ores','Tin ores','Chromium ores','Tungsten ores','Uranium / thorium ores','Molybdenum ores','Titanium ores','Niobium / tantalum / vanadium / zirconium ores','Precious-metal ores','Other ores'])),
 'Mineral inputs': {'2501':'Salt', '2502':'Unroasted iron pyrites', '2503':'Sulphur', '2504':'Natural graphite', '2505':'Natural sands', '2506':'Quartz / quartzite', '2507':'Kaolin', '2508':'Other clays', '2509':'Chalk', '2510':'Natural phosphates', '2511':'Natural barytes / witherite', '2512':'Siliceous fossil meals', '2513':'Pumice / emery / natural abrasives', '2514':'Slate', '2515':'Marble / travertine', '2516':'Granite / other stone', '2517':'Gravel / crushed stone', '2518':'Dolomite', '2519':'Magnesite / magnesia', '2520':'Gypsum / anhydrite / plaster', '2521':'Limestone flux', '2524':'Asbestos', '2525':'Mica', '2526':'Natural steatite / talc', '2528':'Natural borates', '2529':'Feldspar / fluorspar', '2530':'Other mineral substances'},
 'Agricultural and forest inputs': {'0901':'Coffee (including roasted)', '1001':'Wheat / meslin', '1002':'Rye', '1003':'Barley', '1004':'Oats', '1005':'Maize', '1006':'Rice (including milled)', '1007':'Grain sorghum', '1008':'Other cereals', '1201':'Soya beans', '1202':'Groundnuts', '1204':'Linseed', '1205':'Rape / colza seeds', '1206':'Sunflower seeds', '1207':'Other oil seeds', '1801':'Cocoa beans', '4001':'Natural rubber', '4101':'Raw bovine / equine hides', '4102':'Raw sheep skins', '4103':'Other raw hides', '4403':'Wood in the rough', '5101':'Wool, not carded / combed', '5201':'Cotton, not carded / combed', '5301':'Flax, not spun', '5302':'True hemp, not spun'},
 'Primary metals and precious materials': {'7102':'Diamonds (including worked, unmounted)', '7106':'Silver (including semi-manufactured)', '7108':'Gold (including semi-manufactured)', '7110':'Platinum-group metals (including semi-manufactured)', '7402':'Unrefined copper / anodes', '7403':'Refined copper / unwrought alloys', '7502':'Unwrought nickel', '7601':'Unwrought aluminium', '7801':'Unwrought lead', '7901':'Unwrought zinc', '8001':'Unwrought tin'},
}


def build(source_dir):
    files = []
    pins = json.loads(Path(__file__).with_name('materials_source_checksums.json').read_text())
    def read(relative):
        content = (source_dir / relative).read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        if pins.get(relative) != checksum:
            raise ValueError(f'Source checksum mismatch: {relative}')
        files.append({'name': relative, 'url': RAW + 'public/data/trade/' + relative,
                      'sha256': checksum})
        return json.loads(content)
    manifest = read('manifest.json')
    if manifest['source']['version'] != 'BACI_HS17_V202601':
        raise ValueError('Unexpected BACI release')
    country_totals = {r['iso3']: r['exports'] for r in read(f'years/{YEAR}.json')['countries']}
    products = [{'code': code, 'name': name, 'group': group} for group, values in GROUPS.items() for code, name in values.items()]
    rows, routes = [], []
    for hs2 in sorted({p['code'][:2] for p in products}):
        values = read(f'hs4/years/{YEAR}/{hs2}.json')
        paths = read(f'routes/{YEAR}/{hs2}.json')
        if values['year'] != YEAR or paths['year'] != YEAR:
            raise ValueError('Mixed observation years')
        for product in [p for p in products if p['code'].startswith(hs2)]:
            code = product['code']
            seen = set()
            totals = {}
            for iso, exports, imports in values['products'][code]:
                if iso in seen or any(type(v) is not int or not 0 <= v <= 9_007_199_254_740_991 for v in (exports, imports)):
                    raise ValueError('Invalid or duplicate country/product total')
                seen.add(iso)
                totals[iso] = (exports, imports)
                rows.append([iso, code, exports, imports])
            for reference, direction, partners in paths['hs4Routes'].get(code, []):
                if direction not in (-1, 1):
                    raise ValueError('Invalid direction')
                base = totals[reference][0 if direction == 1 else 1]
                for partner, share in partners:
                    if type(share) is not int or not 1 <= share <= 10000 or partner == reference:
                        raise ValueError('Invalid partner share')
                    exporter, importer = (reference, partner) if direction == 1 else (partner, reference)
                    # Keep both source views: percentages have DIFFERENT denominators.
                    routes.append([exporter, importer, code, share, direction, base])
    return {
        'schema_version':'sunlight.materials.v1', 'status':'bundled_snapshot', 'year':YEAR, 'currency':'USD',
        'source':'CEPII BACI HS17', 'release':manifest['source']['version'], 'provisional':False,
        'source_url':'https://www.cepii.fr/DATA_DOWNLOAD/baci/doc/baci_webpage.html',
        'mirror_url':f'{MIRROR}/tree/{REVISION}', 'source_revision':REVISION,
        'source_files':files, 'retrieved_date':'2026-10-17',
        'license':'Etalab Open Licence 2.0', 'license_url':'https://www.etalab.gouv.fr/licence-ouverte-open-licence/',
        'provenance':'BACI-derived published partitions retrieved from Trade Atlas, pinned to the linked revision. BACI reconciles exporter/importer trade reports; these values are not audited domestic production. The original BACI archive has not been independently reprocessed by SUNLIGHT. The mirror uses Other Asia, nes as its practical proxy for Taiwan; reporting areas can differ from political boundaries.',
        'definition':'SUNLIGHT selected HS4 basket of raw materials and primary inputs: energy, ores, minerals, agricultural/forest inputs, primary metals and precious materials. Includes some processed forms within these HS4 headings; not an official exhaustive raw-material classification.',
        'method':'Sum each selected HS4 country export value once, in current USD, for 2023. Source national values are rounded to whole USD. Imports are shown separately and never added to exports. This is gross cross-border trade, including possible re-exports, not domestic extraction, producer origin, GDP, value added, procurement or net benefit.',
        'route_coverage':'Source route partitions retain up to 10 leading partners per country/product, for its net-exporter or net-importer side, subject to a USD 1 million national-product threshold and source geographic coverage. They are a subset, not all bilateral trade.',
        'route_precision':'Partner shares are rounded to 0.01 percentage point, with a minimum displayed share of 0.01%. No precise bilateral dollar value is supplied by these partitions; SUNLIGHT does not fabricate one. Exporter is the shipping trade economy, not necessarily the place of extraction.',
        'row_fields':['country_iso3','hs4','exports_usd','imports_usd'], 'rows':rows,
        'route_fields':['exporter_iso3','importer_iso3','hs4','share_basis_points','reference_direction','reference_total_usd'], 'routes':routes,
        'products':products, 'country_goods_exports':country_totals,
        'total_usd':sum(r[2] for r in rows), 'country_count':len({r[0] for r in rows if r[2] > 0}),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('code/materials_snapshot.json'))
    args = parser.parse_args()
    # A pinned checkout, rather than arbitrary same-shaped data, is required.
    import subprocess
    root = args.source_dir.resolve().parents[2]
    if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'], text=True).strip() != REVISION:
        raise ValueError('Source checkout does not match pinned revision')
    snapshot = build(args.source_dir)
    args.output.write_text(json.dumps(snapshot, separators=(',',':'), ensure_ascii=False)+'\n')
    print({k:snapshot[k] for k in ('year','total_usd','country_count')})
