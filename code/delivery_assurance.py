"""Public obligations followed through separately attributed arrival and delivery evidence.

This local pilot reconciles submitted claims. It does not authenticate issuers,
connect to banks, convert currencies, or execute institutional interventions.
Amounts remain Decimal strings; missing evidence never becomes zero.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
import json
from pathlib import Path
from typing import Annotated, Literal
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime, BeforeValidator, Field, HttpUrl, model_validator

from operations import Amount, Identifier, StrictModel, canonical, connection, digest, utcnow

router = APIRouter(prefix='/assurance', tags=['Delivery assurance'])
COUNTRY_CODES = {c['code'] for c in json.loads(Path(__file__).with_name('research_countries.json').read_text())}
Kind = Literal['funds_sent', 'funds_received', 'settlement_deduction', 'dispatched', 'received', 'accepted', 'outcome']
MONEY = {'funds_sent', 'funds_received', 'settlement_deduction'}
STAGES = ['dispatched', 'received', 'accepted', 'outcome']
LIMITS = ('Calculations reconcile submitted evidence, not authenticated bank or field feeds. '
          'Distinct declared issuers do not establish independence. Goods, money and service outcomes '
          'are separate measurements. No automatic payment stop, recovery or redirection is connected.')


def exact_input(value):
    if isinstance(value, (float, bool)):
        raise ValueError('Use a decimal string or exact integer, not a floating-point JSON amount')
    return value


ExactAmount = Annotated[Amount, BeforeValidator(exact_input)]


class Target(StrictModel):
    value: ExactAmount = Field(gt=0)
    unit: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9_/-]+$')


class ObligationInput(StrictModel):
    reference: Identifier
    title: str = Field(min_length=3, max_length=240)
    sector: str = Field(min_length=1, max_length=100)
    country: str = Field(pattern=r'^[A-Z]{2}$')
    origin_country: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    community: str = Field(min_length=1, max_length=240)
    promise: str = Field(min_length=8, max_length=4000)
    owner: str = Field(min_length=1, max_length=160)
    recipient: str = Field(min_length=1, max_length=200)
    baseline_url: HttpUrl
    due_at: AwareDatetime
    delivery_target: Target
    outcome_target: Target | None = None
    budget: ExactAmount | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    synthetic: bool = False

    @model_validator(mode='after')
    def valid_scope(self):
        if self.country not in COUNTRY_CODES or (self.origin_country and self.origin_country not in COUNTRY_CODES):
            raise ValueError('Select recognized country or territory codes')
        if (self.budget is None) != (self.currency is None):
            raise ValueError('Budget and currency must be supplied together')
        return self


class EvidenceInput(StrictModel):
    expected_version: int = Field(ge=1)
    kind: Kind
    value: ExactAmount
    unit: str = Field(min_length=1, max_length=60, pattern=r'^[A-Za-z0-9_/-]+$')
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    issuer_id: Identifier
    issuer_name: str = Field(min_length=1, max_length=200)
    ledger_reference: Identifier
    document_url: HttpUrl
    observed_at: AwareDatetime
    covers_through: AwareDatetime | None = None
    transfer_id: Identifier | None = None
    sender_id: Identifier | None = None
    recipient_id: Identifier | None = None
    settlement_due_at: AwareDatetime | None = None
    note: str = Field(min_length=3, max_length=4000)
    supersedes: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def valid_evidence(self):
        if self.observed_at > utcnow() + timedelta(minutes=5):
            raise ValueError('Evidence cannot describe a future observation')
        if self.kind in MONEY:
            if self.unit != 'currency' or not self.currency:
                raise ValueError('Financial evidence requires unit currency and an ISO currency')
            if not all((self.transfer_id, self.sender_id, self.recipient_id)):
                raise ValueError('Financial evidence needs a stable transfer ID and both party IDs')
            if self.sender_id == self.recipient_id:
                raise ValueError('Sender and recipient must be different parties')
            if self.covers_through is not None:
                raise ValueError('Financial evidence is a ledger entry, not a cumulative snapshot')
            if self.kind == 'funds_sent' and (not self.settlement_due_at or self.settlement_due_at < self.observed_at):
                raise ValueError('Funds sent requires a settlement deadline at or after the debit')
            if self.kind != 'funds_sent' and self.settlement_due_at:
                raise ValueError('Settlement deadline belongs to the sender record')
        else:
            if self.currency or self.unit == 'currency' or self.transfer_id or self.sender_id or self.recipient_id or self.settlement_due_at:
                raise ValueError('Delivery and outcome snapshots use physical/service units, not financial fields')
            if not self.covers_through or self.covers_through > self.observed_at:
                raise ValueError('A cumulative snapshot needs a coverage time at or before its observation')
        return self


class ActionInput(StrictModel):
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=240)
    kind: Literal['evidence_request', 'financial_review', 'inspection', 'delivery_followup']
    owner: str = Field(min_length=1, max_length=160)
    due_at: AwareDatetime
    note: str = Field(min_length=3, max_length=4000)
    signal_key: str = Field(default='', max_length=200)


class ActionUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    status: Literal['open', 'in_progress', 'completed']
    note: str = Field(min_length=3, max_length=4000)
    completion_evidence_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def completion_basis(self):
        if self.status == 'completed' and not self.completion_evidence_id:
            raise ValueError('Completing a follow-up requires a retained evidence reference')
        if self.status != 'completed' and self.completion_evidence_id:
            raise ValueError('Completion evidence belongs to a completed follow-up')
        return self


class AnalysisInput(StrictModel):
    expected_version: int = Field(ge=1)
    profile: str = Field(min_length=1, max_length=100)


@contextmanager
def assurance_connection():
    with connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS assurance_obligations(
          id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
          version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assurance_evidence(
          id TEXT PRIMARY KEY, obligation_id TEXT NOT NULL REFERENCES assurance_obligations(id),
          kind TEXT NOT NULL, issuer_id TEXT NOT NULL, ledger_reference TEXT NOT NULL,
          payload TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at TEXT NOT NULL,
          superseded_by TEXT);
        CREATE INDEX IF NOT EXISTS assurance_evidence_obligation ON assurance_evidence(obligation_id);
        CREATE INDEX IF NOT EXISTS assurance_evidence_reference ON assurance_evidence(issuer_id,ledger_reference,kind);
        CREATE TABLE IF NOT EXISTS assurance_actions(
          id TEXT PRIMARY KEY, obligation_id TEXT NOT NULL REFERENCES assurance_obligations(id), payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assurance_history(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, obligation_id TEXT NOT NULL REFERENCES assurance_obligations(id),
          payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assurance_analyses(
          id TEXT PRIMARY KEY, obligation_id TEXT NOT NULL REFERENCES assurance_obligations(id), payload TEXT NOT NULL);
        ''')
        yield db


def audit(db, oid, action, detail):
    previous = db.execute('SELECT hash FROM assurance_history WHERE obligation_id=? ORDER BY seq DESC LIMIT 1', (oid,)).fetchone()
    prev = previous['hash'] if previous else ''
    payload = {'at': utcnow().isoformat(), 'action': action, 'detail': detail}
    db.execute('INSERT INTO assurance_history(obligation_id,payload,previous_hash,hash) VALUES(?,?,?,?)',
               (oid, canonical(payload), prev, digest({'previous_hash': prev, 'payload': payload})))


def locked_obligation(db, oid, version=None):
    db.execute('BEGIN IMMEDIATE')
    row = db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone()
    if not row:
        raise HTTPException(404, 'Obligation not found')
    if version is not None and row['version'] != version:
        raise HTTPException(409, 'New evidence or review history arrived. Refresh before saving; your draft can be retained.')
    return row


def bump(db, oid):
    db.execute('UPDATE assurance_obligations SET version=version+1, updated_at=? WHERE id=?', (utcnow().isoformat(), oid))


def decimal_sum(items):
    return sum((Decimal(x['value']) for x in items), Decimal(0))


def transfer_key(e):
    return (e['transfer_id'], e['sender_id'], e['recipient_id'])


def reconcile_transfers(evidence, now):
    groups = {}
    for e in evidence:
        if e['kind'] in MONEY:
            groups.setdefault(transfer_key(e), []).append(e)
    output = []
    for key, rows in groups.items():
        sent = [e for e in rows if e['kind'] == 'funds_sent']
        credits = [e for e in rows if e['kind'] == 'funds_received']
        deductions = [e for e in rows if e['kind'] == 'settlement_deduction']
        r = {'transfer_id': key[0], 'sender_id': key[1], 'recipient_id': key[2],
             'evidence_ids': [e['id'] for e in rows], 'sent': None, 'received': None,
             'deductions': None, 'raw_difference': None, 'residual': None, 'currency': None,
             'distinct_declared_issuers': False, 'settlement_due_at': None,
             'assurance': 'Submitted references; issuer identity and ledger matching are not independently authenticated.'}
        currencies = {e['currency'] for e in rows}
        if len(currencies) == 1:
            r.update(currency=next(iter(currencies)), sent=sent[0]['value'] if len(sent)==1 else None,
                     received=str(decimal_sum(credits)) if credits else None, deductions=str(decimal_sum(deductions)))
        if len(sent) != 1:
            r.update(state='sender_unobserved', reason='Obtain one executed sender debit for this transfer identity.')
        elif len(currencies) != 1:
            r.update(state='not_comparable', reason='Currencies differ. Obtain a documented conversion and settlement basis; no conversion or subtraction performed.')
        else:
            s = sent[0]
            r.update(sent=s['value'], settlement_due_at=s['settlement_due_at'], deductions=str(decimal_sum(deductions)))
            if not credits:
                r.update(state='awaiting_settlement' if now < datetime.fromisoformat(s['settlement_due_at']) else 'arrival_unobserved',
                         reason='No receiving credit is recorded. Arrival remains unknown, even if deductions are supplied.')
            else:
                r['received'] = str(decimal_sum(credits))
                r['distinct_declared_issuers'] = all(e['issuer_id'] != s['issuer_id'] for e in credits)
                r['raw_difference'] = str(Decimal(s['value']) - decimal_sum(credits))
                if any(datetime.fromisoformat(e['observed_at']) < datetime.fromisoformat(s['observed_at']) for e in credits + deductions):
                    r.update(state='not_comparable', reason='A credit or deduction predates the recorded debit; inspect transfer identity and value dates.')
                elif not r['distinct_declared_issuers']:
                    r.update(state='issuer_separation_missing', reason='Sender and receiving records share a declared issuer. Obtain a separately attributable receiving record.')
                elif now < datetime.fromisoformat(s['settlement_due_at']):
                    r.update(state='awaiting_settlement', reason='Settlement is still open. Partial credits are visible; no settled discrepancy is calculated.')
                else:
                    residual = Decimal(s['value']) - decimal_sum(credits) - decimal_sum(deductions)
                    r.update(residual=str(residual), state='unexplained_difference' if residual > 0 else 'excess_arrival' if residual < 0 else 'reconciled_claims',
                             reason='Sender debit minus recorded credits minus submitted pre-credit deductions. Inspect each supporting record; this is a claim-based reconciliation, not a theft finding.')
        output.append(r)
    return sorted(output, key=lambda r: r['transfer_id'])


def stage_comparison(kind, target, evidence, due_at, now):
    rows = [e for e in evidence if e['kind'] == kind]
    result = {'kind': kind, 'target': target, 'observed': None, 'shortfall': None, 'overage': None,
              'evidence_ids': [e['id'] for e in rows], 'covers_through': None}
    if not target:
        return {**result, 'state': 'target_not_defined', 'reason': 'No service outcome target was defined for this obligation.'}
    if not rows:
        return {**result, 'state': 'not_due' if now < due_at else 'evidence_missing', 'reason': 'No cumulative snapshot is recorded; missing evidence is not zero.'}
    # Latest cumulative report per declared issuer. Never add repeated snapshots.
    latest = {}
    for e in sorted(rows, key=lambda x: (datetime.fromisoformat(x['covers_through']), datetime.fromisoformat(x['observed_at']), x['created_at'])):
        latest[e['issuer_id']] = e
    rows = list(latest.values())
    result['evidence_ids'] = [e['id'] for e in rows]
    if any(e['unit'] != target['unit'] for e in rows):
        return {**result, 'state': 'not_comparable', 'reason': 'Snapshot units differ from the obligation target. No quantity comparison performed.'}
    if len({(Decimal(e['value']), datetime.fromisoformat(e['covers_through'])) for e in rows}) > 1:
        return {**result, 'state': 'conflicting_observations', 'reason': 'Declared issuers report different cumulative values or coverage times. Reconcile their scopes before choosing a quantity.'}
    row = rows[0]
    result.update(observed=row['value'], covers_through=row['covers_through'])
    if now < due_at:
        return {**result, 'state': 'not_due', 'reason': 'The obligation is not due. Progress is visible without declaring a shortfall.'}
    if datetime.fromisoformat(row['covers_through']) < due_at:
        return {**result, 'state': 'deadline_evidence_needed', 'reason': 'Latest cumulative evidence does not cover the deadline.'}
    difference = Decimal(target['value']) - Decimal(row['value'])
    return {**result, 'shortfall': str(max(difference, Decimal(0))), 'overage': str(max(-difference, Decimal(0))),
            'state': 'shortfall' if difference > 0 else 'overage' if difference < 0 else 'reported_target_met',
            'reason': 'Target compared with cumulative reported coverage at or after its deadline. Receipt, acceptance and service observations remain distinct; no independent field verification is implied.'}


def assess(obligation, evidence, actions, now=None):
    now = now or utcnow()
    with localcontext() as ctx:
        ctx.prec = 50
        transfers = reconcile_transfers(evidence, now)
        stages = [stage_comparison(k, obligation['outcome_target'] if k == 'outcome' else obligation['delivery_target'],
                                   evidence, datetime.fromisoformat(obligation['due_at']), now) for k in STAGES]
        signals = []
        def signal(key, title, reason, next_step, stage):
            signals.append({'key': key, 'title': title, 'reason': reason, 'next_step': next_step, 'stage': stage})
        if not transfers:
            signal('funds:missing', 'Financial chain unobserved', 'No executed payment or receiving credit is linked to this obligation.',
                   'Obtain the executed payment reference and a separately attributable recipient credit. A budget is not proof of release.', 'funds')
        for t in transfers:
            if t['state'] != 'reconciled_claims':
                signal('funds:' + digest([t['transfer_id'], t['sender_id'], t['recipient_id']])[:24],
                       t['state'].replace('_', ' ').capitalize(), t['reason'],
                       'Inspect the debit, recipient credit, shared transfer identity, settlement cut-off and any pre-credit deduction evidence.', 'funds')
        for s in stages:
            if s['state'] not in ('reported_target_met', 'overage', 'target_not_defined', 'not_due'):
                signal('stage:' + s['kind'], s['kind'].capitalize() + ': ' + s['state'].replace('_', ' '), s['reason'],
                       'Obtain a cumulative ' + s['kind'] + ' record for this exact obligation, with unit, coverage date, issuer and inspection basis.', s['kind'])
        # A matching quantity is not independent acceptance if only the dispatching party reports it.
        dispatchers = {e['issuer_id'] for e in evidence if e['kind'] == 'dispatched'}
        acceptors = {e['issuer_id'] for e in evidence if e['kind'] == 'accepted'}
        if dispatchers and acceptors and not acceptors.difference(dispatchers):
            signal('acceptance:issuer', 'Acceptance needs separate attribution', 'The declared dispatch and acceptance issuers overlap entirely.',
                   'Obtain acceptance or inspection evidence attributable to a separate receiving or inspection party.', 'accepted')
        for left, right in zip(stages[:2], stages[1:3]):
            if (left['observed'] is not None and right['observed'] is not None and
                left['target']['unit'] == right['target']['unit'] and datetime.fromisoformat(left['covers_through']) == datetime.fromisoformat(right['covers_through']) and
                Decimal(right['observed']) > Decimal(left['observed'])):
                signal('sequence:'+left['kind']+':'+right['kind'], 'Delivery stage quantities disagree',
                       right['kind'].capitalize()+' exceeds '+left['kind']+' for the same coverage timestamp.',
                       'Inspect scope, returns, timing and classification before treating these as one delivery chain.', right['kind'])
        overdue = sum(a['status'] != 'completed' and datetime.fromisoformat(a['due_at']) < now for a in actions)
        accepted = next(s for s in stages if s['kind'] == 'accepted')
        outcome = next(s for s in stages if s['kind'] == 'outcome')
        completion_stale = any(a['status'] == 'completed' and not any(e['id'] == a.get('completion_evidence_id') for e in evidence) for a in actions)
        if completion_stale:
            signal('actions:superseded', 'Review completed follow-up evidence', 'A completion reference was superseded by newer evidence.',
                   'Review the correction and update the follow-up. A prior completion does not resolve new evidence.', 'actions')
        complete = all(s['state'] in ('reported_target_met', 'overage', 'target_not_defined') for s in stages)
        return {'as_of': now.isoformat(), 'transfers': transfers, 'stages': stages, 'signals': signals,
                'state': 'attention_required' if signals else 'reported_chain_complete' if complete else 'evidence_pending',
                'open_actions': sum(a['status'] != 'completed' for a in actions), 'overdue_actions': overdue,
                'accepted': accepted, 'outcome': outcome, 'limitations': LIMITS}


def bundle(db, row, now=None):
    evidence = []
    for e in db.execute('SELECT * FROM assurance_evidence WHERE obligation_id=? ORDER BY created_at,id', (row['id'],)):
        evidence.append({**json.loads(e['payload']), 'id': e['id'], 'created_at': e['created_at'],
                         'payload_hash': e['payload_hash'], 'superseded_by': e['superseded_by'], 'assurance': 'unverified_submission'})
    actions = [json.loads(a['payload']) for a in db.execute('SELECT payload FROM assurance_actions WHERE obligation_id=? ORDER BY id', (row['id'],))]
    obligation = json.loads(row['payload'])
    active = [e for e in evidence if not e['superseded_by']]
    assessment = assess(obligation, active, actions, now)
    analyses = [json.loads(a['payload']) for a in db.execute('SELECT payload FROM assurance_analyses WHERE obligation_id=? ORDER BY id', (row['id'],))]
    for run in analyses:
        run['basis_current'] = run['basis_hash'] == analysis_basis(assessment['accepted'])
    return {'id': row['id'], 'version': row['version'], 'created_at': row['created_at'], 'updated_at': row['updated_at'],
            'obligation': obligation, 'evidence': evidence, 'actions': actions, 'analyses': analyses, 'assessment': assessment}


def analysis_basis(stage):
    return digest({k: stage[k] for k in ('target', 'observed', 'evidence_ids', 'state', 'covers_through')})


@router.get('/status')
def status():
    return {'mode': 'attributed evidence pilot', 'limitations': LIMITS,
            'connections': {'bank_or_treasury_feed': False, 'institutional_action_executor': False},
            'storage': 'Operations SQLite path; requires a persistent deployment volume.',
            'kinds': ['funds_sent', 'funds_received', 'settlement_deduction', *STAGES]}


@router.post('/obligations')
def create_obligation(body: ObligationInput):
    oid = uuid.uuid4().hex
    now = utcnow().isoformat()
    payload = body.model_dump(mode='json')
    with assurance_connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM assurance_obligations WHERE reference=?', (body.reference,)).fetchone():
            raise HTTPException(409, 'This obligation reference already exists. Open it to add evidence; do not duplicate the obligation.')
        db.execute('INSERT INTO assurance_obligations VALUES(?,?,?,?,?,?)', (oid, body.reference, canonical(payload), 1, now, now))
        audit(db, oid, 'obligation_created', {'obligation': payload, 'payload_hash': digest(payload)})
        return bundle(db, db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone())


@router.get('/obligations')
def list_obligations(country: str = '', q: str = Query(default='', max_length=200), synthetic: bool = False,
                     attention: bool = False, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    with assurance_connection() as db:
        # SQLite JSON predicates bound the selected records before assessments are calculated.
        where = "json_extract(payload,'$.synthetic')=?"
        params = [int(synthetic)]
        if country:
            where += " AND (json_extract(payload,'$.country')=? OR json_extract(payload,'$.origin_country')=?)"
            params.extend([country, country])
        if q:
            where += " AND (instr(lower(json_extract(payload,'$.title')),lower(?))>0 OR instr(lower(reference),lower(?))>0 OR instr(lower(json_extract(payload,'$.community')),lower(?))>0)"
            params.extend([q, q, q])
        rows = db.execute('SELECT * FROM assurance_obligations WHERE ' + where + ' ORDER BY updated_at DESC,id', params).fetchall()
        now = utcnow()
        results = [bundle(db, r, now) for r in rows]
        total_scope = len(results)
        counts = Counter(r['assessment']['state'] for r in results)
        if attention:
            results = [r for r in results if r['assessment']['signals']]
        return {'obligations': results[offset:offset+limit], 'total': len(results), 'scope_count': total_scope,
                'state_counts': dict(counts), 'as_of': now.isoformat(), 'synthetic': synthetic,
                'coverage': 'Only registered obligations in this deployment and selected scope. No global coverage or combined loss total is implied.'}


@router.get('/obligations/{oid}')
def get_obligation(oid: str):
    with assurance_connection() as db:
        row = db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Obligation not found')
        return bundle(db, row)


@router.post('/obligations/{oid}/evidence')
def add_evidence(oid: str, body: EvidenceInput):
    eid = uuid.uuid4().hex
    with assurance_connection() as db:
        row = locked_obligation(db, oid, body.expected_version)
        obligation = json.loads(row['payload'])
        if body.kind == 'outcome' and not obligation['outcome_target']:
            raise HTTPException(422, 'Define an outcome target when registering the obligation before recording service outcomes.')
        if body.supersedes:
            old = db.execute('SELECT * FROM assurance_evidence WHERE id=? AND obligation_id=? AND superseded_by IS NULL', (body.supersedes, oid)).fetchone()
            if not old:
                raise HTTPException(409, 'Correction must reference current evidence in this obligation')
            prior = json.loads(old['payload'])
            if any(prior[k] != getattr(body, k) for k in ('kind', 'issuer_id', 'ledger_reference', 'transfer_id', 'sender_id', 'recipient_id')):
                raise HTTPException(422, 'A correction must preserve stage, issuer, ledger reference and transfer identity')
        duplicate = db.execute('SELECT id FROM assurance_evidence WHERE issuer_id=? AND ledger_reference=? AND kind=? AND superseded_by IS NULL',
                               (body.issuer_id, body.ledger_reference, body.kind)).fetchone()
        if duplicate and duplicate['id'] != body.supersedes:
            raise HTTPException(409, 'This issuer ledger entry is already recorded. Correct the existing entry rather than counting it again.')
        if body.kind == 'funds_sent':
            for e in db.execute("SELECT id,payload FROM assurance_evidence WHERE kind='funds_sent' AND superseded_by IS NULL"):
                if e['id'] != body.supersedes and transfer_key(json.loads(e['payload'])) == (body.transfer_id, body.sender_id, body.recipient_id):
                    raise HTTPException(409, 'This executed transfer is already allocated to an obligation. Splitting allocations requires a separate allocation model; do not count the transfer twice.')
        payload = body.model_dump(mode='json', exclude={'expected_version'})
        now = utcnow().isoformat()
        db.execute('INSERT INTO assurance_evidence VALUES(?,?,?,?,?,?,?,?,?)',
                   (eid, oid, body.kind, body.issuer_id, body.ledger_reference, canonical(payload), digest(payload), now, None))
        if body.supersedes:
            db.execute('UPDATE assurance_evidence SET superseded_by=? WHERE id=?', (eid, body.supersedes))
        audit(db, oid, 'evidence_corrected' if body.supersedes else 'evidence_recorded', {'evidence_id': eid, 'payload_hash': digest(payload), 'supersedes': body.supersedes})
        bump(db, oid)
        return bundle(db, db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone())


@router.post('/obligations/{oid}/actions')
def create_action(oid: str, body: ActionInput):
    with assurance_connection() as db:
        row = locked_obligation(db, oid, body.expected_version)
        if body.signal_key and body.signal_key not in {s['key'] for s in bundle(db, row)['assessment']['signals']}:
            raise HTTPException(422, 'The selected issue is no longer current. Refresh the evidence before assigning this follow-up.')
        aid = uuid.uuid4().hex
        payload = {**body.model_dump(mode='json', exclude={'expected_version'}), 'id': aid, 'status': 'open',
                   'created_at': utcnow().isoformat(), 'completion_evidence_id': None}
        db.execute('INSERT INTO assurance_actions VALUES(?,?,?)', (aid, oid, canonical(payload)))
        audit(db, oid, 'followup_created', payload)
        bump(db, oid)
        return bundle(db, db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone())


@router.post('/obligations/{oid}/actions/{aid}')
def update_action(oid: str, aid: str, body: ActionUpdate):
    with assurance_connection() as db:
        locked_obligation(db, oid, body.expected_version)
        row = db.execute('SELECT payload FROM assurance_actions WHERE id=? AND obligation_id=?', (aid, oid)).fetchone()
        if not row:
            raise HTTPException(404, 'Follow-up not found')
        if body.completion_evidence_id and not db.execute('SELECT 1 FROM assurance_evidence WHERE id=? AND obligation_id=? AND superseded_by IS NULL', (body.completion_evidence_id, oid)).fetchone():
            raise HTTPException(422, 'Completion evidence must be a current retained record in this obligation')
        payload = {**json.loads(row['payload']), **body.model_dump(mode='json', exclude={'expected_version'}), 'updated_at': utcnow().isoformat()}
        db.execute('UPDATE assurance_actions SET payload=? WHERE id=?', (canonical(payload), aid))
        audit(db, oid, 'followup_updated', payload)
        bump(db, oid)
        return bundle(db, db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone())


@router.post('/obligations/{oid}/delivery-analysis')
async def run_delivery_analysis(oid: str, body: AnalysisInput):
    from api import DeliveryAnalyzeRequest, analyze_delivery
    current = get_obligation(oid)
    if current['version'] != body.expected_version:
        raise HTTPException(409, 'Evidence changed. Refresh before running the engine.')
    stage = current['assessment']['accepted']; o = current['obligation']
    if stage['shortfall'] is None:
        raise HTTPException(422, 'Calibrated delivery analysis requires comparable acceptance evidence covering the deadline.')
    request = DeliveryAnalyzeRequest(contract_id=o['reference'], profile=body.profile, country_code=o['country'], project_name=o['title'],
        outcomes=[{'outcome_id':oid, 'description':o['promise'], 'unit':stage['target']['unit'],
                   'quantity_planned':float(stage['target']['value']), 'quantity_delivered':float(stage['observed']),
                   'inspection_date':stage['covers_through']}])
    result = await analyze_delivery(request)
    run = {'id':uuid.uuid4().hex, 'created_at':utcnow().isoformat(), 'profile':body.profile,
           'input_version':body.expected_version, 'basis_hash':analysis_basis(stage), 'evidence_ids':stage['evidence_ids'],
           'result':result.model_dump(mode='json'),
           'scope':'Existing calibrated delivery engine, using only the comparable accepted quantity. Float-based engine thresholds are separate from the exact Decimal ledger. No independently verified inspection, financial finding or unsupported dimensions are inferred.'}
    with assurance_connection() as db:
        locked_obligation(db, oid, body.expected_version)
        db.execute('INSERT INTO assurance_analyses VALUES(?,?,?)', (run['id'], oid, canonical(run)))
        audit(db, oid, 'delivery_analysis_recorded', {'analysis_id':run['id'], 'payload_hash':digest(run)})
        bump(db, oid)
        return bundle(db, db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone())


@router.get('/obligations/{oid}/export')
def export_obligation(oid: str):
    with assurance_connection() as db:
        row = db.execute('SELECT * FROM assurance_obligations WHERE id=?', (oid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Obligation not found')
        current = bundle(db, row)
        history = [{**dict(h), 'payload': json.loads(h['payload'])} for h in db.execute('SELECT * FROM assurance_history WHERE obligation_id=? ORDER BY seq', (oid,))]
        prev = ''
        valid = True
        for h in history:
            valid &= h['previous_hash'] == prev and h['hash'] == digest({'previous_hash': prev, 'payload': h['payload']})
            prev = h['hash']
        valid &= bool(history) and history[0]['payload']['detail']['obligation'] == current['obligation']
        recorded = {h['payload']['detail']['evidence_id']: h['payload']['detail'] for h in history if h['payload']['action'] in ('evidence_recorded', 'evidence_corrected')}
        by_id = {e['id']: e for e in current['evidence']}
        valid &= set(recorded) == set(by_id)
        for e in current['evidence']:
            payload = {k: v for k, v in e.items() if k not in ('id', 'created_at', 'payload_hash', 'superseded_by', 'assurance')}
            valid &= digest(payload) == e['payload_hash'] == recorded[e['id']]['payload_hash']
            corrected = next((h['payload']['detail']['evidence_id'] for h in history if h['payload']['action'] == 'evidence_corrected' and h['payload']['detail']['supersedes'] == e['id']), None)
            valid &= e['superseded_by'] == corrected
        last_actions = {h['payload']['detail']['id']: h['payload']['detail'] for h in history if h['payload']['action'] in ('followup_created', 'followup_updated')}
        valid &= last_actions == {a['id']: a for a in current['actions']}
        recorded_runs = {h['payload']['detail']['analysis_id']:h['payload']['detail']['payload_hash'] for h in history if h['payload']['action']=='delivery_analysis_recorded'}
        valid &= set(recorded_runs) == {a['id'] for a in current['analyses']}
        for run in current['analyses']:
            valid &= digest({k:v for k,v in run.items() if k!='basis_current'}) == recorded_runs.get(run['id'])
        valid &= current['version'] == len(history)
        return {'current': current, 'history': history, 'exported_at': utcnow().isoformat(),
                'integrity': {'local_chain_and_content_valid': bool(valid), 'head': prev,
                              'meaning': 'Local hash chain only; not an issuer signature, independent timestamp or external authentication.'}}


@router.post('/example')
def worked_example():
    """Explicit synthetic branch. Never included in the institutional default portfolio."""
    with assurance_connection() as db:
        existing = db.execute("SELECT id FROM assurance_obligations WHERE reference='SYNTHETIC-DELIVERY-ASSURANCE-001'").fetchone()
        if existing:
            oid = existing['id']
        else:
            oid = None
    if oid:
        return get_obligation(oid)
    now = utcnow() - timedelta(minutes=1)
    due = now - timedelta(days=5)
    result = create_obligation(ObligationInput(reference='SYNTHETIC-DELIVERY-ASSURANCE-001', title='Worked example · clinic supply programme',
        sector='Health', country='GH', origin_country='NL', community='25 fictional clinics',
        promise='Deliver and accept 1,000 medical kits, then establish usable supplies at 25 clinics.',
        owner='Example programme team', recipient='Example receiving authority', baseline_url='https://example.org/synthetic/contract',
        due_at=due, delivery_target=Target(value='1000', unit='medical_kit'), outcome_target=Target(value='25', unit='clinic'),
        budget='1000000', currency='USD', synthetic=True))
    oid = result['id']
    for kind, value, issuer, ref in [('funds_sent', '1000000', 'example-treasury', 'debit-001'),
                                    ('funds_received', '965000', 'example-recipient-bank', 'credit-001'),
                                    ('settlement_deduction', '5000', 'example-transfer-provider', 'fee-001'),
                                    ('dispatched', '1000', 'example-supplier', 'dispatch-001'),
                                    ('received', '820', 'example-warehouse', 'receipt-001'),
                                    ('accepted', '730', 'example-inspector', 'acceptance-001'),
                                    ('outcome', '18', 'example-service-monitor', 'service-001')]:
        financial = kind in MONEY
        result = add_evidence(oid, EvidenceInput(expected_version=result['version'], kind=kind, value=value,
            unit='currency' if financial else 'clinic' if kind == 'outcome' else 'medical_kit', currency='USD' if financial else None,
            issuer_id=issuer, issuer_name=issuer.replace('-', ' ').title(), ledger_reference=ref,
            document_url='https://example.org/synthetic/' + ref, observed_at=now-timedelta(days=10) if kind == 'funds_sent' else now,
            covers_through=None if financial else now, transfer_id='EXAMPLE-TRANSFER-001' if financial else None,
            sender_id='example-treasury' if financial else None, recipient_id='example-receiving-authority' if financial else None,
            settlement_due_at=due if kind == 'funds_sent' else None,
            note='Fictional worked example. No actual transfer, delivery or verification occurred.'))
    return result


def research_facts(scope, obligation_ids=None):
    """Evidence-backed retrieval, scoped before the latest-200 scan; examples opt-in only."""
    from research_evidence import fact, period_matches
    requested = obligation_ids or []
    with assurance_connection() as db:
        where = '1=1' if requested else "json_extract(payload,'$.synthetic')=0"
        params = []
        if requested:
            where += ' AND id IN ('+','.join('?' for _ in requested)+')'
            params.extend(requested)
        if scope['countries']:
            placeholders = ','.join('?' for _ in scope['countries'])
            where += f" AND (json_extract(payload,'$.country') IN ({placeholders}) OR json_extract(payload,'$.origin_country') IN ({placeholders}))"
            params.extend(scope['countries']*2)
        rows = db.execute('SELECT * FROM assurance_obligations WHERE '+where+' ORDER BY updated_at DESC,id LIMIT 200', params).fetchall()
        output = []
        for row in rows:
            c = bundle(db, row); o = c['obligation']; a = c['assessment']
            if not period_matches(int(o['due_at'][:4]), scope): continue
            prefix = 'SYNTHETIC EXAMPLE. ' if o['synthetic'] else ''
            quantities = '; '.join(s['kind']+': '+str(s['observed'])+' '+(s['target']['unit'] if s['target'] else 'target undefined')+', '+s['state']+', shortfall '+str(s['shortfall']) for s in a['stages'])
            transfers = '; '.join(t['transfer_id']+': '+str(t['sent'])+' sent, '+str(t['received'])+' credited '+str(t['currency'])+', '+t['state']+', residual '+str(t['residual']) for t in a['transfers']) or 'No executed transfer chain observed'
            urls = list(dict.fromkeys([str(o['baseline_url']), *[e['document_url'] for e in c['evidence'] if not e['superseded_by']]]))
            output.append(fact('obligation:'+c['id']+':v'+str(c['version']), 'delivery_assurance', o['title'],
                prefix+o['promise']+' Community: '+o['community']+'. Deadline: '+o['due_at']+'. '+transfers+'. '+quantities+'. '+
                str(a['open_actions'])+' open follow-ups. '+a['limitations'],
                {'obligation_id':c['id'], 'version':c['version'], 'synthetic':o['synthetic'], 'transfers':a['transfers'],
                 'stages':a['stages'], 'signals':a['signals'], 'actions':c['actions'], 'analyses':c['analyses']}, '/assurance/obligations/'+c['id']+'/report',
                country=o['country'], origin=o['origin_country'], destination=o['country'], source_urls=urls,
                obligation_id=c['id'], snapshot_hash=digest({'obligation':o, 'evidence':c['evidence'], 'actions':c['actions']})))
        return output
