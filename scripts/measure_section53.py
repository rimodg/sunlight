#!/usr/bin/env python3
"""Capture FTS to an isolated protected artifact and replay section-53 refusals.

No service configuration, live journal or raw-body persistence. This is an
explicit manual measurement, not deployment of the adapter or a source switch.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'code'))
from watch_capture import checked_url, fetch, policy, project_page
from watch_journal import admit
from invariant_core import Applicability, Citation, Scope
from section53 import DatedEvidence, Publication, load_profile, packet

QUERY = 'https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?updatedFrom=2026-11-12T00:00:00&updatedTo=2026-11-13T00:00:00&limit=100'
SOURCE = {'id':'fts-section53-measurement','adapter':'central_platform',
          'organisation_only_reviewed':True,'interval_seconds':900,'url':QUERY}


def canonical(value):
    return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()


def capture():
    policy({'schema':'sunlight.watch-source-policy.v1','sources':[SOURCE]})
    url, seen, pages = QUERY, set(), []
    while url and len(pages) < 30:
        checked_url(url, QUERY)
        if url in seen: raise ValueError('pagination_cycle')
        seen.add(url)
        receipt={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'status':None}
        try:
            response=fetch(url)
        except (OSError, TimeoutError):
            receipt['failure']='transport_failure';pages.append(receipt)
            break
        receipt['status']=response['status']
        if response['status'] != 200 or response.get('read_failed'):
            receipt['failure']='http_or_body_read_failure';pages.append(receipt)
            break
        body=response['body']
        try:
            projection=project_page(SOURCE,body,url=url)
        except (ValueError, TypeError):
            receipt['failure']='page_projection_refused';pages.append(receipt)
            break
        receipt.update(source_sha256=hashlib.sha256(body).hexdigest(),source_bytes=len(body),
                       projection_sha256=hashlib.sha256(canonical(projection)).hexdigest(),projection=projection)
        pages.append(receipt)
        url=projection['next']
        print(json.dumps({'page':len(pages),'received':projection['received_count']}),flush=True)
    result={'schema':'sunlight.section53-capture.v1','source_policy':SOURCE,'complete':url is None,'raw_bodies_retained':False,'pages':pages}
    admit(result)
    return result


def replay(captured):
    if captured.get('schema') != 'sunlight.section53-capture.v1': raise ValueError('capture_schema')
    admit(captured)
    profile=load_profile(ROOT/'config/section53-profile.json','ordinary')
    results=[];received=admitted=refused=0;release_keys=set();marked_releases=set()
    for pi,page in enumerate(captured['pages']):
        if 'projection' not in page: continue
        projection=page['projection']
        if hashlib.sha256(canonical(projection)).hexdigest()!=page['projection_sha256']: raise ValueError('projection_hash')
        if projection.get('adapter_version')!='central-platform-contract-details.v1':raise ValueError('adapter_version')
        received+=projection['received_count'];admitted+=len(projection['records']);refused+=len(projection['refusals'])
        for item in projection['records']:
            r=item['record'];ri=item['index'];key=(r['ocid'],r['id']);release_keys.add(key)
            for ci,c in enumerate(r.get('contracts',[])):
                for di,d in enumerate(c.get('documents',[])):
                    # Related/previous documents cannot stand in for this notice.
                    if not d or d.get('id')!=r['id']:continue
                    marked_releases.add(key)
                    loc=f'/releases/{ri}/contracts/{ci}'
                    signed=c.get('dateSigned');published=d.get('datePublished')
                    parsed_pub=datetime.fromisoformat(published.replace('Z','+00:00')) if published else None
                    pub_day=parsed_pub.astimezone(ZoneInfo('Europe/London')).date() if parsed_pub else None
                    sig_day=datetime.fromisoformat(signed.replace('Z','+00:00')).date() if signed else None
                    citation=Citation(page['url'],loc+f'/documents/{di}/datePublished',page['source_sha256'])
                    pub=Publication(DatedEvidence(pub_day,'public_access','UK civil calendar',citation)) if pub_day else None
                    # Explicit owner-approved gate: no entry date is present in
                    # this projection. Do not infer one from signature or scope.
                    scope=Scope(Applicability.UNKNOWN,'Entry date and complete section-53 scope are not admitted')
                    finding=packet(entry=None,publication=pub,scope=scope,profile=profile)
                    results.append({'ocid':r['ocid'],'release_id':r['id'],'contract_id':c.get('id'),'page':pi,
                        'locator':loc,'source_sha256':page['source_sha256'],'source_url':page['url'],
                        'dateSigned':signed,'signature_locator':loc+'/dateSigned','datePublished':published,
                        'publication_locator':loc+f'/documents/{di}/datePublished',
                        'aboveThreshold':c.get('aboveThreshold'),
                        'signature_to_publication_calendar_days':(pub_day-sig_day).days if pub_day and sig_day else None,
                        'measurement_basis':'Signature source calendar date; publication instant converted to Europe/London civil date. Not a legal assessment or entry-date bound.',
                        'assessment':finding})
    from collections import Counter
    states=dict(sorted(Counter(r['assessment']['finding']['state'] for r in results).items()))
    days=[r['signature_to_publication_calendar_days'] for r in results if r['signature_to_publication_calendar_days'] is not None]
    result={'schema':'sunlight.section53-results.v1','capture_complete':captured['complete'],
        'counts':{'received_release_rows':received,'admitted_release_rows':admitted,'refused_release_rows':refused,
                  'distinct_release_keys':len(release_keys),'contract_details_releases':len(marked_releases),
                  'contract_notice_rows':len(results),'both_dates':len(days),
                  'above_threshold_true':sum(r['aboveThreshold'] is True for r in results),
                  'above_threshold_false':sum(r['aboveThreshold'] is False for r in results),
                  'entry_date_confirmed':sum(r['assessment']['contract_entry'] is not None for r in results),
                  'assessable':sum(states.get(s,0) for s in ('HOLDS','BREAKS')),'states':states},
        'plain_measurement':{'minimum_days':min(days) if days else None,'maximum_days':max(days) if days else None,
                             'negative_gaps':sum(d<0 for d in days),'legal_assessment':False},'results':results}
    admit(result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--replay',type=Path)
    args=parser.parse_args()
    if args.output.exists(): raise SystemExit('Output must be a new directory; existing evidence is preserved')
    captured=json.loads(args.replay.read_text()) if args.replay else capture()
    results=replay(captured)
    args.output.mkdir(parents=True)
    (args.output/'capture.json').write_bytes(canonical(captured))
    (args.output/'results.json').write_bytes(canonical(results))
    print(json.dumps(results['counts'],indent=2))
    return 0 if captured['complete'] else 2

if __name__=='__main__': raise SystemExit(main())
