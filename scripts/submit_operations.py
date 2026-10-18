"""Submit validated normalized publisher snapshots to an authorized SUNLIGHT deployment.

Uses SUNLIGHT_CONNECTOR_USER/PASSWORD from the caller's environment. Never prints
credentials or payloads. No redirects or external document fetching. This is a
push client, not a UN Quantum/Compass mapper or source poller.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'code'))
from operations import IngestRequest, SourceInput


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='SUNLIGHT API origin, e.g. https://your-service.onrender.com')
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--source', type=Path, help='Optional source registration JSON; immutable once registered')
    parser.add_argument('--dry-run', action='store_true')
    args=parser.parse_args()
    target=urlparse(args.url)
    if not target.hostname:
        parser.error('--url requires a valid hostname')
    if target.username or target.password or target.query or target.fragment or target.path not in ('','/'):
        parser.error('--url must be an origin without credentials, path, query or fragment')
    if target.scheme!='https' and not (target.scheme=='http' and target.hostname in ('127.0.0.1','localhost','::1')):
        parser.error('Use HTTPS, or HTTP loopback for local development')
    try:
        if args.batch.stat().st_size>2*1024*1024:
            raise ValueError('Batch exceeds 2 MB')
        batch=IngestRequest.model_validate_json(args.batch.read_text())
        source=SourceInput.model_validate_json(args.source.read_text()) if args.source else None
        if source and source.source_id!=batch.source_id:
            raise ValueError('Source IDs do not match')
    except Exception:
        print('Input validation failed; check files against /openapi.json. No request sent.',file=sys.stderr);return 2
    if args.dry_run:
        print(json.dumps({'valid':True,'events':len(batch.events),'network_requests':0}));return 0
    password=os.environ.get('SUNLIGHT_CONNECTOR_PASSWORD')
    auth=httpx.BasicAuth(os.environ.get('SUNLIGHT_CONNECTOR_USER','sunlight'),password) if password else None
    try:
        with httpx.Client(base_url=args.url.rstrip('/'),auth=auth,timeout=120,follow_redirects=False) as client:
            if source:
                response=client.post('/operations/sources',json=source.model_dump(mode='json'))
                if response.status_code not in (200,201):
                    print(f'Source registration failed (HTTP {response.status_code}); ingestion not attempted.',file=sys.stderr);return 1
            response=client.post('/operations/ingest',json=batch.model_dump(mode='json'))
            if response.status_code!=200:
                print(f'Ingestion failed (HTTP {response.status_code}); inspect the deployment logs and schema.',file=sys.stderr);return 1
            result=response.json()
            print(json.dumps({'submitted':len(batch.events),'results':result['results']}));return 0
    except httpx.HTTPError:
        print('Deployment request failed; credentials and input data were not logged.',file=sys.stderr);return 1


if __name__=='__main__':
    raise SystemExit(main())
