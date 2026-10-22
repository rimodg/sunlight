"""Comparable monetary series; statistical changes are never settlement residuals."""
from decimal import Decimal, localcontext

from fastapi import HTTPException


def _change(before, after, same_period):
    if same_period:
        reason = 'same_period'
    elif before['value'] is None or after['value'] is None:
        reason = 'missing_observation'
    elif before['basis'] != after['basis']:
        reason = 'basis_changed'
    elif before['_coverage'] != after['_coverage']:
        reason = 'coverage_changed'
    else:
        a, b = Decimal(before['value']), Decimal(after['value'])
        return {'status': 'comparable', 'difference': format(b-a, 'f'),
                'percent': format(((b-a)/a*100).quantize(Decimal('0.01')), 'f') if a > 0 else None,
                'percent_basis': 'positive_baseline' if a > 0 else 'nonpositive_baseline'}
    return {'status': reason, 'difference': None, 'percent': None, 'percent_basis': None}


def analyse(snapshot, catalog, measure, countries='', baseline=None, year=None, direction='inward'):
    names = {c['code']: c['name'] for c in catalog}
    codes = countries.split(',') if countries else []
    if len(codes) > 4 or len(codes) != len(set(codes)) or any(c not in names for c in codes):
        raise HTTPException(422, 'Select up to four distinct recognized country ISO codes')
    if direction not in ('inward', 'outward'):
        raise HTTPException(422, 'Direction must be inward or outward')
    aid = measure == 'aid'
    layer = next((l for l in snapshot['layers'] if l['id'] == measure), None)
    if not layer and not aid:
        raise HTTPException(422, 'Recognized monetary measure required')
    year = year if year is not None else snapshot['aid']['year'] if aid else layer['year']
    baseline = baseline if baseline is not None else max(2019, year-1)
    if not (2019 <= baseline <= year <= 2026):
        raise HTTPException(422, 'Baseline and comparison years must be ordered within 2019–2026')
    metadata = ({'id': 'aid', 'label': 'Bilateral development assistance · net',
                 'kind': 'net_flow', 'currency': 'USD', 'direction': direction,
                 'definition': snapshot['aid']['basis'], 'source': 'World Bank WDI / OECD DAC',
                 'source_url': 'https://data.worldbank.org/indicator/DC.DAC.TOTL.CD',
                 'license': 'CC BY-4.0'} if aid else {k:v for k,v in layer.items() if k not in ('rows', 'total', 'country_count', 'total_basis', 'year')})
    years = list(range(2019, 2027))
    indexed = {(r['country'],r['year']): r['value'] for r in layer['rows']} if layer else {}
    with localcontext() as ctx:
        ctx.prec = 60
        series = []
        for code in ['WLD', *codes]:
            points = []
            for period in years:
                if aid:
                    rows = [r for r in snapshot['aid']['rows'] if r['year'] == period and
                            (code == 'WLD' or r['to' if direction == 'inward' else 'from'] == code)]
                    value = format(sum((Decimal(r['usd']) for r in rows),Decimal(0)), 'f') if rows else None
                    basis = 'covered_bilateral_net' if rows else 'unavailable'
                    coverage = frozenset((r['from'],r['to']) for r in rows)
                elif code == 'WLD':
                    rows = [r for r in layer['rows'] if r['year'] == period and r['country'] != 'WLD']
                    value = indexed.get(('WLD',period))
                    if value is not None:
                        basis, coverage = 'publisher_world', frozenset(['WLD'])
                    else:
                        value = format(sum((Decimal(r['value']) for r in rows),Decimal(0)), 'f') if rows else None
                        basis, coverage = ('covered_economies_sum',frozenset(r['country'] for r in rows)) if rows else ('unavailable',frozenset())
                else:
                    value = indexed.get((code,period))
                    rows = [value] if value is not None else []
                    basis = 'country_observation' if value is not None else 'unavailable'
                    coverage = frozenset([code]) if value is not None else frozenset()
                points.append({'year':period,'value':value,'basis':basis,'coverage_count':len(rows),
                               '_coverage':coverage})
            before, after = points[baseline-2019], points[year-2019]
            change = _change(before,after,baseline == year)
            for point in points:
                point.pop('_coverage')
            series.append({'country':code,'name':'World / covered total' if code == 'WLD' else names[code],
                           'points':points,'baseline':before,'current':after,'change':change})
    return {'measure':metadata,'year':year,'baseline_year':baseline,'countries':codes,'series':series,
            'aid_direction':direction if aid else None,'source_revision':snapshot['source_revision'],
            'source_repository':snapshot['source_repository'],'retrieved_at':snapshot['retrieved_at'],
            'provenance':snapshot['provenance'], 'mirror_updated_at':snapshot['mirror_updated_at'],
            'comparison_rule':'One measure, current USD, exact source years. No interpolation or inflation adjustment. Changes in covered-country or bilateral-pair composition block aggregate differences; positive baselines alone support percentage change.',
            'interpretation':'A statistical change is not a missing payment, procurement shortfall, or theft finding. Stocks are positions, not transfers. These figures do not verify recipient bank credits or public benefit.'}
