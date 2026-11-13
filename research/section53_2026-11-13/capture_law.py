"""Archive primary law outside Git; retain hashed, readable text extracts."""
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parents[2] / 'outputs/section53-2026-11-13/law'
SOURCES = {
    **{f'pa{s}': (f'ukpga/2023/54/section/{s}', f'section {s}') for s in (2, 3, 5, 9, 53, 87, 94)},
    **{f'pr{r}': (f'uksi/2024/692/regulation/{r}', f'regulation {r}') for r in (1, 5, 32, 33, 34, 35)},
    'transition': ('uksi/2024/716/regulation/5', 'regulation 5'),
    'commencement': ('uksi/2024/716/schedule', 'Schedule, section 53'),
}

def capture(item):
    key, (path, locator) = item
    url = f'https://www.legislation.gov.uk/{path}/data.xml'
    with urllib.request.urlopen(url, timeout=40) as response:
        raw = response.read(4 * 1024 * 1024)
        final = response.url
    root = ET.fromstring(raw)
    text = '\n'.join(' '.join(n.itertext()).strip() for n in root.iter() if n.tag.rsplit('}', 1)[-1] in ('Title', 'Pnumber', 'Text')) + '\n'
    encoded = text.encode()
    target = ARCHIVE / f'{key}.xml'
    target.write_bytes(raw)
    (HERE / f'{key}.txt').write_bytes(encoded)
    return {'id': key, 'url': url, 'final_url': final, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'locator': locator,
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'local_path': str(target),
            'extract_path': f'{key}.txt', 'extract_sha256': hashlib.sha256(encoded).hexdigest()}

if __name__ == '__main__':
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        manifest = sorted(pool.map(capture, SOURCES.items()), key=lambda x: x['id'])
    (HERE / 'law-sources.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'sources': len(manifest), 'archive': str(ARCHIVE)}))
