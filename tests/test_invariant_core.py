"""Synthetic reference examples only. These fixtures assert no real legal floor."""
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, localcontext
import hashlib
import json

import pytest

from invariant_core import (
    Announcement, AnnouncementSeries, Applicability, BindingStatus, Calculation,
    Citation, Conversion, InvariantError, Norm, Period, Quantity, Scope, State,
    Term, decimal, evaluate,
)

D = date.fromisoformat
P = Period(D('2026-01-01'), D('2027-01-01'))
SOURCE_TEXT = b'SYNTHETIC: producer 72; denominator 100; minimum ratio 0.70; bag factor 16. No real statute.'
C = Citation('fixture:synthetic-core-profile', 'synthetic-profile', hashlib.sha256(SOURCE_TEXT).hexdigest())
N = Norm('SYNTHETIC minimum share', 'Synthetic test instrument', P.start, C, BindingStatus.BINDING, C)
S = Scope(Applicability.APPLIES, 'Synthetic fixture explicitly in scope', (C,))


def q(amount='72', unit='money/tonne', currency='GBP', period=P, source=C):
    return Quantity(amount, unit, currency, period, source)


def check(left=None, right=None, **kwargs):
    return evaluate(left or Term('observed', q()), kwargs.pop('relation', '>='),
                    right or Term('minimum', q('70')), norm=kwargs.pop('norm', N),
                    period=kwargs.pop('period', P), scope=kwargs.pop('scope', S), **kwargs)


@pytest.mark.parametrize('bad', [0.1, 1, True, None, 'NaN', 'Infinity', '-Infinity', 'bad'])
def test_non_decimal_or_non_finite_refused(bad):
    with pytest.raises(InvariantError):
        decimal(bad)


@pytest.mark.parametrize('unit,currency', [('', 'GBP'), ('ratio', 'GBP'), ('money', 'gbp'), ('money', '')])
def test_invalid_basis_refused(unit, currency):
    with pytest.raises(InvariantError):
        q(unit=unit, currency=currency)


def test_exact_arithmetic_is_independent_of_ambient_context():
    with localcontext() as context:
        context.prec = 2
        value = Calculation('add', q('123456789.1'), q('0.2'))
        assert value.amount == Decimal('123456789.3')
        assert Calculation('subtract', q('0.3'), q('0.1')).amount == Decimal('0.2')
        assert Calculation('scale', value, q('0.25', 'ratio', None)).amount == Decimal('30864197.325')


@pytest.mark.parametrize('operation', ['add', 'subtract', 'divide'])
@pytest.mark.parametrize('other', [q(unit='money/bag'), q(currency='USD'), q(period=Period(D('2025-01-01'), P.start))])
def test_incompatible_arithmetic_refused(operation, other):
    with pytest.raises(InvariantError):
        Calculation(operation, q(), other)


@pytest.mark.parametrize('denominator', ['0', '3'])
def test_division_never_fakes_an_exact_decimal(denominator):
    with pytest.raises(InvariantError):
        Calculation('divide', q('1'), q(denominator))


def test_cited_conversion_is_explicit_and_preserved_in_finding():
    conversion = Conversion('synthetic.bags-per-tonne', '16', 'money/bag', 'GBP', 'money/tonne', 'GBP', P, C)
    converted = Calculation('convert', q('4.5', 'money/bag'), conversion=conversion)
    assert converted.amount == Decimal('72')
    finding = check(Term('converted', converted))
    data = json.loads(finding.to_json())
    assert data['left']['value']['conversion']['profile_entry'] == 'synthetic.bags-per-tonne'
    assert data['left']['value']['left']['source']['sha256'] == C.sha256
    assert data['margin']['amount'] == '2'
    assert data['margin']['unit'] == 'money/tonne'


def test_explicit_currency_conversion():
    conversion = Conversion('synthetic.fx', '0.8', 'money/tonne', 'USD', 'money/tonne', 'GBP', P, C)
    value = Calculation('convert', q('100', currency='USD'), conversion=conversion)
    assert check(Term('converted', value)).state == State.HOLDS


@pytest.mark.parametrize('change', [dict(factor='0'), dict(factor='-1'), dict(source=None), dict(profile_entry='')])
def test_bad_conversion_profile_refused(change):
    args = dict(profile_entry='synthetic.bags', factor='16', from_unit='money/bag', from_currency='GBP', to_unit='money/tonne', to_currency='GBP', period=P, source=C)
    args.update(change)
    with pytest.raises(InvariantError):
        Conversion(**args)


def test_conversion_wrong_basis_and_partial_period_refused():
    conversion = Conversion('synthetic.bags', '16', 'money/bag', 'GBP', 'money/tonne', 'GBP', Period(P.start, D('2026-07-01')), C)
    with pytest.raises(InvariantError, match='basis'):
        Calculation('convert', q(), conversion=conversion)
    with pytest.raises(InvariantError, match='entire'):
        Calculation('convert', q(unit='money/bag'), conversion=conversion)


@pytest.mark.parametrize('observed,relation,expected,margin', [('72','>=',State.HOLDS,'2'), ('70','>=',State.HOLDS,'0'), ('69','>=',State.BREAKS,'-1'), ('72','<=',State.BREAKS,'-2'), ('69','<=',State.HOLDS,'1')])
def test_inclusive_states_and_signed_margins(observed, relation, expected, margin):
    finding = check(Term('observed', q(observed)), relation=relation)
    assert finding.state == expected
    assert finding.margin.amount == Decimal(margin)
    assert finding.equation == f'observed {relation} minimum'


def test_synthetic_hand_check_and_determinism():
    ratio = Calculation('divide', q('72'), q('100'))
    finding = check(Term('announced_ratio', ratio), Term('minimum_ratio', q('0.70', 'ratio', None)))
    assert ratio.amount == Decimal('0.72')
    assert finding.margin.amount == Decimal('0.02')
    first = finding.to_json()
    with localcontext() as context:
        context.prec = 1
        assert finding.to_json() == first
    assert all(check(Term('announced_ratio', ratio), Term('minimum_ratio', q('0.70', 'ratio', None))).to_json() == first for _ in range(10))
    assert json.loads(first)['norm']['source']['sha256'] == C.sha256


def test_missing_realised_denominator_keeps_reason_publisher_and_equation():
    missing = Term('realised_denominator', None, 'Not found in this synthetic release', 'Synthetic publisher')
    finding = check(right=missing)
    assert finding.state == State.UNASSESSABLE
    assert finding.margin is None
    assert finding.equation == 'observed >= realised_denominator'
    assert 'Synthetic publisher' in finding.reason
    assert json.loads(finding.to_json())['right']['value'] is None


@pytest.mark.parametrize('other', [q(unit='money/bag'), q(currency='USD'), q(period=Period(D('2025-01-01'), P.start))])
def test_evaluator_records_mismatch_as_unassessable(other):
    finding = check(right=Term('minimum', other))
    assert finding.state == State.UNASSESSABLE
    assert finding.margin is None


def test_evaluation_period_must_match_both_terms():
    finding = check(period=Period(P.start, D('2026-07-01')))
    assert finding.state == State.UNASSESSABLE
    assert 'evaluation period' in finding.reason


def test_before_commencement_is_not_applicable_even_with_missing_terms():
    before = Period(D('2024-01-01'), P.start)
    missing = Term('observed', None, 'No source supplied', 'Synthetic publisher')
    finding = check(left=missing, period=before)
    assert finding.state == State.NOT_APPLICABLE
    assert finding.margin is None
    assert 'before commencement' in finding.reason


def test_commencement_day_applies_and_crossing_boundary_abstains():
    assert check().state == State.HOLDS
    finding = check(norm=replace(N, commencement=D('2026-06-01')))
    assert finding.state == State.UNASSESSABLE
    assert 'split' in finding.reason


def test_end_boundary_is_exclusive():
    norm = replace(N, end=D('2026-07-01'), end_source=C)
    assert check(norm=norm).state == State.UNASSESSABLE
    after = Period(norm.end, P.end)
    assert check(norm=norm, period=after).state == State.NOT_APPLICABLE


@pytest.mark.parametrize('status', [BindingStatus.UNVERIFIED, BindingStatus.NON_BINDING])
def test_uncertain_or_nonbinding_norm_never_claims_a_legal_hold(status):
    assert check(norm=replace(N, binding_status=status)).state == State.UNASSESSABLE


def test_missing_commencement_and_uncited_boundary():
    assert check(norm=replace(N, commencement=None, commencement_source=None)).state == State.UNASSESSABLE
    with pytest.raises(InvariantError, match='citation'):
        replace(N, commencement_source=None)


def test_scope_unknown_and_excluded():
    assert check(scope=Scope(Applicability.UNKNOWN, 'Regime not established')).state == State.UNASSESSABLE
    assert check(scope=Scope(Applicability.EXCLUDED, 'Cited exclusion', (C,))).state == State.NOT_APPLICABLE
    with pytest.raises(InvariantError):
        Scope(Applicability.APPLIES, 'Unsupported assertion')


def test_immutable_records_and_strict_dates():
    with pytest.raises(AttributeError):
        q().amount = Decimal('1')
    with pytest.raises(InvariantError):
        Period(datetime(2026, 1, 1), P.end)
    with pytest.raises(InvariantError):
        Period(P.end, P.start)
    with pytest.raises(InvariantError):
        Citation('source', '', C.sha256)


def announcements():
    middle = D('2026-07-01')
    return (Announcement('first', P.start, Period(P.start, middle), q('72'), C),
            Announcement('second', D('2026-06-25'), Period(middle, P.end), q('68'), C))


def test_mid_period_changes_survive_and_boundaries_are_exact():
    first, second = announcements()
    series = AnnouncementSeries((second, first))
    assert series.entries == (first, second)
    assert series.at(D('2026-06-30'), known_on=P.end).value.amount == Decimal('72')
    assert series.at(D('2026-07-01'), known_on=P.end).value.amount == Decimal('68')
    assert series.boundaries(P) == (P.start, D('2026-07-01'), P.end)
    with pytest.raises(InvariantError):
        series.at(P.end, known_on=P.end)


def test_future_announcements_and_gaps_are_not_filled():
    series = AnnouncementSeries(announcements())
    with pytest.raises(InvariantError):
        series.at(D('2026-07-01'), known_on=D('2026-06-20'))
    gap = AnnouncementSeries((announcements()[0],))
    with pytest.raises(InvariantError):
        gap.at(D('2026-08-01'), known_on=P.end)


def test_conflicting_announcements_are_preserved_but_refused_at_selection():
    first, second = announcements()
    conflicting = replace(second, effective=P)
    series = AnnouncementSeries((first, conflicting))
    assert len(series.entries) == 2
    with pytest.raises(InvariantError, match='ambiguous'):
        series.at(D('2026-06-30'), known_on=P.end)


def test_invalid_series_refused():
    first, second = announcements()
    for entries in ((), (first, first), (first, replace(second, value=q(currency='USD')))):
        with pytest.raises(InvariantError):
            AnnouncementSeries(entries)
