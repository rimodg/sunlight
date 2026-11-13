#!/usr/bin/env python3
"""Verify measurement custody and recount receipts; does not evaluate a legal rule.

Needs the external artifacts at the explicit paths in external-artifacts.json
and read-only access to the original watch journal. No HTTP requests or writes.
"""
from collections import Counter
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text())


def check_hash(path, expected, size=None):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected or (size is not None and len(raw) != size):
        raise ValueError(f'Artifact mismatch: {path}')
    return raw


def main():
    artifacts = read(HERE / 'external-artifacts.json')
    for artifact in artifacts:
        check_hash(Path(artifact['path']), artifact['sha256'], artifact['bytes'])
    for source in read(HERE / 'law-sources.json'):
        check_hash(Path(source['local_path']), source['sha256'], source['bytes'])
        check_hash(HERE / source['extract_path'], source['extract_sha256'])
    for source in read(HERE / 'framework-evidence.json'):
        raw = check_hash(Path(source['source']['local_path']), source['source']['sha256'])
        assert source['identifier'].encode() in raw
        assert b'PCR2015' in raw
        assert date.fromisoformat(source['start']).strftime('%d/%m/%Y').encode() in raw

    measurement = read(HERE / 'record-measurement.json')
    summary, records = measurement['summary'], measurement['records']
    cohort_path = next(Path(x['path']) for x in artifacts if Path(x['path']).name == 'cohort.json')
    cohort = read(cohort_path)
    keys = {(r['ocid'], r['release_id']) for r in records}
    original_keys = {(r['record']['key'], r['record']['release_id']) for r in cohort['rows']}
    assert keys == original_keys and len(records) == len(keys) == summary['release_records'] == 96
    assert len({r['ocid'] for r in records}) == summary['distinct_ocids'] == 93
    assert len({a for r in records for a in r['award_ids']}) == summary['distinct_award_ids'] == 94
    counts = Counter(r['regime'] for r in records)
    assert all(counts[k] == v for k, v in summary['enriched_regime_counts'].items())
    assert sum(bool(r['parent_notice_matches']) for r in records) == summary['records_with_parent_fts_notice_match'] == 6
    assert not any(r['corresponding_award_notice_matches'] for r in records)
    assert not any(r['assessable_under_pcr_norm'] or r['assessable_under_pa_norm'] for r in records)
    assert all(r['regime_reason'] for r in records)
    assert all(r['regime_evidence'] for r in records if r['regime'] == 'PCR2015')
    assert all(not x['locator'].endswith(('/name', '/title')) for r in records for x in r['identifier_candidates'])
    scan = read(HERE / 'fts-search-receipt.json')
    assert scan['complete'] and not scan['pages'][-1]['next']
    assert sum(p['releases'] for p in scan['pages']) == scan['records'] == 431
    assert scan['exact_tender_reference_intersections'] == []

    day = read(ROOT / 'reports/native-2026-11-13/first-day-summary.json')
    journal = Path('/Users/rimodg/Library/Application Support/SUNLIGHT/watch-live-sources-20261112/journal.sqlite3')
    con = sqlite3.connect(journal.as_uri() + '?mode=ro', uri=True)
    try:
        con.execute('BEGIN')
        assert con.execute('select hash from watch_events where seq=?', (summary['cohort_seq'],)).fetchone()[0] == summary['cohort_head']
        assert con.execute('select hash from watch_events where seq=?', (day['journal_seq'],)).fetchone()[0] == day['journal_head']
        counts = dict(con.execute('select kind,count(*) from watch_events where seq<=? group by kind', (day['journal_seq'],)))
        assert counts['scheduler_completed'] == day['scheduler_completed'] == 241
        assert counts['scheduler_failed'] == day['scheduler_failed'] == 21
        receipts = [json.loads(x[0]) for x in con.execute("select payload from watch_events where seq<=? and kind='source_receipt'", (day['journal_seq'],))]
        for source, expected in day['sources'].items():
            subset = [r for r in receipts if r['source'] == source]
            assert dict(Counter(r['outcome'] for r in subset)) == expected['outcomes']
            assert sum(bool(r.get('capture')) for r in subset) == expected['captures']
            assert sum(r.get('admitted_count') or 0 for r in subset) == expected['admitted_occurrences']
        for original in cohort['rows']:
            payload = json.loads(con.execute('select payload from watch_events where seq=?', (original['event_seq'],)).fetchone()[0])
            assert original['record'] in payload['records']
    finally:
        con.close()
    elapsed = (datetime.fromisoformat(day['last_completed_at']) - datetime.fromisoformat(day['first_completed_at'])).total_seconds()
    assert elapsed == day['recorded_elapsed_seconds'] and elapsed >= 86400
    validation = read(ROOT / 'research/invariant_core/validation.json')
    for name in ['code/invariant_core.py', 'tests/test_invariant_core.py']:
        check_hash(ROOT / name, validation['files'][name])
    print('Verified original-source/extract hashes and external measurement artifacts.')
    print('96 records: PCR2015 9; PA2023 0; UNDETERMINED 87. Parent FTS matches 6; corresponding award matches 0.')
    print('First-day journal recount: 241 completed, 21 failed; source outcomes and appearances match retained report.')
    print('Core and core tests unchanged from the previously measured backend run. No legal rule executed.')


if __name__ == '__main__':
    main()
