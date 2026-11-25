"""Replay the events-in-order consistency rule over an exported pair set.

Reads only; refuses to overwrite an existing output. Every result row carries
the sealed watcher's lens (the facts read from the pair and the selection row
that matched, see code/watcher.py) and is stamped with the journal capture it
cites and the exact rule version that computed it (see code/custody.py).
The watcher runs only if it is on the roster with the seal the roster pins
(see code/roster.py); the results file names that roster.
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
from roster import ROSTER_FILE, enrol, load_roster, reference
from watcher import lens, load_watcher, seal

ROOT = Path(__file__).resolve().parents[1]
RULE_MODULE = 'code/events_in_order.py'
RULE_PROFILE = 'config/events-in-order-profile.json'
WATCHER_FILE = 'config/watchers/events-in-order.json'


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


def current_watcher(root=ROOT) -> tuple[dict, dict]:
    """The watcher as loaded from the checkout and its seal."""
    return load_watcher(root, WATCHER_FILE), seal(root, WATCHER_FILE)


def current_roster(root=ROOT) -> dict:
    return load_roster(root, ROSTER_FILE)


def replay(pairs: dict, profile, rule: dict | None = None, watcher: tuple[dict, dict] | None = None,
           roster: dict | None = None, root=ROOT) -> dict:
    """Assess every exported pair with `profile` under `rule`, through `watcher`.

    Without `rule`, the default rule version (RULE_PROFILE) is used, and only
    for the profile that version names: a different profile must come with
    the rule version that hashes it, or the results would claim a rule that
    did not compute them.
    """
    if rule is None:
        if profile != load_profile(ROOT / RULE_PROFILE):
            raise InvariantError('Rule version required for a profile other than the default')
        rule = current_rule_version()
    watcher, sealed = current_watcher() if watcher is None else watcher
    roster = current_roster(root) if roster is None else roster
    enrol(roster, sealed, WATCHER_FILE)  # A watcher not on the roster does not run.
    rows = []
    for pair in sorted(pairs['pairs'], key=lambda p: (p['ocid'], p['award_id'], p['award_date'], p['tender_end_date'])):
        block = lens(watcher, sealed, pair)
        row = {'ocid': pair['ocid'], 'award_id': pair['award_id']}
        if block['selection']['outcome'] == 'SELECTED':
            r = assess(award_date=pair.get('award_date'), tender_end_date=pair.get('tender_end_date'),
                       procurement_method=pair.get('procurement_method'),
                       publication_date=pair.get('publication_date'), profile=profile)
            row.update(award_date=r.award_date, tender_end_date=r.tender_end_date,
                       procurement_method=r.procurement_method,
                       days_award_after_deadline=r.days_award_after_deadline,
                       deadline_after_notice_publication=r.deadline_after_notice_publication,
                       state=r.state.value, reason=r.reason)
        else:
            # The rule did not run. The row says so in the watcher's own words.
            row.update(award_date=pair.get('award_date') if isinstance(pair.get('award_date'), str) else None,
                       tender_end_date=pair.get('tender_end_date') if isinstance(pair.get('tender_end_date'), str) else None,
                       procurement_method=pair.get('procurement_method') if isinstance(pair.get('procurement_method'), str) else None,
                       days_award_after_deadline=None, deadline_after_notice_publication=None,
                       state='UNASSESSABLE', reason='Not selected by the watcher: ' + block['selection']['reason'])
        row['watcher'] = block
        rows.append(stamp(row, source={'capture_seq': pair.get('capture_seq'),
                                       'capture_hash': pair.get('capture_hash')}, rule=rule))
    states = Counter(row['state'] for row in rows)
    flagged = [row for row in rows if row['state'] == 'INCONSISTENT']
    return {'schema': 'sunlight.events-in-order-results.v4', 'rule_class': 'record_consistency',
            'indicator_only': True, 'legal_status': profile.legal_status, 'rule_version': rule,
            'watcher_seal': sealed, 'roster': reference(root, roster, ROSTER_FILE),
            'population': len(rows),
            'not_selected': sum(1 for row in rows if row['watcher']['selection']['outcome'] == 'NOT_SELECTED'),
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
