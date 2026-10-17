"""Published material export context; never supplied to the detection engine."""
import json
from pathlib import Path
from fastapi import APIRouter

SNAPSHOT_PATH = Path(__file__).with_name('materials_snapshot.json')
SNAPSHOT = json.loads(SNAPSHOT_PATH.read_text(encoding='utf-8'))
router = APIRouter()


@router.get('/watch-data/materials')
async def material_exports():
    return SNAPSHOT
