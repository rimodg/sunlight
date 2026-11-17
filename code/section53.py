"""Section 53 deadline mechanics over reviewed evidence, never signature proxies.

This module does not infer legal applicability. Review must admit scope and a
contract-entry source. Public availability proves an upper bound only; a late
upper bound cannot prove a late earliest qualifying event.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path

from invariant_core import (Applicability, BindingStatus, Calculation, Citation,
    InvariantError, Norm, Period, Quantity, Scope, State, Term, evaluate)


@dataclass(frozen=True)
class DatedEvidence:
    day: date
    event: str
    calendar_basis: str
    source: Citation

    def __post_init__(self):
        if type(self.day) is not date or not isinstance(self.source, Citation):
            raise InvariantError('Calendar date and citation required')
        if self.event not in {'contract_entry', 'signature', 'public_access', 'qualifying_publication'}:
            raise InvariantError('Unknown dated event')
        if not isinstance(self.calendar_basis, str) or not self.calendar_basis.strip():
            raise InvariantError('Explicit calendar basis required')


@dataclass(frozen=True)
class Publication:
    observed: DatedEvidence
    # A public timestamp by itself never establishes absence of an earlier
    # acknowledgement/alternative. A reviewed separate citation is mandatory.
    earliest_qualifying_evidence: Citation | None = None

    def __post_init__(self):
        if not isinstance(self.observed, DatedEvidence) or self.observed.event not in {'public_access', 'qualifying_publication'}:
            raise InvariantError('Publication event required')
        if self.earliest_qualifying_evidence is not None and not isinstance(self.earliest_qualifying_evidence, Citation):
            raise InvariantError('Earliest qualifying event needs a citation')
        if self.observed.event == 'qualifying_publication' and self.earliest_qualifying_evidence is None:
            raise InvariantError('Qualifying-event evidence required')


@dataclass(frozen=True)
class DeadlineProfile:
    norm: Norm
    days: Decimal
    first_day: Decimal
    threshold_source: Citation
    first_day_source: Citation
    calendar_basis: str
    unit: str

    def __post_init__(self):
        if not isinstance(self.norm, Norm) or not all(isinstance(x, Citation) for x in (self.threshold_source, self.first_day_source)):
            raise InvariantError('Cited profile required')
        for value in (self.days, self.first_day):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0 or value != value.to_integral_value():
                raise InvariantError('Positive exact integer day quantities required')
        if not self.calendar_basis or not self.unit:
            raise InvariantError('Calendar basis and unit required')


def load_profile(path: str | Path, variant: str) -> DeadlineProfile:
    data = json.loads(Path(path).read_text())
    if data.get('schema') != 'sunlight.section53-profile.v1':
        raise InvariantError('Unsupported deadline profile')
    v = data['variants'][variant]
    citation = lambda x: Citation(**x)
    norm = Norm(v['provision_text'], data['instrument'], date.fromisoformat(data['commencement']),
                citation(v['source']), BindingStatus(data['binding_status']), citation(data['commencement_source']))
    return DeadlineProfile(norm, Decimal(v['days']), Decimal(data['first_day']['amount']),
                           citation(v['source']), citation(data['first_day']['source']),
                           data['calendar_basis'], data['unit'])


def assess(*, entry: DatedEvidence | None, publication: Publication | None,
           scope: Scope, profile: DeadlineProfile):
    """A complete four-state result; all comparisons are exact calendar arithmetic.

    The explicit entry-date gate precedes scope evaluation by owner instruction.
    No signature event, inferred one-sided date bound or release timestamp is
    accepted as contract entry. Missing values retain named publishers.
    """
    if entry is not None and (not isinstance(entry, DatedEvidence) or entry.event != 'contract_entry'):
        raise InvariantError('Explicit contract-entry evidence required; signature is not entry')
    if publication is not None and not isinstance(publication, Publication):
        raise InvariantError('Typed publication evidence required')
    if not isinstance(scope, Scope) or not isinstance(profile, DeadlineProfile):
        raise InvariantError('Reviewed scope and profile required')
    # This placeholder window only lets the core express missing evidence; it
    # is never emitted as an observed entry date or used to infer non-applicability.
    anchor = entry.day if entry else profile.norm.commencement
    period = Period(anchor, anchor + timedelta(days=1))
    right = Term('statutory_day_limit', Quantity(profile.days, profile.unit, None, period, profile.threshold_source))
    left = Term('inclusive_days_from_entry_to_qualifying_publication', None,
                'Explicit contract-entry date not admitted; dateSigned is not substituted', 'Contracting authority')
    if entry is None:
        return evaluate(left, '<=', right, norm=profile.norm, period=period,
                        scope=Scope(Applicability.UNKNOWN, left.missing_reason))
    problem = None
    if entry.calendar_basis != profile.calendar_basis:
        problem = 'Entry calendar basis differs from the cited profile'
    elif publication is None:
        problem = 'Qualifying publication evidence not admitted'
    elif publication.observed.calendar_basis != entry.calendar_basis:
        problem = 'Publication and entry calendar bases differ'
    elif publication.observed.day < entry.day:
        problem = 'Publication precedes the admitted entry date; event identity requires review'
    if problem:
        left = Term(left.name, None, problem, 'Contracting authority / central digital platform')
    else:
        observed = publication.observed
        start = Quantity(Decimal(entry.day.toordinal()), profile.unit, None, period, entry.source)
        end = Quantity(Decimal(observed.day.toordinal()), profile.unit, None, period, observed.source)
        elapsed = Calculation('subtract', end, start)
        inclusive = Calculation('add', elapsed, Quantity(profile.first_day, profile.unit, None, period, profile.first_day_source))
        left = Term(left.name, inclusive)
    finding = evaluate(left, '<=', right, norm=profile.norm, period=period, scope=scope)
    if finding.state == State.BREAKS and publication.earliest_qualifying_evidence is None:
        # Drop the would-be statutory margin: the observed late upper bound is
        # not the legally qualifying event being tested. Keep it in the packet.
        missing = Term(left.name, None, 'Earlier successful submission or qualifying alternative publication is unresolved',
                       'Contracting authority / Cabinet Office')
        finding = evaluate(missing, '<=', right, norm=profile.norm, period=period, scope=scope)
    return finding


def packet(*, entry, publication, scope, profile):
    """Include event-level evidence even when a statutory margin is undefined."""
    from dataclasses import asdict
    def event(value):
        return None if value is None else {'day': value.day.isoformat(), 'event': value.event,
            'calendar_basis': value.calendar_basis, 'source': asdict(value.source)}
    result = assess(entry=entry, publication=publication, scope=scope, profile=profile)
    return {'schema': 'sunlight.section53-indicator.v1', 'indicator_only': True,
            'contract_entry': event(entry),
            'observed_publication': event(publication.observed) if publication else None,
            'earliest_qualifying_evidence': asdict(publication.earliest_qualifying_evidence) if publication and publication.earliest_qualifying_evidence else None,
            'evaluation_period_basis': 'admitted_entry_day' if entry else 'placeholder_for_missing_entry_not_an_observation',
            'finding': json.loads(result.to_json())}
