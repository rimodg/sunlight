#!/usr/bin/env python3
"""Verify committed section-53 custody and replay; optionally original law bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.measure_section53 import replay,canonical


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--with-originals',action='store_true');args=p.parse_args()
    here=ROOT/'research/section53_2026-11-13'
    sources=[]
    for name in ('law-sources.json','guidance-sources.json'):
        for source in json.loads((here/name).read_text()):
            assert hashlib.sha256((here/source['extract_path']).read_bytes()).hexdigest()==source['extract_sha256'],source['id']
            if args.with_originals:
                raw=Path(source['local_path']).read_bytes()
                assert len(raw)==source['bytes'] and hashlib.sha256(raw).hexdigest()==source['sha256'],source['id']
            sources.append(source)
    order=json.loads((here/'order-check.json').read_text())
    if args.with_originals:
        raw=Path(order['local_path']).read_bytes()
        assert len(raw)==order['bytes'] and hashlib.sha256(raw).hexdigest()==order['sha256']
    captured=json.loads((here/'adapter-run/capture.json').read_text())
    results=json.loads((here/'adapter-run/results.json').read_text())
    assert replay(captured)==results
    assert captured['complete'] and captured['raw_bodies_retained'] is False
    expected=captured['source_policy']['url']; seen=set()
    for page in captured['pages']:
        assert page['url']==expected and expected not in seen
        seen.add(expected);assert page['status']==200
        expected=page['projection']['next']
    assert expected is None
    assert results['counts']['received_release_rows']==430
    assert results['counts']['contract_notice_rows']==150
    assert results['counts']['states']=={'UNASSESSABLE':150}
    assert results['counts']['assessable']==0
    profile=json.loads((ROOT/'config/section53-profile.json').read_text())
    admitted={x['url']:x['sha256'] for x in sources}
    for c in (profile['commencement_source'],profile['first_day']['source'],*(v['source'] for v in profile['variants'].values())):
        assert admitted[c['source']]==c['sha256']
    print(json.dumps({'source_extracts_verified':len(sources),'originals_verified':args.with_originals,
        'complete_pages':len(captured['pages']),'deterministic_replay':True,'counts':results['counts']},indent=2))

if __name__=='__main__':main()
