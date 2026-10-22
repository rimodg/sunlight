"""Pilot operations ledger: attributed snapshots, exact comparisons and review history.

No network fetches, invented observations, currency conversion or theft verdicts.
SQLite supports one deployment/volume; this is not a multi-tenant ingestion service.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

router = APIRouter(prefix='/operations', tags=['Pilot operations'])
Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r'^[A-Za-z0-9_.:/-]+$')]
Amount = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=6)]


def utcnow():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class SourceInput(StrictModel):
    source_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    publisher_url: HttpUrl
    profile: str = Field(min_length=1, max_length=100)
    expected_refresh_seconds: int = Field(default=3600, ge=60, le=31536000)


class Measure(StrictModel):
    value: Amount
    metric: Literal['delivery', 'payment', 'goods_export', 'goods_import']
    unit: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9_/-]+$')
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    period_start: date
    period_end: date
    document_url: HttpUrl

    @model_validator(mode='after')
    def consistent_measure(self):
        if self.period_start > self.period_end:
            raise ValueError('period_start must not follow period_end')
        if (self.unit == 'currency') != (self.currency is not None):
            raise ValueError('currency unit requires an ISO currency; physical units must not carry a currency')
        if self.metric == 'payment' and self.unit != 'currency':
            raise ValueError('payment measures require a currency unit')
        return self


class Expected(Measure):
    due_at: AwareDatetime

    @model_validator(mode='after')
    def valid_due(self):
        if self.due_at.date() < self.period_end:
            raise ValueError('due_at must not precede the end of the covered period')
        return self


class Observed(Measure):
    observed_at: AwareDatetime

    @model_validator(mode='after')
    def valid_observation(self):
        if self.observed_at.date() < self.period_end:
            raise ValueError('a cumulative period observation must not precede its period end')
        return self


class FlowRevision(StrictModel):
    event_id: Identifier
    contract_id: Identifier
    item_id: Identifier
    revision: int = Field(ge=1, le=2147483647)
    title: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=160)
    origin_country: str = Field(pattern=r'^[A-Z]{2}$')
    destination_country: str = Field(pattern=r'^[A-Z]{2}$')
    published_at: AwareDatetime
    expected: Expected
    observed: Observed | None = None
    procurement_record: dict[str, Any] | None = None

    @model_validator(mode='after')
    def clocks_and_identity(self):
        if self.published_at > utcnow() + timedelta(minutes=5):
            raise ValueError('published_at cannot be in the future (five-minute clock tolerance)')
        if self.observed and self.observed.observed_at > self.published_at:
            raise ValueError('an observation cannot postdate its source publication')
        if self.procurement_record is not None and self.procurement_record.get('ocid') != self.contract_id:
            raise ValueError('procurement_record.ocid must match contract_id')
        return self


class IngestRequest(StrictModel):
    source_id: Identifier
    events: list[FlowRevision] = Field(min_length=1, max_length=50)


class ReviewInput(StrictModel):
    expected_revision: int = Field(ge=1)
    expected_audit_head: str = Field(pattern=r'^[a-f0-9]{64}$')
    status: Literal['open', 'in_review', 'awaiting_evidence', 'resolved']
    followed: bool
    owner: str = Field(default='', max_length=160)
    note: str = Field(min_length=1, max_length=4000)


def compare(event: FlowRevision, now=None):
    now = now or utcnow()
    e, o = event.expected, event.observed
    common = {'expected': str(e.value), 'observed': str(o.value) if o else None,
              'gap': None, 'gap_percent': None, 'overage': None,
              'unit': e.unit, 'currency': e.currency, 'metric': e.metric,
              'definition': 'Expected minus source-reported cumulative observation for the same metric, unit, currency and covered period. Not a theft estimate.'}
    if o is None:
        if now < e.due_at:
            return {**common, 'state': 'not_due', 'reason': 'The target is not due; no observation is required for a deadline comparison yet.'}
        return {**common, 'state': 'missing_observation', 'reason': 'No observation submitted. Missing evidence is not zero delivery.'}
    mismatch = [k for k in ('metric', 'unit', 'currency', 'period_start', 'period_end') if getattr(e, k) != getattr(o, k)]
    if mismatch:
        return {**common, 'state': 'not_comparable', 'reason': 'Different ' + ', '.join(mismatch) + '; no subtraction performed.'}
    if now < e.due_at:
        return {**common, 'state': 'not_due', 'reason': 'The expected outcome is not due yet; no shortfall is inferred.'}
    if o.observed_at < e.due_at:
        return {**common, 'state': 'awaiting_due_observation', 'reason': 'Latest observation predates the due time; obtain an observation covering the deadline.'}
    delta = e.value - o.value
    return {**common, 'gap': str(max(delta, Decimal(0))), 'overage': str(max(-delta, Decimal(0))),
            'gap_percent': str(max(delta, Decimal(0)) / e.value * 100) if e.value else None,
            'state': 'shortfall' if delta > 0 else 'overage' if delta < 0 else 'matched',
            'reason': 'Comparable attributed measurements. Source references have not been independently authenticated or inspected by SUNLIGHT.'}


def db_path():
    return Path(os.environ.get('SUNLIGHT_OPERATIONS_DB', str(Path(os.environ.get('SUNLIGHT_CALIBRATION_DIR', Path(__file__).resolve().parents[1]/'calibration'))/'operations.sqlite3')))


@contextmanager
def connection():
    path = db_path();path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS op_sources(id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS op_revisions(source_id TEXT NOT NULL REFERENCES op_sources(id), event_id TEXT NOT NULL,
          case_id TEXT NOT NULL, revision INTEGER NOT NULL, published_at TEXT NOT NULL, received_at TEXT NOT NULL,
          payload TEXT NOT NULL, payload_hash TEXT NOT NULL, analysis TEXT NOT NULL,
          PRIMARY KEY(source_id,event_id), UNIQUE(case_id,revision));
        CREATE INDEX IF NOT EXISTS op_revision_case ON op_revisions(case_id,revision DESC);
        CREATE TABLE IF NOT EXISTS op_reviews(case_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS op_audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
          payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
        ''')
        yield db
        db.commit()
    except BaseException:
        db.rollback();raise
    finally:
        db.close()


def append_audit(db, case_id, action, detail):
    previous = db.execute('SELECT hash FROM op_audit WHERE case_id=? ORDER BY seq DESC LIMIT 1', (case_id,)).fetchone()
    prev = previous['hash'] if previous else ''
    payload = {'action': action, 'at': utcnow().isoformat(), 'detail': detail}
    db.execute('INSERT INTO op_audit(case_id,payload,previous_hash,hash) VALUES(?,?,?,?)', (case_id, canonical(payload), prev, digest({'previous_hash': prev, 'payload': payload})))


def case_id_for(source_id, event):
    return digest([source_id, event.contract_id, event.item_id])[:32]


def default_review():
    return {'status': 'open', 'followed': False, 'owner': ''}


def format_case(db, row, now=None):
    payload = json.loads(row['payload']); event = FlowRevision.model_validate(payload)
    review = db.execute('SELECT payload FROM op_reviews WHERE case_id=?', (row['case_id'],)).fetchone()
    prior = db.execute('SELECT revision,payload FROM op_revisions WHERE case_id=? AND revision<? ORDER BY revision DESC LIMIT 1',(row['case_id'],row['revision'])).fetchone()
    baseline_change = None
    if prior:
        old = json.loads(prior['payload'])
        if any(old[k] != payload[k] for k in ('expected','category')):
            baseline_change = {'previous_revision':prior['revision'],'previous_expected':old['expected'],'previous_category':old['category']}
    return {'case_id': row['case_id'], 'source_id': row['source_id'], 'revision': row['revision'],
            'received_at': row['received_at'], 'payload_hash': row['payload_hash'], 'record': payload,
            'comparison': compare(event, now), 'baseline_change': baseline_change, 'analysis': json.loads(row['analysis']),
            'review': json.loads(review['payload']) if review else default_review()}


def current_row(db, case_id):
    row = db.execute('SELECT * FROM op_revisions WHERE case_id=? ORDER BY revision DESC LIMIT 1', (case_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Case not found')
    return row


async def run_engines(event, profile):
    # Reuse existing calibrated APIs; do not reproduce their rules in the operations desk.
    from api import AnalyzeRequest, analyze_contract, DeliveryAnalyzeRequest, analyze_delivery
    result = {'procurement': None, 'delivery': None, 'scope': 'Only supplied records and comparable delivery quantities are analyzed. Missing dimensions remain unverified.'}
    if event.procurement_record is not None:
        response = await analyze_contract(AnalyzeRequest(contract=event.procurement_record, profile=profile))
        result['procurement'] = response.model_dump(mode='json')
    comparison = compare(event)
    if event.expected.metric == 'delivery' and event.expected.unit != 'currency' and comparison['gap'] is not None:
        response = await analyze_delivery(DeliveryAnalyzeRequest(contract_id=event.contract_id, profile=profile,
            country_code=event.destination_country, project_name=event.title,
            outcomes=[{'outcome_id': event.item_id, 'description': event.title, 'unit': event.expected.unit,
                       'quantity_planned': float(event.expected.value), 'quantity_delivered': float(event.observed.value),
                       'inspection_date': event.observed.observed_at.isoformat()}]))
        result['delivery'] = response.model_dump(mode='json')
    return result


@router.get('/status')
def operations_status():
    return {'mode': 'source_push_pilot', 'schema_version': 'sunlight.operations.v1', 'server_time': utcnow().isoformat(),
            'automatic_external_polling': False, 'un_connection': 'not_connected',
            'storage': 'SQLite on deployment filesystem', 'volume_durability': 'not_verified',
            'storage_note': 'Records survive process restarts on the same filesystem. Mount SUNLIGHT_OPERATIONS_DB on a persistent disk before retaining institutional records; ephemeral hosting can erase this ledger on redeploy. Single replica only.',
            'access_scope': 'Shared deployment access gate; no tenant or per-source authorization. Institutional gateway, access roles and authenticated publisher mappings remain integration requirements.'}


@router.get('/sources')
def sources():
    now = utcnow();output = []
    with connection() as db:
        for row in db.execute('SELECT * FROM op_sources ORDER BY created_at DESC').fetchall():
            source = json.loads(row['payload'])
            timing = db.execute('SELECT MAX(received_at) received, MAX(published_at) published, COUNT(*) revisions FROM op_revisions WHERE source_id=?', (row['id'],)).fetchone()
            published = datetime.fromisoformat(timing['published']) if timing['published'] else None
            output.append({**source, 'created_at': row['created_at'], 'last_received_at': timing['received'],
                           'latest_published_at': timing['published'], 'revisions': timing['revisions'],
                           'freshness': 'awaiting_first_submission' if published is None else 'late' if (now-published).total_seconds()>source['expected_refresh_seconds'] else 'within_declared_interval'})
    return {'sources': output, 'server_time': now.isoformat()}


@router.post('/sources', status_code=201)
def register_source(source: SourceInput):
    from api import get_profile
    try:
        get_profile(source.profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = source.model_dump(mode='json')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT payload FROM op_sources WHERE id=?', (source.source_id,)).fetchone()
        if existing:
            if json.loads(existing['payload']) != data:
                raise HTTPException(409, 'Source ID already has a different immutable configuration; register a new source ID')
            return {'source': data, 'duplicate': True}
        db.execute('INSERT INTO op_sources VALUES(?,?,?)', (source.source_id, canonical(data), utcnow().isoformat()))
    return {'source': data, 'duplicate': False}


@router.post('/ingest')
async def ingest(request: IngestRequest):
    try:
        encoded = canonical(request.model_dump(mode='json')).encode()
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, 'Submissions must contain finite JSON values') from exc
    if len(encoded) > 2*1024*1024:
        raise HTTPException(413, 'Ingestion batch exceeds 2 MB')
    results = []
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        source = db.execute('SELECT payload FROM op_sources WHERE id=?', (request.source_id,)).fetchone()
        if not source:
            raise HTTPException(404, 'Register the source before submitting events')
        profile = json.loads(source['payload'])['profile']
        source_hash = digest(json.loads(source['payload']))
        for event in request.events:
            case_id = case_id_for(request.source_id, event)
            payload = event.model_dump(mode='json');fingerprint = digest(payload)
            existing = db.execute('SELECT * FROM op_revisions WHERE source_id=? AND event_id=?', (request.source_id, event.event_id)).fetchone()
            if existing:
                if existing['payload_hash'] != fingerprint:
                    raise HTTPException(409, 'Event ID replayed with different content')
                results.append({'case_id': case_id, 'revision': event.revision, 'state': 'duplicate'});continue
            same_version = db.execute('SELECT event_id FROM op_revisions WHERE case_id=? AND revision=?', (case_id, event.revision)).fetchone()
            if same_version:
                raise HTTPException(409, 'Case revision already exists; new event IDs do not replace an existing revision')
            previous = db.execute('SELECT * FROM op_revisions WHERE case_id=? ORDER BY revision DESC LIMIT 1', (case_id,)).fetchone()
            if previous and event.revision > previous['revision'] and event.published_at < datetime.fromisoformat(previous['published_at']):
                raise HTTPException(409, 'A higher revision cannot have an earlier publication time')
            analysis = await run_engines(event, profile)
            db.execute('INSERT INTO op_revisions VALUES(?,?,?,?,?,?,?,?,?)', (request.source_id, event.event_id, case_id, event.revision,
                       event.published_at.astimezone(timezone.utc).isoformat(), utcnow().isoformat(), canonical(payload), fingerprint, canonical(analysis)))
            supersedes = previous is None or event.revision > previous['revision']
            baseline_changed = bool(previous and supersedes and any(json.loads(previous['payload'])[k] != payload[k] for k in ('expected','category')))
            append_audit(db, case_id, 'revision_received', {'revision': event.revision, 'payload_hash': fingerprint, 'analysis_hash': digest(analysis), 'source_hash': source_hash, 'became_current': supersedes, 'baseline_changed': baseline_changed})
            if supersedes:
                old_review = db.execute('SELECT payload FROM op_reviews WHERE case_id=?', (case_id,)).fetchone()
                if old_review:
                    review = json.loads(old_review['payload']);review['status'] = 'open'
                    db.execute('UPDATE op_reviews SET payload=? WHERE case_id=?', (canonical(review), case_id))
                    append_audit(db, case_id, 'review_reopened', {'reason': 'New current source revision requires review', 'revision': event.revision})
            results.append({'case_id': case_id, 'revision': event.revision, 'state': 'current' if supersedes else 'archived', 'baseline_changed': baseline_changed})
    return {'results': results, 'atomic_batch': True, 'received_at': utcnow().isoformat()}


@router.get('/cases')
def list_cases(q: str = Query('', max_length=200), source_id: str = '', country: str = '', comparison: str = '',
               workflow: str = '', followed: bool = False, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    now = utcnow()
    with connection() as db:
        rows = db.execute('SELECT r.* FROM op_revisions r JOIN (SELECT case_id,MAX(revision) revision FROM op_revisions GROUP BY case_id) c ON r.case_id=c.case_id AND r.revision=c.revision ORDER BY r.received_at DESC').fetchall()
        cases = [format_case(db, r, now) for r in rows]
    cases = [c for c in cases if (not source_id or c['source_id']==source_id) and
             (not country or country.upper() in (c['record']['origin_country'], c['record']['destination_country'])) and
             (not comparison or c['comparison']['state']==comparison) and (not workflow or c['review']['status']==workflow) and
             (not followed or c['review']['followed']) and (not q or q.casefold() in canonical(c['record']).casefold() or q.casefold() in c['source_id'].casefold() or q.casefold() in canonical(c['review']).casefold())]
    counts = {};groups = {}
    for case in cases:
        c = case['comparison'];counts[c['state']] = counts.get(c['state'], 0)+1
        if c['gap'] is None:
            continue
        e = case['record']['expected']
        key = (case['source_id'], case['record']['category'], e['metric'], e['unit'], e['currency'], e['period_start'], e['period_end'])
        if key not in groups:
            groups[key] = {'source_id': key[0], 'category': key[1], 'metric': key[2], 'unit': key[3], 'currency': key[4], 'period_start': key[5], 'period_end': key[6], 'cases': 0, 'shortfall': Decimal(0), 'overage': Decimal(0)}
        groups[key]['cases'] += 1
        with localcontext() as ctx:
            ctx.prec = 64  # More than 24 input digits plus SQLite's maximum row-count digits.
            groups[key]['shortfall'] += Decimal(c['gap']);groups[key]['overage'] += Decimal(c['overage'])
    totals = [{**g, 'shortfall': str(g['shortfall']), 'overage': str(g['overage'])} for g in groups.values()]
    return {'cases': cases[offset:offset+limit], 'total': len(cases), 'counts': counts, 'comparable_groups': totals,
            'server_time': now.isoformat(), 'aggregation': 'Latest revision only, grouped by source, category, metric, unit, currency and period. Sources are never combined; missing/noncomparable/not-due observations are excluded. Shortfalls and overages never offset each other.'}


@router.get('/cases/{case_id}')
def get_case(case_id: str):
    with connection() as db:
        current = format_case(db, current_row(db, case_id))
        current['source'] = json.loads(db.execute('SELECT payload FROM op_sources WHERE id=?',(current['source_id'],)).fetchone()['payload'])
        current['history'] = [{'revision': r['revision'], 'published_at': r['published_at'], 'received_at': r['received_at'], 'payload_hash': r['payload_hash']} for r in db.execute('SELECT * FROM op_revisions WHERE case_id=? ORDER BY revision DESC', (case_id,))]
        current['audit'] = [dict(r) for r in db.execute('SELECT * FROM op_audit WHERE case_id=? ORDER BY seq', (case_id,))]
    return current


@router.post('/cases/{case_id}/review')
def review_case(case_id: str, review: ReviewInput):
    with connection() as db:
        db.execute('BEGIN IMMEDIATE');current = current_row(db, case_id)
        if current['revision'] != review.expected_revision:
            raise HTTPException(409, 'A newer source revision exists; refresh before saving review')
        head = db.execute('SELECT hash FROM op_audit WHERE case_id=? ORDER BY seq DESC LIMIT 1', (case_id,)).fetchone()
        if not head or head['hash'] != review.expected_audit_head:
            raise HTTPException(409, 'The case history changed; refresh before saving review')
        payload = review.model_dump(mode='json');payload.pop('expected_revision');payload.pop('expected_audit_head')
        db.execute('INSERT INTO op_reviews VALUES(?,?) ON CONFLICT(case_id) DO UPDATE SET payload=excluded.payload', (case_id, canonical(payload)))
        append_audit(db, case_id, 'review_updated', {'revision': current['revision'], **payload})
    return {'case_id': case_id, 'review': payload}


@router.get('/cases/{case_id}/export')
def export_case(case_id: str):
    exported_at = utcnow()
    with connection() as db:
        current = format_case(db, current_row(db, case_id), exported_at)
        source = json.loads(db.execute('SELECT payload FROM op_sources WHERE id=?',(current['source_id'],)).fetchone()['payload'])
        revisions = [{**dict(r), 'payload': json.loads(r['payload']), 'analysis': json.loads(r['analysis'])} for r in db.execute('SELECT * FROM op_revisions WHERE case_id=? ORDER BY revision', (case_id,))]
        audit = [{**dict(r), 'payload': json.loads(r['payload'])} for r in db.execute('SELECT * FROM op_audit WHERE case_id=? ORDER BY seq', (case_id,))]
    previous = '';valid = True
    for entry in audit:
        valid = valid and entry['previous_hash']==previous and digest({'previous_hash': previous, 'payload': entry['payload']})==entry['hash']
        previous = entry['hash']
    valid = valid and len([a for a in audit if a['payload']['action']=='revision_received']) == len(revisions)
    reconstructed_review = default_review()
    for a in audit:
        if a['payload']['action']=='review_updated':
            reconstructed_review = {k:v for k,v in a['payload']['detail'].items() if k!='revision'}
        elif a['payload']['action']=='review_reopened':
            reconstructed_review['status']='open'
    valid = valid and reconstructed_review == current['review']
    for row in revisions:
        matching = next((a for a in audit if a['payload']['action']=='revision_received' and a['payload']['detail']['revision']==row['revision']), None)
        valid = valid and digest(row['payload'])==row['payload_hash'] and matching is not None
        if matching:
            valid = valid and matching['payload']['detail']['payload_hash']==row['payload_hash'] and matching['payload']['detail']['analysis_hash']==digest(row['analysis']) and matching['payload']['detail'].get('source_hash')==digest(source)
    return {'schema_version': 'sunlight.operations.case-packet.v1', 'exported_at': exported_at.isoformat(), 'source': source, 'current': current, 'revisions': revisions, 'audit': audit,
            'integrity': {'chain_and_content_valid': bool(valid), 'audit_head': previous, 'limit': 'Local content integrity only; not a source signature, external timestamp or protection against a database owner rewriting the entire chain.'}}
