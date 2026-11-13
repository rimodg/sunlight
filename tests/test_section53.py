"""Constructed deadline fixtures; no fixture is evidence about a real authority."""
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import json

import pytest
from invariant_core import Applicability, Citation, InvariantError, Scope, State
from section53 import DatedEvidence, Publication, assess, load_profile, packet

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Citation('synthetic://section53/entry', 'synthetic fixture, not a real contract', 'a' * 64)
PUB = Citation('synthetic://section53/publication', 'synthetic fixture, not a real notice', 'b' * 64)
EARLIEST = Citation('synthetic://section53/review', 'synthetic review excludes earlier qualifying events', 'c' * 64)
SCOPE = Scope(Applicability.APPLIES, 'Synthetic in-scope ordinary public contract, all exclusions reviewed', (SOURCE,))
PROFILE = load_profile(ROOT / 'config/section53-profile.json', 'ordinary')


def entry(day=date(2026, 11, 3)):
    return DatedEvidence(day, 'contract_entry', 'UK civil calendar', SOURCE)


def publication(day=date(2026, 11, 12), earliest=None):
    return Publication(DatedEvidence(day, 'public_access', 'UK civil calendar', PUB), earliest)


def run(e=None, p=None, **kw):
    return assess(entry=e or entry(), publication=p or publication(), scope=kw.pop('scope', SCOPE), profile=kw.pop('profile', PROFILE), **kw)


@pytest.mark.parametrize('offset,state,margin', [(0, State.HOLDS, '29'), (9, State.HOLDS, '20'), (29, State.HOLDS, '0'), (30, State.BREAKS, '-1')])
def test_exact_inclusive_deadline_synthetic(offset, state, margin):
    result = run(p=publication(entry().day + timedelta(days=offset), EARLIEST))
    assert result.state == state
    assert result.margin.amount == Decimal(margin)
    encoded = result.to_json()
    assert SOURCE.sha256 in encoded and PUB.sha256 in encoded
    assert PROFILE.threshold_source.sha256 in encoded


def test_signature_refused_even_with_citation():
    with pytest.raises(InvariantError, match='signature is not entry'):
        run(e=replace(entry(), event='signature'))


def test_no_entry_is_unassessable_even_if_below_threshold_scope():
    result = assess(entry=None, publication=publication(), profile=PROFILE,
                    scope=Scope(Applicability.EXCLUDED, 'Synthetic below threshold', (SOURCE,)))
    assert result.state == State.UNASSESSABLE
    assert result.margin is None
    assert 'dateSigned' in result.reason


def test_no_entry_does_not_invent_earlier_commencement():
    result = assess(entry=None, publication=publication(date(2024, 1, 1)), scope=SCOPE, profile=PROFILE)
    assert result.state == State.UNASSESSABLE


def test_pre_commencement_not_applicable():
    result = run(e=entry(date(2025, 2, 23)), p=publication(date(2025, 3, 1)))
    assert result.state == State.NOT_APPLICABLE
    assert result.margin is None


@pytest.mark.parametrize('reason', ['below threshold', 'private utility', 'user-choice award', 'saved PCR procurement'])
def test_explicit_cited_exclusion_not_applicable(reason):
    result = run(scope=Scope(Applicability.EXCLUDED, 'Synthetic ' + reason, (SOURCE,)))
    assert result.state == State.NOT_APPLICABLE


def test_missing_scope_not_assumed_from_pa_label():
    assert run(scope=Scope(Applicability.UNKNOWN, 'Regime and scope not established')).state == State.UNASSESSABLE


def test_late_public_time_cannot_prove_break_without_earliest_event_evidence():
    result = run(p=publication(date(2026, 12, 3)))
    assert result.state == State.UNASSESSABLE
    assert result.margin is None
    assert 'alternative' in result.reason


def test_earlier_successful_event_can_hold_despite_later_public_time():
    # Explicit admitted event, not inferred from the late public timestamp.
    p = Publication(DatedEvidence(date(2026, 11, 30), 'qualifying_publication', 'UK civil calendar', PUB), EARLIEST)
    assert run(p=p).state == State.HOLDS


def test_qualifying_event_requires_separate_evidence():
    with pytest.raises(InvariantError, match='Qualifying-event'):
        Publication(replace(publication().observed, event='qualifying_publication'))


def test_light_touch_uses_cited_distinct_profile():
    light = load_profile(ROOT / 'config/section53-profile.json', 'light_touch')
    r = run(p=publication(entry().day + timedelta(days=119), EARLIEST), profile=light,
            scope=Scope(Applicability.APPLIES, 'Synthetic reviewed light-touch scope', (SOURCE,)))
    assert r.state == State.HOLDS and r.margin.amount == 0
    assert '120' in r.to_json() and '53(1)(a)' in r.to_json()


@pytest.mark.parametrize('start,end,expected', [(date(2028,2,1),date(2028,3,1),'0'), (date(2026,12,20),date(2027,1,18),'0'), (date(2026,3,20),date(2026,4,18),'0')])
def test_calendar_not_elapsed_hours(start,end,expected):
    r=run(e=entry(start),p=publication(end,EARLIEST))
    assert r.margin.amount == Decimal(expected)


def test_calendar_basis_mismatch_refused():
    p=Publication(replace(publication().observed, calendar_basis='UTC calendar'))
    assert run(p=p).state == State.UNASSESSABLE


def test_publication_before_entry_is_data_ambiguity():
    assert run(p=publication(date(2026,11,2))).state == State.UNASSESSABLE


def test_missing_publication_names_expected_publisher():
    r=assess(entry=entry(),publication=None,scope=SCOPE,profile=PROFILE)
    assert r.state == State.UNASSESSABLE and 'central digital platform' in r.reason


def test_all_states_have_equation_and_null_margin_explained():
    cases=[packet(entry=entry(),publication=publication(),scope=SCOPE,profile=PROFILE),
           packet(entry=None,publication=publication(),scope=SCOPE,profile=PROFILE),
           packet(entry=entry(),publication=publication(date(2026,12,3),EARLIEST),scope=SCOPE,profile=PROFILE),
           packet(entry=entry(date(2024,1,1)),publication=publication(),scope=SCOPE,profile=PROFILE)]
    assert {r['finding']['state'] for r in cases} == {s.value for s in State}
    for r in cases:
        assert '<=' in r['finding']['equation'] and r['finding']['reason']
        assert r['indicator_only'] is True
    assert cases[1]['contract_entry'] is None
    assert cases[1]['evaluation_period_basis'].startswith('placeholder')
    assert cases[2]['earliest_qualifying_evidence']['sha256'] == EARLIEST.sha256


def test_deterministic_exact_arithmetic_includes_sources():
    values=[json.dumps(packet(entry=entry(),publication=publication(),scope=SCOPE,profile=PROFILE),sort_keys=True) for _ in range(20)]
    assert len(set(values)) == 1
    assert '20' in values[0]


@pytest.mark.parametrize('bad',[30.0, Decimal('NaN'), Decimal('1.5'), Decimal('-1')])
def test_profile_refuses_nonexact_or_invalid_day_counts(bad):
    with pytest.raises(InvariantError): replace(PROFILE,days=bad)
