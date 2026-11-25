"""Replay the events-in-order consistency rule over an exported pair set.

Reads only; refuses to overwrite an existing output. Every result row is
stamped with the journal capture it cites and the exact rule version that
computed it (see code/custody.py).
Usage: PYTHONPATH=code python scripts/measure_events_in_order.py PAIRS PROFILE OUT
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from custody import rule_version, stamp
from invariant_core import InvariantError
from events_in_order import assess, load_profile

ROOT = Path(__file__).resolve().parents[1]
RULE_MODULE = 'code/events_in_order.py'
RULE_PROFILE = 'config/events-in-order-profile.json'


def current_rule_version(root=ROOT, profile: str = RULE_PROFILE) -> dict:
    return rule_version(rule_id='events_in_order', root=root, module=RULE_MODULE, profile=profile)


def profile_in_repository(profile_path, root=ROOT) -> str:
    """The profile's path relative to the repository, or a refusal.

    The rule version hashes the profile the replay actually uses, so that
    profile must be a file inside the repository the version names.
    """
    try:
        relative = Path(profile_path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        raise SystemExit('Profile must be inside the repository') from None
    return relative.as_posix()


def replay(pairs: dict, profile, rule: dict | None = None) -> dict:
    """Assess every exported pair with `profile` under `rule`.

    Without `rule`, the default rule version (RULE_PROFILE) is used, and only
    for the profile that version names: a different profile must come with
    the rule version that hashes it, or the results would claim a rule that
    did not compute them.
    """
    if rule is None:
        if profile != load_profile(ROOT / RULE_PROFILE):
            raise InvariantError('Rule version required for a profile other than the default')
        rule = current_rule_version()
    rows = []
    for pair in sorted(pairs['pairs'], key=lambda p: (p['ocid'], p['award_id'], p['award_date'], p['tender_end_date'])):
        r = assess(award_date=pair.get('award_date'), tender_end_date=pair.get('tender_end_date'),
                   procurement_method=pair.get('procurement_method'),
                   publication_date=pair.get('publication_date'), profile=profile)
        row = {'ocid': pair['ocid'], 'award_id': pair['award_id'],
               'award_date': r.award_date, 'tender_end_date': r.tender_end_date,
               'procurement_method': r.procurement_method,
               'days_award_after_deadline': r.days_award_after_deadline,
               'deadline_after_notice_publication': r.deadline_after_notice_publication,
               'state': r.state.value, 'reason': r.reason}
        rows.append(stamp(row, source={'capture_seq': pair.get('capture_seq'),
                                       'capture_hash': pair.get('capture_hash')}, rule=rule))
    states = Counter(row['state'] for row in rows)
    flagged = [row for row in rows if row['state'] == 'INCONSISTENT']
    return {'schema': 'sunlight.events-in-order-results.v2', 'rule_class': 'record_consistency',
            'indicator_only': True, 'legal_status': profile.legal_status, 'rule_version': rule,
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
    # The rule version names the profile the replay uses, never the default one.
    rule = current_rule_version(profile=profile_in_repository(profile_path))
    out = replay(json.loads(raw), load_profile(profile_path), rule)
    out['input_sha256'] = hashlib.sha256(raw).hexdigest()
    out_path.write_text(canonical(out))
    print(json.dumps({k: out[k] for k in ('population', 'states', 'answered', 'inconsistent_with_deadline_after_notice_publication')}))
