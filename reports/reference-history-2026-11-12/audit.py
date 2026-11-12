from pathlib import Path
from datetime import datetime, timezone
import sys, json, hashlib, sqlite3, random, subprocess
import numpy as np
root=Path('/Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/sunlight-eval-c515bd8')
out=Path('/Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/outputs/eval001')
db=Path('/Users/rimodg/brain/SUNLIGHT/data/sunlight.db')
cases=root/'prosecuted_cases.json'
assert hashlib.file_digest(db.open('rb'),'sha256').hexdigest()=='d90c30354df7a5c5ffe912d3fff095d6387ae5a568a38975853cd778d7aeeb8e'
assert hashlib.file_digest(cases.open('rb'),'sha256').hexdigest()=='f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f'
sys.path.insert(0,str(root/'code'))
import evaluation as ev
import doj_validation as doj
archived=json.loads((root/'reports/evaluation_report.json').read_text())
archived_doj=json.loads((root/'reports/validation_report.json').read_text())
cache=doj.build_agency_cache(str(db))
def sample():
 np.random.seed(42);random.seed(42)
 return [r['contract_id'] for r in doj.get_clean_contracts(str(db),cache,n=200)]
a,b=sample(),sample()
summary={'started_at':datetime.now(timezone.utc).isoformat(),'historical_commit':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'historical_environment_recreated':False,'runtime':'Current locked CPython 3.12.14; historical dependencies were not recorded in these reports.','sampling_probe':{'same_seed':42,'draw_sizes':[len(a),len(b)],'same_draw':a==b,'set_overlap':len(set(a)&set(b)),'draw_sha256':[hashlib.sha256(json.dumps(x).encode()).hexdigest() for x in [a,b]]}}
print(json.dumps(summary['sampling_probe']),flush=True)
ids=[r['id'] for r in archived['case_details'] if r['source']=='clean_sample']
assert len(ids)==200 and len(set(ids))==200
con=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)
qualifying=con.execute('''WITH agency_medians AS (SELECT agency_name, AVG(award_amount) med_amount FROM contracts WHERE award_amount>0 GROUP BY agency_name HAVING COUNT(*)>=10) SELECT c.contract_id,c.award_amount,c.vendor_name,c.agency_name,c.description FROM contracts c JOIN agency_medians am ON c.agency_name=am.agency_name WHERE c.award_amount<am.med_amount AND c.award_amount>100000''').fetchall()
by_id={}
for row in qualifying:by_id.setdefault(row[0],[]).append(row)
fixed=[]
for cid in ids:
 rows=by_id.get(cid,[])
 assert len(rows)==1,(cid,len(rows))
 cid,amount,vendor,agency,desc=rows[0]
 fixed.append({'contract_id':cid,'award_amount':amount,'vendor_name':vendor,'agency_name':agency,'description':desc,'is_sole_source':False,'has_donations':False,'comparables':doj.select_comparables_from_cache(cid,agency,amount,cache)})
con.close()
def archived_draw(db_path,agency_cache,n):
 assert n==200
 return fixed
ev.get_clean_contracts=archived_draw
result=ev.run_full_evaluation(str(db),str(cases),run_seed=42,n_bootstrap=1000,n_clean=200,calibration_profile='doj_federal')
ev.write_evaluation_report_json(result,str(out/'archived-sample-replay.json'))
result=json.loads((out/'archived-sample-replay.json').read_text())
summary['general_archived_sample_replay']={'sample_rows_found_in_verified_database':len(fixed),'sampling_intervention':'Only sample selection replaced with the 200 IDs retained in the archived report, in archived order; all values and comparables read from verified current database. Historical scoring code unchanged.','case_details_equal':result['case_details']==archived['case_details'],'classification_metrics_equal':result['classification_metrics']==archived['classification_metrics'],'confusion_matrix_equal':result['confusion_matrix']==archived['confusion_matrix'],'pr_curve_equal':result['pr_curve']==archived['pr_curve'],'threshold_sweep_equal':result['threshold_sweep']==archived['threshold_sweep'],'confidence_intervals_equal':result['confidence_intervals_95pct']==archived['confidence_intervals_95pct']}
print(json.dumps(summary['general_archived_sample_replay']),flush=True)
positive=doj.run_validation(str(db),str(cases),run_seed=42,n_bootstrap=1000,n_clean=0)
summary['doj_positive_diagnostic']={'positive_case_details_equal':positive['doj_case_details']==archived_doj['doj_case_details'],'case_count':len(positive['doj_case_details']),'negative_draw_retained_in_archive':False,'qualification':'Diagnostic with zero negative comparisons, not a replay of the archived full DOJ result; exact negative draw cannot be recovered from that report.'}
summary['inputs_unchanged']=hashlib.file_digest(db.open('rb'),'sha256').hexdigest()=='d90c30354df7a5c5ffe912d3fff095d6387ae5a568a38975853cd778d7aeeb8e'
summary['finished_at']=datetime.now(timezone.utc).isoformat()
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary['doj_positive_diagnostic']),flush=True)
