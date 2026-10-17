"""Read-only, bundled public aggregate data. No synthetic spending fallback."""
import json
from pathlib import Path
from fastapi import APIRouter

SNAPSHOT_PATH = Path(__file__).with_name('public_procurement_snapshot.json')
SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text(encoding='utf-8'))
router = APIRouter()


@router.get('/watch-data/procurement')
async def public_procurement():
    return SNAPSHOT
