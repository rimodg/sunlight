"""Replay the events-in-order consistency rule over an exported pair set.

Reads only; refuses to overwrite an existing output.
Usage: PYTHONPATH=code python scripts/measure_events_in_order.py PAIRS PROFILE OUT
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from events_in_order import assess, load_profile


def replay(pairs: dict, profile) -> dict:
    rows = []
    for pair in sorted(pairs['pairs'], key=lambda p: (p['ocid'], p['award_id'], p['award_date'], p['tender_end_date'])):
        r = assess(award_date=pair.get('award_date'), tender_end_date=pair.get('tender_end_date'),
                   procurement_method=pair.get('procurement_method'),
                   publication_date=pair.get('publication_date'), profile=profile)
        rows.append({'ocid': pair['ocid'], 'award_id': pair['award_id'],
                     'capture_seq': pair.get('capture_seq'), 'capture_hash': pair.get('capture_hash'),
                     'award_date': r.award_date, 'tender_end_date': r.tender_end_date,
                     'procurement_method': r.procurement_method,
                     'days_award_after_deadline': r.days_award_after_deadline,
                     'deadline_after_notice_publication': r.deadline_after_notice_publication,
                     'state': r.state.value, 'reason': r.reason})
    states = Counter(row['state'] for row in rows)
    flagged = [row for row in rows if row['state'] == 'INCONSISTENT']
    return {'schema': 'sunlight.events-in-order-results.v1', 'rule_class': 'record_consistency',
            'indicator_only': True, 'legal_status': profile.legal_status,
            'population': len(rows),
            'states': {k: states.get(k, 0) for k in ('CONSISTENT', 'INCONSISTENT', 'UNASSESSABLE', 'NOT_APPLICABLE')},
            'answered': states.get('CONSISTENT', 0) + states.get('INCONSISTENT', 0),
            'inconsistent_with_deadline_after_notice_publication':
                sum(1 for row in flagged if row['deadline_after_notice_publication']),
            'results': rows}


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n'


if __name__ == '__main__':
    pairs_path, profile_path, out_path = map(Path, sys.argv[1:4])
    if out_path.exists():
        raise SystemExit('Refusing to overwrite an existing output')
    raw = pairs_path.read_bytes()
    out = replay(json.loads(raw), load_profile(profile_path))
    out['input_sha256'] = hashlib.sha256(raw).hexdigest()
    out_path.write_text(canonical(out))
    print(json.dumps({k: out[k] for k in ('population', 'states', 'answered', 'inconsistent_with_deadline_after_notice_publication')}))
