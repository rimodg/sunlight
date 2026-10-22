"""Extract dated UCDP candidate observations from a pinned public data mirror."""
import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path

REVISION = 'a01e6fe3dd2fac5f6335cc24eca3ea2296b24779'
SHA256 = 'daad6da8a79dfdf9ce4b4dee7391797bc7532c83dba0fedf1d742f8e870cac99'
SOURCE = f'https://raw.githubusercontent.com/drdjcannon/worldwatch-data/{REVISION}/ucdp/ucdp-events.json'


def build(path):
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError('Source checksum mismatch')
    source = json.loads(content)
    if source['schema'] != 1 or source['annualVersion'] != '26.1' or source['candidateVersion'] != '26.0.8':
        raise ValueError('Unexpected source version')
    events, seen = [], set()
    for row in source['events']:
        if row['id'] in seen:
            raise ValueError('Duplicate source event ID')
        seen.add(row['id'])
        start, end = date.fromisoformat(row['date_start']), date.fromisoformat(row['date_end'])
        if end < start:
            raise ValueError('Invalid event date interval')
        if start.year != 2026:
            continue
        coordinates = [row['longitude'], row['latitude']]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in coordinates) or not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90:
            raise ValueError('Invalid coordinates')
        if row['type_of_violence'] not in (1,2,3) or row['where_prec'] not in range(1,8):
            raise ValueError('Unknown violence or location precision')
        events.append({'id':row['id'], 'start':start.isoformat(), 'end':end.isoformat(),
            'coordinates':coordinates, 'reporting_area':row['country'], 'place':row['where_coordinates'],
            'type':row['type_of_violence'], 'location_precision':row['where_prec'],
            'date_precision':row['date_prec'], 'event_clarity':row['event_clarity'],
            'sides':[row['side_a'],row['side_b']]})
    plotted = [e for e in events if e['location_precision'] in (1,2)]
    return {
        'schema_version':'sunlight.conflict-context.v1', 'status':'bundled_snapshot',
        'source':'Uppsala Conflict Data Program (UCDP)', 'version':'Candidate 26.0.8',
        'year':2026, 'preliminary':True, 'retrieved_date':'2026-10-17',
        'source_generated_at':source['generatedAt'], 'latest_start':max(e['start'] for e in events),
        'earliest_start':min(e['start'] for e in events), 'latest_end':max(e['end'] for e in events),
        'source_url':'https://ucdp.uu.se/downloads/', 'candidate_url':'https://ucdp.uu.se/downloads/candidateged/',
        'mirror_revision':REVISION, 'mirror_url':f'https://github.com/drdjcannon/worldwatch-data/tree/{REVISION}',
        'source_file':{'url':SOURCE,'sha256':SHA256},
        'license':'CC BY 4.0', 'license_url':'https://creativecommons.org/licenses/by/4.0/',
        'citations':[
            {'title':'Davies, Pettersson & Öberg (2026), Organized violence 1989–2025, and violent political protests. Journal of Peace Research.','url':'https://doi.org/10.1093/jopres/xjag046'},
            {'title':'Sundberg & Melander (2013), Introducing the UCDP Georeferenced Event Dataset. Journal of Peace Research 50(4), 523–532.','url':'https://doi.org/10.1177/0022343313484347'},
        ],
        'definition':'Records of fatal organized violence: state-based conflict, non-state conflict, and one-sided violence against civilians, as coded by UCDP. An event marker does not classify an entire country as a war zone or depict a front line.',
        'coverage':'Capped public mirror extract, not the full UCDP database or complete worldwide coverage. The mirror keeps 2,000 records: up to 1,500 recent candidate records and at least 500 annual records. SUNLIGHT selects the 1,500 records starting in 2026. These start August 5–31; some reported intervals extend into September. Missing points do not imply peace or absent violence.',
        'geography':'Only location precision 1 (exact named location) or 2 (near a named location) is drawn. Nearby-location coordinates are approximate references, not exact attack sites. Province/country centroids and broader or uncertain locations remain in the register but are not plotted. Identical source coordinates share one point; no random displacement is added.',
        'dates':'Candidate coding is preliminary and can be revised. Date precision and report intervals are retained; one record can summarize several incidents. The snapshot is fixed to the cited source revision, not a live alert or automatic refresh service.',
        'reporting_areas':'UCDP reporting areas can differ from map countries. Its Israel reporting area includes records in Gaza and the West Bank. Place names and coordinates remain unchanged. Country research filters plotted points against the approximate basemap boundary, rather than treating a UCDP reporting area as a procurement jurisdiction.',
        'interpretation':'Conflict observations and trade/procurement records have different coverage and periods. Co-location does not establish causation, aid or loan dependence, corruption, stolen funds, or an amount to recover. No conflict variable enters SUNLIGHT procurement findings or scores.',
        'method':'Filter the pinned mirror to date_start in 2026; retain source IDs, intervals, violence type, source coordinates, location/date precision and actors. Omit news headlines and casualty figures. Plot only precision 1/2, grouping exact matching coordinates without weighting point size by severity. No country-level totals from the mirror are presented as event-sample totals.',
        'record_count':len(events), 'plottable_count':len(plotted),
        'omitted_location_count':len(events)-len(plotted),
        'location_count':len({tuple(e['coordinates']) for e in plotted}), 'events':events,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('code/conflict_snapshot.json'))
    args = parser.parse_args(); snapshot = build(args.source)
    args.output.write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n')
    print({k:snapshot[k] for k in ('record_count','plottable_count','location_count','latest_start')})
