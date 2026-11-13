"""Bounded read-only field-coverage measurement, not a legal rule or service adapter.

Bodies stay in memory. Persist only identifiers, typed dates, booleans and
fixed classifications; never names, titles, descriptions or contact fields.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'code'))
from watch_capture import checked_url, fetch
from watch_journal import admit

URL = 'https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?updatedFrom=2026-11-12T00:00:00&updatedTo=2026-11-13T00:00:00&limit=100'

class Refused(ValueError):
    pass

def identifier(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise Refused('identifier_shape')
    return value

def instant(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)', value):
        raise Refused('timestamp_shape')
    datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value

def project(release, page, index):
    ocid, rid = identifier(release.get('ocid')), identifier(release.get('id'))
    if not ocid or not rid:
        raise Refused('release_identity_absent')
    tender = release.get('tender') or {}
    basis = tender.get('legalBasis') or {}
    basis_code = (basis.get('scheme'), basis.get('id'))
    # Unknown classifications are retained as unknown, never mapped to PA.
    known_basis = {('UKPGA', '2023/54'): 'UKPGA_2023_54', ('CELEX', '32014L0024'): 'CELEX_32014L0024', ('CELEX', '32014L0025'): 'CELEX_32014L0025', ('CELEX', '32009L0081'): 'CELEX_32009L0081', ('CELEX', '32014L0023'): 'CELEX_32014L0023'}
    contracts = []
    for ci, contract in enumerate(release.get('contracts') or []):
        notices = []
        for di, doc in enumerate(contract.get('documents') or []):
            # Select only the publisher's exact fixed contract-details marker.
            if doc.get('description') != 'Contract details notice on Find a Tender':
                continue
            did = identifier(doc.get('id'))
            expected = 'https://www.find-tender.service.gov.uk/Notice/' + str(did)
            if doc.get('url') != expected or not re.fullmatch(r'\d{6}-\d{4}', did or ''):
                raise Refused('notice_identity')
            notices.append({'id': did, 'url': expected, 'datePublished': instant(doc.get('datePublished')), 'locator': f'/releases/{index}/contracts/{ci}/documents/{di}'})
        threshold = contract.get('aboveThreshold')
        if threshold is not None and type(threshold) is not bool:
            raise Refused('threshold_type')
        contracts.append({'id': identifier(contract.get('id')), 'dateSigned': instant(contract.get('dateSigned')), 'aboveThreshold': threshold, 'notices': notices, 'locator': f'/releases/{index}/contracts/{ci}'})
    result = {'ocid': ocid, 'release_id': rid, 'release_date': instant(release.get('date')), 'legal_basis': known_basis.get(basis_code, 'UNKNOWN'), 'contracts': contracts, 'page': page, 'locator': f'/releases/{index}'}
    admit(result)
    return result

def counts(records):
    contracts = [c for r in records for c in r['contracts'] if c['notices']]
    both = [c for c in contracts if c['dateSigned'] and any(n['datePublished'] for n in c['notices'])]
    pa = [c for r in records if r['legal_basis'] == 'UKPGA_2023_54' for c in r['contracts'] if c['notices']]
    return {'admitted_release_rows': len(records), 'distinct_release_keys': len({(r['ocid'],r['release_id']) for r in records}), 'release_rows_with_contract_details_marker': sum(any(c['notices'] for c in r['contracts']) for r in records), 'contract_rows_with_contract_details_marker': len(contracts), 'contract_rows_with_both_dates': len(both), 'contract_rows_missing_signature_date': sum(c['dateSigned'] is None for c in contracts), 'contract_rows_missing_notice_publication_date': sum(not any(n['datePublished'] for n in c['notices']) for c in contracts), 'pa_labelled_contract_details_rows': len(pa), 'pa_labelled_above_threshold_rows': sum(c['aboveThreshold'] is True for c in pa), 'pa_labelled_below_threshold_rows': sum(c['aboveThreshold'] is False for c in pa), 'pa_labelled_threshold_unknown_rows': sum(c['aboveThreshold'] is None for c in pa), 'pa_labelled_above_threshold_rows_with_both_dates': sum(c['aboveThreshold'] is True and c['dateSigned'] is not None and any(n['datePublished'] for n in c['notices']) for c in pa)}

def main():
    url, pages, records, refusals, seen = URL, [], [], [], set()
    complete = False
    for page in range(30):
        if not url:
            complete = True
            break
        checked_url(url, URL)
        if url in seen:
            raise ValueError('pagination_cycle')
        seen.add(url)
        response = fetch(url)
        receipt = {'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'status': response['status']}
        if response['status'] != 200 or response.get('read_failed'):
            receipt['failure'] = 'http_or_body_read_failure'
            pages.append(receipt)
            break  # no retry; preserve failure, never call a partial scan complete
        body = response['body']
        receipt.update({'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)})
        doc = json.loads(body)
        rows = doc.get('releases')
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('page_shape')
        receipt['received_rows'] = len(rows)
        for i, row in enumerate(rows):
            try:
                records.append(project(row, page, i))
            except (Refused, ValueError, TypeError, AttributeError):
                refusals.append({'page': page, 'index': i, 'reason': 'field_shape_refused'})
        url = (doc.get('links') or {}).get('next')
        if url:
            checked_url(url, URL)
        receipt['next'] = url
        pages.append(receipt)
        print(json.dumps({'page': page, 'received': len(rows), 'more': bool(url)}), flush=True)
    output = {'schema': 'sunlight.section53-coverage.v1', 'query': URL, 'complete': complete, 'raw_bodies_retained': False, 'pages': pages, 'records': records, 'refusals': refusals, 'counts': counts(records)}
    admit(output)
    (HERE / 'coverage.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'complete': complete, 'refusals': len(refusals), **output['counts']}, indent=2))

if __name__ == '__main__':
    main()
