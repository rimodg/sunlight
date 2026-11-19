"""Events-in-order consistency rule. Constructed cases, then a replay of the
measured export. No case here is evidence about a real authority."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import pytest
from invariant_core import InvariantError, State
from events_in_order import Consistency, Method, assess, load_profile, packet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from measure_events_in_order import canonical, replay  # noqa: E402

PROFILE = load_profile(ROOT / 'config' / 'events-in-order-profile.json')
RESEARCH = ROOT / 'research' / 'events_in_order_2026-11-18'


def run(award='2026-03-10T00:00:00Z', end='2026-03-01T12:00:00Z', method='open', pub=None, profile=PROFILE):
    return assess(award_date=award, tender_end_date=end, procurement_method=method,
                  publication_date=pub, profile=profile)


def test_award_after_deadline_is_consistent():
    r = run()
    assert r.state is Consistency.CONSISTENT and r.days_award_after_deadline == 9


def test_award_before_deadline_is_inconsistent():
    r = run(award='2026-02-20T00:00:00Z')
    assert r.state is Consistency.INCONSISTENT and r.days_award_after_deadline == -9


def test_same_civil_day_is_unassessable_not_guessed():
    r = run(award='2026-03-01T00:00:00Z')
    assert r.state is Consistency.UNASSESSABLE and 'same civil day' in r.reason


def test_one_day_apart_in_different_offsets_is_unassessable():
    r = run(award='2026-07-31T00:00:00Z', end='2026-08-01T00:00:00+01:00')
    assert r.state is Consistency.UNASSESSABLE and 'different offsets' in r.reason
    assert run(award='2026-07-31T00:00:00Z', end='2026-08-01T12:00:00Z').state is Consistency.INCONSISTENT


def test_extreme_offsets_cannot_flip_the_order_at_any_civil_gap():
    # Both probes were raised in review of PR #26.
    a = run(award='2026-03-03T00:00:00+14:00', end='2026-03-01T23:59:00-12:00')
    b = run(award='2026-03-01T23:00:00-12:00', end='2026-03-03T00:00:00+14:00')
    assert a.days_award_after_deadline == 2 and b.days_award_after_deadline == -2
    assert a.state is b.state is Consistency.UNASSESSABLE
    assert 'different offsets' in a.reason and 'different offsets' in b.reason


def test_different_offsets_still_answer_when_the_whole_award_day_is_clear():
    assert run(award='2026-03-10T00:00:00Z', end='2026-03-01T12:00:00+01:00').state is Consistency.CONSISTENT
    assert run(award='2026-02-20T00:00:00Z', end='2026-03-01T12:00:00+01:00').state is Consistency.INCONSISTENT


@pytest.mark.parametrize('method', [None, '', 'framework', 7])
def test_missing_or_unknown_method_is_unassessable(method):
    r = run(method=method)
    assert r.state is Consistency.UNASSESSABLE and 'expected publisher' in r.reason


def test_direct_is_not_applicable_and_limited_is_unassessable():
    assert run(method='direct', award='2026-02-01T00:00:00Z').state is Consistency.NOT_APPLICABLE
    assert run(method='limited', award='2026-02-01T00:00:00Z').state is Consistency.UNASSESSABLE


@pytest.mark.parametrize('bad', [None, '', 'not a date', '2026-03-10', '2026-03-10T00:00:00', 0, [], {}])
def test_missing_or_offsetless_dates_are_unassessable_never_zero(bad):
    for kwargs in ({'award': bad}, {'end': bad}):
        r = run(**kwargs)
        assert r.state is Consistency.UNASSESSABLE
        assert r.days_award_after_deadline is None
        assert 'expected publisher' in r.reason


def test_applicability_comes_from_the_profile_not_the_code():
    methods = tuple((k, Method('EXCLUDED', m.text) if k == 'open' else m) for k, m in PROFILE.methods)
    assert run(profile=replace(PROFILE, methods=methods)).state is Consistency.NOT_APPLICABLE


def test_deadline_after_notice_publication_is_reported_not_scored():
    early = run(award='2026-02-20T00:00:00Z', pub='2026-02-25T09:00:00Z')
    late = run(award='2026-02-20T00:00:00Z', pub='2026-03-05T09:00:00Z')
    assert early.deadline_after_notice_publication is True
    assert late.deadline_after_notice_publication is False
    assert early.state is late.state is Consistency.INCONSISTENT
    assert run().deadline_after_notice_publication is None


def test_deterministic_and_never_a_legal_state():
    a, b = run(award='2026-02-20T00:00:00Z'), run(award='2026-02-20T00:00:00Z')
    assert a == b
    legal = {s.value for s in State}
    assert not {'HOLDS', 'BREAKS'} & {c.value for c in Consistency}
    assert a.state.value not in legal - {'UNASSESSABLE', 'NOT_APPLICABLE'}
    assert a.indicator_only is True and a.rule_class == 'record_consistency'


def test_packet_cites_only_its_own_sources_and_states_legal_limit():
    p = packet(run(award='2026-02-20T00:00:00Z'), PROFILE)
    text = json.dumps(p)
    assert set(p['citations']) == {'tender_end', 'award_date', 'procurement_method'}
    assert 'Not a legal norm' in p['legal_status']
    assert 'legislation.gov.uk' not in text and 'FAR' not in text
    for word in ('fraud', 'corrupt', 'illegal', 'unlawful', 'breach of law'):
        assert word not in text.lower()
    assert all(len(c['sha256']) == 64 for c in p['citations'].values())


def test_profile_must_be_typed_and_of_the_right_class(tmp_path):
    with pytest.raises(InvariantError):
        run(profile={'methods': {}})
    bad = tmp_path / 'p.json'
    data = json.loads((ROOT / 'config' / 'events-in-order-profile.json').read_text())
    data['rule_class'] = 'legal_compliance'
    bad.write_text(json.dumps(data))
    with pytest.raises(InvariantError):
        load_profile(bad)


def test_replay_of_measured_export_matches_stored_results_byte_for_byte():
    raw = (RESEARCH / 'pairs.json').read_bytes()
    stored_text = (RESEARCH / 'results.json').read_text()
    stored = json.loads(stored_text)
    again = replay(json.loads(raw), PROFILE)
    again['input_sha256'] = hashlib.sha256(raw).hexdigest()
    assert canonical(again) == stored_text
    assert stored['population'] == 193
    assert stored['states'] == {'CONSISTENT': 119, 'INCONSISTENT': 5, 'UNASSESSABLE': 60, 'NOT_APPLICABLE': 9}
    assert stored['answered'] == 124
    assert sum(stored['states'].values()) == stored['population']


def test_replay_is_independent_of_input_order():
    pairs = json.loads((RESEARCH / 'pairs.json').read_text())
    flipped = {**pairs, 'pairs': list(reversed(pairs['pairs']))}
    assert replay(pairs, PROFILE) == replay(flipped, PROFILE)


def test_no_em_dash_and_no_personal_shaped_content_in_outputs():
    for path in (RESEARCH / 'results.json', ROOT / 'config' / 'events-in-order-profile.json',
                 ROOT / 'code' / 'events_in_order.py'):
        text = path.read_text()
        assert chr(0x2014) not in text
    assert '@' not in (RESEARCH / 'results.json').read_text()
