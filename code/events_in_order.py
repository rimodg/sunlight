"""Record consistency: an award is not dated before its own tender deadline.

This is NOT a legal rule and never uses the legal states HOLDS or BREAKS.
Both dates are defined by a published data standard; the result says only
whether one record agrees with its own published dates. Every result is a
risk indicator, never an allegation. Missing is not zero.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path

from invariant_core import Citation, InvariantError

SCHEMA = 'sunlight.events-in-order-profile.v1'


class Consistency(str, Enum):
    CONSISTENT = 'CONSISTENT'
    INCONSISTENT = 'INCONSISTENT'
    UNASSESSABLE = 'UNASSESSABLE'
    NOT_APPLICABLE = 'NOT_APPLICABLE'


@dataclass(frozen=True)
class Method:
    applicability: str
    text: str

    def __post_init__(self):
        if self.applicability not in {'APPLIES', 'EXCLUDED', 'UNKNOWN'}:
            raise InvariantError('Explicit method applicability required')
        if not isinstance(self.text, str) or not self.text.strip():
            raise InvariantError('Method definition text required')


@dataclass(frozen=True)
class OrderProfile:
    instrument: str
    legal_status: str
    calendar_basis: str
    tender_end_text: str
    tender_end_source: Citation
    award_date_text: str
    award_date_source: Citation
    method_source: Citation
    methods: tuple[tuple[str, Method], ...]

    def method(self, code):
        return dict(self.methods).get(code)


def load_profile(path: str | Path) -> OrderProfile:
    data = json.loads(Path(path).read_text())
    if data.get('schema') != SCHEMA or data.get('rule_class') != 'record_consistency':
        raise InvariantError('Unsupported events-in-order profile')
    d = data['definitions']
    methods = tuple(sorted((k, Method(**v)) for k, v in data['methods'].items()))
    return OrderProfile(data['instrument'], data['legal_status'], data['calendar_basis'],
                        d['tender_end']['text'], Citation(**d['tender_end']['source']),
                        d['award_date']['text'], Citation(**d['award_date']['source']),
                        Citation(**data['method_source']), methods)


@dataclass(frozen=True)
class OrderResult:
    state: Consistency
    reason: str
    statement: str
    award_date: str | None
    tender_end_date: str | None
    procurement_method: str | None
    days_award_after_deadline: int | None
    deadline_after_notice_publication: bool | None
    rule_class: str = 'record_consistency'
    indicator_only: bool = True


def _stamp(value):
    """A published ISO 8601 timestamp with an explicit offset, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def assess(*, award_date, tender_end_date, procurement_method,
           publication_date=None, profile: OrderProfile) -> OrderResult:
    """Total over any input. Conservative: doubt is UNASSESSABLE, never a guess."""
    if not isinstance(profile, OrderProfile):
        raise InvariantError('Cited profile required')
    statement = 'awards[].date is not earlier than tender.tenderPeriod.endDate'
    award, end, published = _stamp(award_date), _stamp(tender_end_date), _stamp(publication_date)
    gap = (award.date() - end.date()).days if award and end else None
    late_deadline = (end.date() > published.date()) if end and published else None

    def result(state, reason):
        return OrderResult(state, reason, statement,
                           award_date if isinstance(award_date, str) else None,
                           tender_end_date if isinstance(tender_end_date, str) else None,
                           procurement_method if isinstance(procurement_method, str) else None,
                           gap, late_deadline)

    method = profile.method(procurement_method) if isinstance(procurement_method, str) else None
    if method is None:
        return result(Consistency.UNASSESSABLE,
                      'Procurement method is missing or not in the cited codelist; expected publisher: contracting authority')
    if method.applicability == 'EXCLUDED':
        return result(Consistency.NOT_APPLICABLE,
                      'Cited method definition has no competitive submission period: ' + method.text)
    if method.applicability == 'UNKNOWN':
        return result(Consistency.UNASSESSABLE,
                      'Cited method definition does not establish a submission period: ' + method.text)
    if award is None or end is None:
        missing = [name for name, value in (('awards[].date', award), ('tender.tenderPeriod.endDate', end)) if value is None]
        return result(Consistency.UNASSESSABLE,
                      'Missing or unreadable date with explicit offset: ' + ', '.join(missing) + '; expected publisher: contracting authority')
    if gap == 0:
        return result(Consistency.UNASSESSABLE,
                      'Both dates fall on the same civil day; the order within the day is not established')
    if award.utcoffset() != end.utcoffset():
        # The award time of day is not published, so the award is a whole
        # civil day in its own offset. In different offsets the civil order is
        # trusted only when that whole day lies on the same side of the
        # deadline instant. This can only add refusals, never answers.
        day_start = award.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        instants_agree = day_start >= end if gap > 0 else day_end <= end
        if abs(gap) == 1 or not instants_agree:
            return result(Consistency.UNASSESSABLE,
                          'Dates are in different offsets and the order is not established')
    if gap > 0:
        return result(Consistency.CONSISTENT, 'Award is dated after the closing date for submissions')
    return result(Consistency.INCONSISTENT,
                  'Award is dated before the closing date for submissions in the same record')


def packet(result: OrderResult, profile: OrderProfile) -> dict:
    """The result with the citations it rests on, and no others."""
    return {'schema': 'sunlight.events-in-order-indicator.v1',
            'result': {**asdict(result), 'state': result.state.value},
            'legal_status': profile.legal_status,
            'instrument': profile.instrument,
            'calendar_basis': profile.calendar_basis,
            'citations': {'tender_end': {'text': profile.tender_end_text, **asdict(profile.tender_end_source)},
                          'award_date': {'text': profile.award_date_text, **asdict(profile.award_date_source)},
                          'procurement_method': asdict(profile.method_source)}}
