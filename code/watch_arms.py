"""Historical declarations and separately sourced accountability evidence, never risk scores."""
import json
from pathlib import Path
from fastapi import APIRouter

SNAPSHOT = json.loads(Path(__file__).with_name('arms_snapshot.json').read_text(encoding='utf-8'))
AUDITS = json.loads(Path(__file__).with_name('arms_audit_context.json').read_text(encoding='utf-8'))
SNAPSHOT = {**SNAPSHOT, 'field_evidence': AUDITS['field_evidence'], 'audit_provenance': {k:v for k,v in AUDITS.items() if k != 'field_evidence'}}
router = APIRouter()

@router.get('/watch-data/arms')
async def arms_context():
    return SNAPSHOT
