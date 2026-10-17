#!/usr/bin/env python3
"""Build a source-pinned aggregate snapshot; repeated indicators are not additive."""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

REVISION = '9fd6f26cb22a48b883ee3791fbb3e9da4950f999'
REPOSITORY = 'https://github.com/undp-anticorruption/public-procurement-datasets'
EXPECTED = {
    'tab_1.csv': 'aac0b82b34fdfa38425c710c57eed9a2495dfa96bf539de5962d883705a75720',
    'tab_3.csv': 'e09fa5375a8a0dfb4bf364e871741f35a1711300294f016eb108101c77e408bd',
}


def unique_rows(path, category=False):
    groups = defaultdict(set)
    names = {}
    excluded = set()
    for row in csv.DictReader(path.open(encoding='utf-8-sig', newline='')):
        if row['Contract_value'] != 'ALL':
            continue
        code = row['Country_code_ISO_2']
        if code == 'EU':
            excluded.add(code)
            continue
        code = 'GB' if code == 'UK' else code
        year = int(row['Year'])
        key = (code, year, row['Product_market']) if category else (code, year)
        count_column = next(k for k in row if k.startswith('All_contracts('))
        value_column = next(k for k in row if k.startswith('Total_contract_value_million_usd('))
        try:
            count = Decimal(row[count_column])
            usd = Decimal(row[value_column]) * 1_000_000
            if not count.is_finite() or count != count.to_integral_value() or count < 0 or not usd.is_finite() or usd < 0 or usd != usd.to_integral_value():
                raise ValueError('Invalid aggregate')
        except InvalidOperation as exc:
            raise ValueError('Invalid aggregate') from exc
        groups[key].add((int(count), int(usd)))
        names[code] = row['Country']
    if any(len(values) != 1 for values in groups.values()):
        raise ValueError('Conflicting repeated totals; inspect the source rather than summing indicators')
    return {key: next(iter(value)) for key, value in groups.items()}, names, excluded


def build(source_dir):
    for name, digest in EXPECTED.items():
        if hashlib.sha256((source_dir / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'{name}: checksum differs from pinned source revision')
    totals, names, excluded = unique_rows(source_dir / 'tab_1.csv')
    categories, _, _ = unique_rows(source_dir / 'tab_3.csv', category=True)
    rows = []
    for (code, year), (count, usd) in sorted(totals.items()):
        markets = [{'name': market or 'Market unspecified', 'contracts': n, 'usd': amount}
                   for (c, y, market), (n, amount) in sorted(categories.items()) if c == code and y == year]
        rows.append({'code': code, 'name': names[code], 'year': year, 'contracts': count, 'usd': usd,
                     'categories': sorted(markets, key=lambda x: (-x['usd'], x['name']))})
    years = sorted({row['year'] for row in rows}, reverse=True)
    annual = []
    for year in years:
        values = [r for r in rows if r['year'] == year]
        annual.append({'year': year, 'countries': len(values), 'contracts': sum(r['contracts'] for r in values), 'usd': sum(r['usd'] for r in values)})
    return {
        'schema_version': 'sunlight.public-procurement.v1', 'status': 'bundled_snapshot',
        'publisher': 'Anti-Corruption Compass public datasets / undp-anticorruption',
        'source_repository': REPOSITORY, 'source_revision': REVISION,
        'source_commit_date': '2026-08-25', 'retrieved_date': '2026-10-16', 'retrieval_timezone': 'America/New_York',
        'source_files': [{'name': name, 'sha256': digest, 'url': f'{REPOSITORY}/blob/{REVISION}/{name}'} for name, digest in EXPECTED.items()],
        'currency': 'USD', 'value_precision': 'Source values are rounded to 0.01 million USD; converting units does not add precision.',
        'coverage': 'Published country-year aggregates, not complete national spending, a live feed or independently verified contract records.',
        'method': 'ALL contract-value groups only; deduplicate identical country-year totals across risk indicators. Exclude EU aggregate to avoid overlap with member countries. Map UK to GB. Never sum years into an annual total.',
        'category_coverage': 'Published market breakdowns may be incomplete and are not asserted to reconcile to country totals. No residual category is invented.',
        'excluded_aggregate_codes': sorted(excluded), 'default_year': years[0], 'years': years,
        'country_count': len({r['code'] for r in rows}), 'annual': annual, 'rows': rows,
        'completion': 'The source aggregates contain no completion documents or verified delivered values. These gaps cannot be calculated from this snapshot.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source_dir)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n')
    print(json.dumps({'countries': result['country_count'], 'latest': result['annual'][0], 'output': str(args.output)}))
