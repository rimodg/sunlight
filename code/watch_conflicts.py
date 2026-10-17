"""Dated geographic context. Conflict observations never enter detection scores."""
import json
from pathlib import Path
from fastapi import APIRouter

SNAPSHOT = json.loads(Path(__file__).with_name('conflict_snapshot.json').read_text(encoding='utf-8'))
router = APIRouter()


@router.get('/watch-data/conflicts')
async def conflict_context():
    return SNAPSHOT
