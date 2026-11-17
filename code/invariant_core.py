"""Source-bearing invariant primitives. No jurisdictional rules or unit constants.

Periods and effective windows are half-open [start, end). Decimal operations
are exact: a non-terminating decimal is refused, never silently rounded.
A citation records provenance, not proof of authenticity or legal applicability.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from fractions import Fraction
import json
import re


class InvariantError(ValueError):
    """An unsafe or ambiguous calculation was refused."""


def _text(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvariantError("Non-empty text required")


def _date(value: date) -> None:
    if type(value) is not date:
        raise InvariantError("A calendar date is required, not a timestamp")


def decimal(value: str | Decimal) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise InvariantError("Use a decimal string or Decimal, never a float")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise InvariantError("Invalid decimal") from exc
    if not result.is_finite():
        raise InvariantError("Finite decimal required")
    return result


def _exact(value: Fraction) -> Decimal:
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise InvariantError("Non-terminating decimal; no rounding policy supplied")
    places = max(twos, fives)
    coefficient = value.numerator * 2 ** (places - twos) * 5 ** (places - fives)
    digits = tuple(int(c) for c in str(abs(coefficient)))
    return Decimal((int(coefficient < 0), digits, -places))


@dataclass(frozen=True)
class Citation:
    source: str
    locator: str
    sha256: str

    def __post_init__(self):
        _text(self.source)
        _text(self.locator)
        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise InvariantError("Lowercase SHA-256 required")


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    def __post_init__(self):
        _date(self.start)
        _date(self.end)
        if self.end <= self.start:
            raise InvariantError("Period end must follow start")

    def covers(self, other: Period) -> bool:
        return self.start <= other.start and other.end <= self.end


@dataclass(frozen=True)
class Quantity:
    amount: Decimal
    unit: str
    currency: str | None
    period: Period
    source: Citation

    def __post_init__(self):
        object.__setattr__(self, "amount", decimal(self.amount))
        _basis(self.unit, self.currency)
        if not isinstance(self.period, Period) or not isinstance(self.source, Citation):
            raise InvariantError("Quantity needs a period and citation")


def _basis(unit: str, currency: str | None) -> None:
    _text(unit)
    if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
        raise InvariantError("Currency must be an uppercase three-letter code or None")
    if unit == "ratio" and currency is not None:
        raise InvariantError("A ratio is dimensionless")


@dataclass(frozen=True)
class Conversion:
    """Cited profile entry; result = input * factor, valid for the whole period."""
    profile_entry: str
    factor: Decimal
    from_unit: str
    from_currency: str | None
    to_unit: str
    to_currency: str | None
    period: Period
    source: Citation

    def __post_init__(self):
        _text(self.profile_entry)
        object.__setattr__(self, "factor", decimal(self.factor))
        if self.factor <= 0:
            raise InvariantError("Conversion factor must be positive")
        _basis(self.from_unit, self.from_currency)
        _basis(self.to_unit, self.to_currency)
        if not isinstance(self.period, Period) or not isinstance(self.source, Citation):
            raise InvariantError("Conversion needs a period and citation")


def _same(left: Value, right: Value):
    if left.unit != right.unit:
        raise InvariantError("Unit mismatch: a cited conversion is required")
    if left.currency != right.currency:
        raise InvariantError("Currency mismatch: a cited conversion is required")
    if left.period != right.period:
        raise InvariantError("Period mismatch: implicit aggregation is forbidden")


@dataclass(frozen=True)
class Calculation:
    """Expression tree: derived values never masquerade as published figures."""
    operation: str
    left: Value
    right: Value | None = None
    conversion: Conversion | None = None

    def __post_init__(self):
        if not isinstance(self.left, (Quantity, Calculation)):
            raise InvariantError("A sourced operand is required")
        if self.operation == "convert":
            c = self.conversion
            if not isinstance(c, Conversion) or self.right is not None:
                raise InvariantError("Conversion requires exactly one cited profile entry")
            if (self.left.unit, self.left.currency) != (c.from_unit, c.from_currency):
                raise InvariantError("Conversion input basis does not match")
            if not c.period.covers(self.left.period):
                raise InvariantError("Conversion does not cover the entire quantity period")
        else:
            if self.conversion is not None or not isinstance(self.right, (Quantity, Calculation)):
                raise InvariantError("Two sourced operands required")
            if self.operation in ("add", "subtract", "divide"):
                _same(self.left, self.right)
            elif self.operation == "scale":
                if (self.right.unit, self.right.currency) != ("ratio", None):
                    raise InvariantError("Scale requires a sourced dimensionless ratio")
                if self.left.period != self.right.period:
                    raise InvariantError("Period mismatch")
            else:
                raise InvariantError("Unknown operation")
        self.amount  # Refuse invalid arithmetic at construction, not at reporting.

    @property
    def amount(self) -> Decimal:
        left = Fraction(self.left.amount)
        if self.operation == "convert":
            return _exact(left * Fraction(self.conversion.factor))
        right = Fraction(self.right.amount)
        if self.operation == "add":
            return _exact(left + right)
        if self.operation == "subtract":
            return _exact(left - right)
        if self.operation == "scale":
            return _exact(left * right)
        if right == 0:
            raise InvariantError("Zero denominator")
        return _exact(left / right)

    @property
    def unit(self) -> str:
        if self.operation == "convert":
            return self.conversion.to_unit
        return "ratio" if self.operation == "divide" else self.left.unit

    @property
    def currency(self) -> str | None:
        if self.operation == "convert":
            return self.conversion.to_currency
        return None if self.operation == "divide" else self.left.currency

    @property
    def period(self) -> Period:
        return self.left.period


Value = Quantity | Calculation


class BindingStatus(str, Enum):
    BINDING = "BINDING"
    NON_BINDING = "NON_BINDING"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class Norm:
    provision_text: str
    instrument: str
    commencement: date | None
    source: Citation
    binding_status: BindingStatus
    commencement_source: Citation | None = None
    end: date | None = None
    end_source: Citation | None = None

    def __post_init__(self):
        _text(self.provision_text)
        _text(self.instrument)
        if not isinstance(self.source, Citation) or not isinstance(self.binding_status, BindingStatus):
            raise InvariantError("Norm needs a citation and explicit binding status")
        for boundary, citation in ((self.commencement, self.commencement_source), (self.end, self.end_source)):
            if boundary is not None:
                _date(boundary)
                if not isinstance(citation, Citation):
                    raise InvariantError("Effective boundaries require their own citation")
            elif citation is not None:
                raise InvariantError("Boundary citation without boundary date")
        if self.end and (self.commencement is None or self.end <= self.commencement):
            raise InvariantError("Invalid norm effective window")


@dataclass(frozen=True)
class Term:
    name: str
    value: Value | None
    missing_reason: str | None = None
    expected_publisher: str | None = None

    def __post_init__(self):
        _text(self.name)
        if self.value is None:
            _text(self.missing_reason)
            _text(self.expected_publisher)
        elif not isinstance(self.value, (Quantity, Calculation)) or self.missing_reason is not None or self.expected_publisher is not None:
            raise InvariantError("Term must be either sourced or explicitly missing")


class State(str, Enum):
    HOLDS = "HOLDS"
    BREAKS = "BREAKS"
    UNASSESSABLE = "UNASSESSABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Applicability(str, Enum):
    APPLIES = "APPLIES"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Scope:
    """Rule-specific scope determination. Core never infers jurisdiction or regime."""
    status: Applicability
    reason: str
    evidence: tuple[Citation, ...] = ()

    def __post_init__(self):
        if not isinstance(self.status, Applicability):
            raise InvariantError("Explicit applicability required")
        _text(self.reason)
        if not isinstance(self.evidence, tuple) or not all(isinstance(x, Citation) for x in self.evidence):
            raise InvariantError("Scope evidence must be an immutable citation tuple")
        if self.status != Applicability.UNKNOWN and not self.evidence:
            raise InvariantError("Determined scope needs cited evidence")


@dataclass(frozen=True)
class Finding:
    state: State
    equation: str
    left: Term
    right: Term
    norm: Norm
    period: Period
    scope: Scope
    margin: Calculation | None
    reason: str

    def to_json(self) -> str:
        return json.dumps(_record(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _record(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        result = {f.name: _record(getattr(value, f.name)) for f in fields(value)}
        if isinstance(value, Calculation):
            result.update(amount=_record(value.amount), unit=value.unit, currency=value.currency, period=_record(value.period))
        return result
    if isinstance(value, tuple):
        return [_record(x) for x in value]
    return value


def evaluate(left: Term, relation: str, right: Term, *, norm: Norm,
             period: Period, scope: Scope) -> Finding:
    """Inclusive comparisons. Positive margin means headroom, zero meets the rule.

    A period crossing a legal boundary must be split explicitly. Missing terms
    keep their placeholders and publisher; undefined margins are null, not zero.
    """
    if relation not in (">=", "<="):
        raise InvariantError("Only inclusive >= or <= comparisons are supported")
    if not isinstance(norm, Norm) or not isinstance(period, Period) or not isinstance(scope, Scope):
        raise InvariantError("Norm, period and scope are required")
    if not isinstance(left, Term) or not isinstance(right, Term) or left.name == right.name:
        raise InvariantError("Two distinct named terms required")
    equation = f"{left.name} {relation} {right.name}"
    def result(state, reason, margin=None):
        return Finding(state, equation, left, right, norm, period, scope, margin, reason)
    if norm.binding_status != BindingStatus.BINDING or norm.commencement is None:
        return result(State.UNASSESSABLE, "Binding force or commencement is not established")
    if period.end <= norm.commencement:
        return result(State.NOT_APPLICABLE, "Evaluation period is wholly before commencement")
    if norm.end and period.start >= norm.end:
        return result(State.NOT_APPLICABLE, "Evaluation period is after this norm version's end")
    if period.start < norm.commencement or (norm.end and period.end > norm.end):
        return result(State.UNASSESSABLE, "Period crosses a legal boundary; split it before evaluating")
    if scope.status == Applicability.UNKNOWN:
        return result(State.UNASSESSABLE, scope.reason)
    if scope.status == Applicability.EXCLUDED:
        return result(State.NOT_APPLICABLE, scope.reason)
    missing = [t for t in (left, right) if t.value is None]
    if missing:
        return result(State.UNASSESSABLE, "; ".join(f"{t.name}: {t.missing_reason}; expected publisher: {t.expected_publisher}" for t in missing))
    try:
        _same(left.value, right.value)
        if left.value.period != period:
            raise InvariantError("Terms do not cover the evaluation period")
        operands = (left.value, right.value) if relation == ">=" else (right.value, left.value)
        margin = Calculation("subtract", *operands)
    except InvariantError as exc:
        return result(State.UNASSESSABLE, str(exc))
    return result(State.HOLDS if margin.amount >= 0 else State.BREAKS,
                  "Sourced comparison meets the rule" if margin.amount >= 0 else "Sourced comparison indicates a break", margin)


@dataclass(frozen=True)
class Announcement:
    identifier: str
    announced_on: date
    effective: Period
    value: Quantity
    effective_source: Citation

    def __post_init__(self):
        _text(self.identifier)
        _date(self.announced_on)
        if not isinstance(self.effective, Period) or not isinstance(self.value, Quantity) or not isinstance(self.effective_source, Citation):
            raise InvariantError("Announcement needs a value and cited effective window")
        if not self.value.period.covers(self.effective):
            raise InvariantError("Effective window lies outside quantity period")


@dataclass(frozen=True)
class AnnouncementSeries:
    entries: tuple[Announcement, ...]

    def __post_init__(self):
        if not isinstance(self.entries, tuple) or not self.entries or not all(isinstance(x, Announcement) for x in self.entries):
            raise InvariantError("An immutable non-empty announcement tuple is required")
        if len({x.identifier for x in self.entries}) != len(self.entries):
            raise InvariantError("Announcement identifiers must be unique")
        first = self.entries[0].value
        if any((x.value.unit, x.value.currency) != (first.unit, first.currency) for x in self.entries):
            raise InvariantError("Series basis changes require explicit conversion before construction")
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda x: (x.effective.start, x.identifier))))

    def at(self, effective_on: date, *, known_on: date) -> Announcement:
        _date(effective_on)
        _date(known_on)
        candidates = [x for x in self.entries if x.announced_on <= known_on and x.effective.start <= effective_on < x.effective.end]
        if len(candidates) != 1:
            raise InvariantError("Missing or ambiguous effective value; no implicit priority or averaging")
        return candidates[0]

    def boundaries(self, period: Period) -> tuple[date, ...]:
        """All potential split dates, not a claim of complete or unambiguous coverage."""
        return tuple(sorted({period.start, period.end} | {d for x in self.entries for d in (x.effective.start, x.effective.end) if period.start < d < period.end}))
