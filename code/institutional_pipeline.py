"""
SUNLIGHT Institutional Two-Pass Pipeline (Optimized)
"""
import sqlite3
import numpy as np
import hashlib
import json
import os
import time
import traceback
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from institutional_statistical_rigor import (
    BootstrapAnalyzer, BayesianFraudPrior, MultipleTestingCorrection,
    DOJProsecutionThresholds, FraudTier,
)
from sunlight_logging import get_logger
from calibration_config import get_profile, get_prior_for_context, get_tier_thresholds, get_fdr_params

logger = get_logger("pipeline")

def derive_contract_seed(run_seed, contract_id):
    return int(hashlib.sha256(f"{run_seed}:{contract_id}".encode()).hexdigest()[:8], 16)

def compute_dataset_hash(contracts):
    pairs = sorted((c['contract_id'], c.get('raw_data_hash', '')) for c in contracts)
    return hashlib.sha256(json.dumps(pairs, sort_keys=True, separators=(',',':')).encode()).hexdigest()

def compute_config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',',':')).encode()).hexdigest()

def _get_size_bin(amount):
    if amount <= 0: return 0
    return int(np.log10(amount))

def _is_defense(agency):
    lower = (agency or '').lower()
    return any(x in lower for x in ['defense','dod','army','navy','air force'])

def _is_it(desc):
    lower = (desc or '').lower()
    return any(x in lower for x in ['it ','technology','software','computer'])

def select_comparables_from_cache(contract_id, agency, amount, agency_cache):
    amounts = agency_cache.get(agency, [])
    # Exclude self
    amounts = [a for cid, a in amounts if cid != contract_id]
    if not amounts: return []
    target_bin = _get_size_bin(amount)
    similar = [a for a in amounts if abs(_get_size_bin(a) - target_bin) <= 1]
    if len(similar) < 5:
        similar = [a for a in amounts if 0.1 * amount <= a <= 10 * amount]
    return similar

def score_contract(contract, seed, config, bootstrap_analyzer, calibration_profile=None):
    np.random.seed(seed)
    comparables = contract.get('comparables', [])
    amount = contract['award_amount']
    confidence_level = config.get('confidence_level', 0.95)
    min_comparables = config.get('min_comparables', 3)
    insufficient = len(comparables) < min_comparables
    result = {'contract_id': contract['contract_id'], 'insufficient_comparables': insufficient, 'comparable_count': len(comparables)}
    if insufficient:
        logger.debug("Insufficient comparables",
            extra={"contract_id": contract['contract_id'], "comparable_count": len(comparables),
                   "min_required": min_comparables, "decision": "GRAY"})
        result.update({'selection_params_json': json.dumps({'agency': contract.get('agency_name',''), 'reason': 'insufficient'}),
            'raw_pvalue': None, 'markup_pct': None, 'markup_ci_lower': None, 'markup_ci_upper': None,
            'raw_zscore': None, 'log_zscore': None, 'bootstrap_percentile': None,
            'percentile_ci_lower': None, 'percentile_ci_upper': None,
            'bayesian_prior': None, 'bayesian_likelihood_ratio': None, 'bayesian_posterior': None})
        return result

    comp_array = np.array(comparables)
    result['selection_params_json'] = json.dumps({'agency': contract.get('agency_name',''), 'size_bin': _get_size_bin(amount), 'n': len(comparables)})

    mean_p = np.mean(comp_array); std_p = np.std(comp_array, ddof=1)
    raw_zscore = (amount - mean_p) / std_p if std_p > 0 else 0.0
    log_comp = np.log1p(comp_array); log_t = np.log1p(amount)
    log_m = np.mean(log_comp); log_s = np.std(log_comp, ddof=1)
    log_zscore = (log_t - log_m) / log_s if log_s > 0 else 0.0
    median_p = np.median(comp_array)
    markup_pct = ((amount - median_p) / median_p) * 100 if median_p > 0 else 0.0

    # Reseed after BootstrapAnalyzer init (which sets seed=42 internally)
    np.random.seed(seed)
    markup_r = bootstrap_analyzer.markup_confidence_interval(amount, comparables, confidence_level)
    np.random.seed(seed + 1)
    pct_r = bootstrap_analyzer.percentile_confidence_interval(amount, comparables, confidence_level)

    result.update({
        'raw_pvalue': float(markup_r.p_value), 'markup_pct': round(float(markup_pct), 2),
        'markup_ci_lower': float(markup_r.ci_lower), 'markup_ci_upper': float(markup_r.ci_upper),
        'raw_zscore': round(float(raw_zscore), 4), 'log_zscore': round(float(log_zscore), 4),
        'bootstrap_percentile': float(pct_r.point_estimate),
        'percentile_ci_lower': float(pct_r.ci_lower), 'percentile_ci_upper': float(pct_r.ci_upper),
    })

    bayesian = BayesianFraudPrior()
    if calibration_profile is not None:
        profile_base = get_prior_for_context(calibration_profile)
        bayesian.BASE_RATES = {**BayesianFraudPrior.BASE_RATES, 'overall': profile_base}
    chars = {'is_mega_contract': amount > 25e6, 'is_defense': _is_defense(contract.get('agency_name','')),
        'is_it_services': _is_it(contract.get('description','')), 'is_sole_source': contract.get('is_sole_source', False),
        'has_political_donations': contract.get('has_donations', False)}
    br = bayesian.calculate_posterior(100 - markup_r.p_value * 100, chars)
    result.update({'bayesian_prior': float(br.prior_probability), 'bayesian_likelihood_ratio': float(br.likelihood_ratio), 'bayesian_posterior': float(br.posterior_probability)})
    return result

def assign_tier(score, fdr_adj, survives_fdr, thresholds=None):
    if thresholds is None:
        thresholds = {'red': 0.72, 'yellow': 0.38, 'min_typ_red': 2, 'min_ci_yellow': 66}
    if score['insufficient_comparables']: return 'GRAY', 9999
    ci = score.get('markup_ci_lower',0) or 0
    post = score.get('bayesian_posterior',0) or 0
    pci = score.get('percentile_ci_lower',0) or 0
    red_post = thresholds['red']
    yellow_post = thresholds['yellow']
    min_ci_yellow = thresholds.get('min_ci_yellow', 65)
    f = []
    if ci > 300: f.append(95)
    elif ci > 200: f.append(85)
    elif ci > 150: f.append(75)
    elif ci > 100: f.append(65)
    elif ci > 75: f.append(55)
    if pci > 95: f.append(90)
    elif pci > 90: f.append(80)
    if post > red_post: f.append(90)
    elif post > yellow_post: f.append(75)
    if not f:
        logger.debug("No evidence signals", extra={"contract_id": score.get('contract_id'), "decision": "GREEN"})
        return 'GREEN', 5000
    avg = int(np.mean(f))
    if ci > 300:
        tier = 'RED'
    elif avg >= 90 and survives_fdr:
        tier = 'RED'
    elif avg >= 70 and ci > min_ci_yellow:
        tier = 'YELLOW'
    elif score['comparable_count'] < 5:
        tier = 'GRAY'
    else:
        tier = 'GREEN'
    priority = 100 - avg if tier == 'RED' else (200 - avg if tier == 'YELLOW' else (9000 if tier == 'GRAY' else 5000))
    cid = score.get('contract_id')
    if tier in ('RED', 'YELLOW'):
        logger.info("Fraud signal detected",
            extra={"contract_id": cid, "decision": tier,
                   "confidence_avg": avg, "markup_ci_lower": ci,
                   "bayesian_posterior": round(post, 4),
                   "percentile_ci_lower": pci, "survives_fdr": survives_fdr,
                   "evidence_factors": f})
    else:
        logger.debug("Tier assigned",
            extra={"contract_id": cid, "decision": tier, "confidence_avg": avg})
    return tier, priority

def append_audit_entry(db_path, action, details, run_id=None):
    conn = sqlite3.connect(db_path); c = conn.cursor()
    c.execute("SELECT MAX(sequence_number) FROM audit_log")
    seq = (c.fetchone()[0] or 0) + 1
    prev_hash = '0'*64
    if seq > 1:
        from sql_allowlist import validate_column
        for col in ['entry_hash','current_log_hash']:
            try:
                c.execute(f"SELECT {validate_column(col)} FROM audit_log WHERE sequence_number=?", (seq-1,))
                r = c.fetchone()
                if r and r[0]: prev_hash = r[0]; break
            except: continue
    ts = datetime.now(timezone.utc).isoformat()
    lid = hashlib.sha256(f"{seq}:{ts}".encode()).hexdigest()[:16]
    payload = json.dumps({'sequence':seq,'timestamp':ts,'action':action,'run_id':run_id,'details':details,'previous_hash':prev_hash}, sort_keys=True, separators=(',',':'))
    eh = hashlib.sha256(payload.encode()).hexdigest()
    c.execute("INSERT INTO audit_log (log_id,sequence_number,timestamp,action_type,entity_id,previous_log_hash,current_log_hash,action,run_id,details,previous_hash,entry_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (lid,seq,ts,action,run_id,prev_hash,eh,action,run_id,json.dumps(details),prev_hash,eh))
    conn.commit(); conn.close()
    logger.debug("Audit entry appended",
        extra={"action": action, "run_id": run_id, "sequence": seq, "entry_hash": eh[:16]})
    return eh

def verify_audit_chain(db_path):
    conn = sqlite3.connect(db_path); c = conn.cursor()
    try: c.execute("SELECT sequence_number,timestamp,action,run_id,details,previous_hash,entry_hash FROM audit_log ORDER BY sequence_number")
    except: c.execute("SELECT sequence_number,timestamp,action_type,entity_id,'{}',previous_log_hash,current_log_hash FROM audit_log ORDER BY sequence_number")
    rows = c.fetchall(); conn.close()
    if not rows: return True, "Empty (valid)"
    exp = '0'*64
    for r in rows:
        seq,ts,act,rid,det,ph,sh = r
        if ph != exp: return False, f"Chain broken at {seq}"
        d = json.loads(det) if isinstance(det,str) else det
        p = json.dumps({'sequence':seq,'timestamp':ts,'action':act,'run_id':rid,'details':d,'previous_hash':ph}, sort_keys=True, separators=(',',':'))
        if hashlib.sha256(p.encode()).hexdigest() != sh: return False, f"Hash mismatch at {seq}"
        exp = sh
    return True, f"Valid ({len(rows)} entries)"

class InstitutionalPipeline:
    DEFAULT_CONFIG = {'n_bootstrap':1000,'confidence_level':0.95,'min_comparables':3,'fdr_alpha':0.10,'min_amount':0,'version':'2.0.0'}

    def __init__(self, db_path):
        self.db_path = db_path

    def run(self, run_seed=42, config=None, limit=None, verbose=True, calibration_profile="doj_federal"):
        caller_config = config or {}
        config = {**self.DEFAULT_CONFIG, **caller_config}
        # Load calibration profile and apply its FDR alpha unless caller explicitly set one
        cal_profile = get_profile(calibration_profile) if isinstance(calibration_profile, str) else calibration_profile
        fdr_params = get_fdr_params(cal_profile)
        if 'fdr_alpha' not in caller_config:
            config['fdr_alpha'] = fdr_params['alpha']
        tier_thresholds = get_tier_thresholds(cal_profile)
        config_hash = compute_config_hash({**config, 'calibration_profile': cal_profile.name})
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{run_seed}"
        logger.info("Pipeline starting",
            extra={"run_id": run_id, "run_seed": run_seed, "n_bootstrap": config['n_bootstrap'],
                   "fdr_alpha": config['fdr_alpha'], "calibration_profile": cal_profile.name,
                   "config_hash": config_hash[:16]})

        # Preload ALL contract amounts by agency (one query, not 1000)
        agency_cache = self._build_agency_cache()
        logger.info("Agency cache built", extra={"run_id": run_id, "n_agencies": len(agency_cache)})

        contracts = self._load_contracts(config['min_amount'], limit)
        dataset_hash = compute_dataset_hash(contracts)
        logger.info("Contracts loaded",
            extra={"run_id": run_id, "n_contracts": len(contracts),
                   "dataset_hash": dataset_hash[:16], "min_amount": config['min_amount']})

        self._create_run_record(run_id, run_seed, config, config_hash, dataset_hash, len(contracts))
        append_audit_entry(self.db_path, 'RUN_STARTED', {'run_id':run_id,'n':len(contracts),'config_hash':config_hash,'dataset_hash':dataset_hash}, run_id)

        # Create ONE bootstrap analyzer (reused across all contracts)
        ba = BootstrapAnalyzer(n_iterations=config['n_bootstrap'])

        logger.info("Pass 1: Scoring contracts", extra={"run_id": run_id, "n_contracts": len(contracts)})
        scores, errors = [], []
        t0 = time.time()
        for i, con in enumerate(contracts):
            if (i+1) % 100 == 0:
                el = time.time()-t0; rate = (i+1)/el
                logger.info("Scoring progress",
                    extra={"run_id": run_id, "scored": i+1, "total": len(contracts),
                           "rate_per_sec": round(rate, 1), "eta_sec": round((len(contracts)-i-1)/rate)})
            try:
                cseed = derive_contract_seed(run_seed, con['contract_id'])
                con['comparables'] = select_comparables_from_cache(con['contract_id'], con['agency_name'], con['award_amount'], agency_cache)
                scores.append(score_contract(con, cseed, config, ba, calibration_profile=cal_profile))
            except Exception as e:
                logger.error("Contract scoring failed",
                    extra={"run_id": run_id, "contract_id": con['contract_id'], "error": str(e)})
                errors.append({'contract_id': con['contract_id'], 'error': str(e)})
        p1t = time.time()-t0
        logger.info("Pass 1 complete",
            extra={"run_id": run_id, "n_scored": len(scores), "n_errors": len(errors),
                   "elapsed_sec": round(p1t, 1), "rate_per_sec": round(len(scores)/p1t, 1) if p1t > 0 else 0})

        logger.info("Pass 2: FDR correction", extra={"run_id": run_id})
        scorable = [s for s in scores if not s['insufficient_comparables']]
        raw_pv = [s['raw_pvalue'] for s in scorable]
        if len(raw_pv) > 1:
            surv, adj = MultipleTestingCorrection.benjamini_hochberg(raw_pv, alpha=config['fdr_alpha'])
        else:
            surv, adj = [False]*len(raw_pv), raw_pv[:]
        fi = 0
        for s in scores:
            if s['insufficient_comparables']:
                s.update({'fdr_adjusted_pvalue':None,'survives_fdr':False,'tier':'GRAY','triage_priority':9999})
            else:
                s['fdr_adjusted_pvalue']=float(adj[fi]); s['survives_fdr']=bool(surv[fi])
                s['tier'], s['triage_priority'] = assign_tier(s, adj[fi], surv[fi], thresholds=tier_thresholds); fi+=1

        logger.info("Persisting scores", extra={"run_id": run_id, "n_scores": len(scores)})
        self._persist_scores(run_id, scores)
        tc = {}
        for s in scores: tc[s['tier']] = tc.get(s['tier'],0)+1
        self._finalize_run(run_id, len(scores), len(errors), tc, p1t)
        append_audit_entry(self.db_path, 'RUN_COMPLETED', {'run_id':run_id,'scored':len(scores),'tiers':tc}, run_id)

        # Extended summary
        ci_widths = [s['markup_ci_upper']-s['markup_ci_lower'] for s in scores if s.get('markup_ci_upper') is not None and s.get('markup_ci_lower') is not None]
        n_fdr_tests = len(scorable)
        n_fdr_sig = sum(1 for s in scores if s.get('survives_fdr'))

        logger.info("Pipeline complete",
            extra={"run_id": run_id, "tier_RED": tc.get('RED', 0), "tier_YELLOW": tc.get('YELLOW', 0),
                   "tier_GREEN": tc.get('GREEN', 0), "tier_GRAY": tc.get('GRAY', 0),
                   "pct_gray": round(tc.get('GRAY', 0)/len(scores)*100, 1) if scores else 0,
                   "median_ci_width": round(float(np.median(ci_widths)), 1) if ci_widths else None,
                   "fdr_tests": n_fdr_tests, "fdr_significant": n_fdr_sig,
                   "elapsed_sec": round(p1t, 1),
                   "rate_per_sec": round(len(scores)/p1t, 1) if p1t > 0 else 0})
        return {'run_id':run_id,'run_seed':run_seed,'config_hash':config_hash,'dataset_hash':dataset_hash,
            'n_contracts':len(contracts),'n_scored':len(scores),'n_errors':len(errors),'tier_counts':tc,'pass1_time':round(p1t,1)}

    def _build_agency_cache(self):
        conn = sqlite3.connect(self.db_path); c = conn.cursor()
        c.execute("SELECT contract_id, agency_name, award_amount FROM contracts WHERE award_amount > 0")
        cache = {}
        for cid, agency, amt in c.fetchall():
            if agency not in cache: cache[agency] = []
            cache[agency].append((cid, amt))
        conn.close()
        return cache

    def _load_contracts(self, min_amount, limit=None):
        conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row; c = conn.cursor()
        q = "SELECT contract_id,award_amount,vendor_name,agency_name,description,raw_data_hash FROM contracts WHERE award_amount>? ORDER BY contract_id"
        p = [min_amount]
        if limit: q += " LIMIT ?"; p.append(limit)
        c.execute(q, p)
        contracts = []
        for row in c.fetchall():
            r = dict(row)
            c.execute("SELECT SUM(amount) FROM political_donations WHERE vendor_name=?", (r['vendor_name'],))
            d = c.fetchone()
            r['has_donations'] = d[0] is not None and d[0] > 0
            r['donation_amount'] = d[0] or 0
            contracts.append(r)
        conn.close()
        return contracts

    def _create_run_record(self, run_id, seed, config, chash, dhash, n):
        conn = sqlite3.connect(self.db_path); c = conn.cursor()
        c.execute("INSERT INTO analysis_runs (run_id,started_at,status,run_seed,config_json,config_hash,dataset_hash,contracts_analyzed,n_contracts,code_commit_hash,environment_json,model_version) VALUES (?,?,'RUNNING',?,?,?,?,?,?,?,?,?)",
            (run_id, datetime.now(timezone.utc).isoformat(), seed, json.dumps(config), chash, dhash, n, n, self._code_hash(), json.dumps({'np':np.__version__}), config.get('version','')))
        conn.commit(); conn.close()

    def _finalize_run(self, run_id, scored, errs, tc, elapsed):
        conn = sqlite3.connect(self.db_path); c = conn.cursor()
        c.execute("UPDATE analysis_runs SET status='COMPLETED',completed_at=?,n_scored=?,n_errors=?,summary_json=?,fdr_n_tests=?,fdr_n_significant=? WHERE run_id=?",
            (datetime.now(timezone.utc).isoformat(), scored, errs, json.dumps({'tiers':tc,'sec':round(elapsed,1)}), scored-tc.get('GRAY',0), tc.get('RED',0)+tc.get('YELLOW',0), run_id))
        conn.commit(); conn.close()

    def _persist_scores(self, run_id, scores):
        conn = sqlite3.connect(self.db_path); c = conn.cursor()
        for s in scores:
            sid = hashlib.sha256(f"{run_id}:{s['contract_id']}".encode()).hexdigest()[:16]
            post = s.get('bayesian_posterior') or 0; mci = s.get('markup_ci_lower') or 0
            conf = max(0, min(100, int(post*50 + min(mci/10, 50))))
            c.execute("INSERT OR REPLACE INTO contract_scores (score_id,contract_id,run_id,fraud_tier,tier,triage_priority,confidence_score,raw_pvalue,fdr_adjusted_pvalue,survives_fdr,markup_pct,markup_ci_lower,markup_ci_upper,raw_zscore,log_zscore,bootstrap_percentile,percentile_ci_lower,percentile_ci_upper,bayesian_prior,bayesian_likelihood_ratio,bayesian_posterior,comparable_count,insufficient_comparables,selection_params_json,scored_at,analyzed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid,s['contract_id'],run_id,s['tier'],s['tier'],s['triage_priority'],conf,s.get('raw_pvalue'),s.get('fdr_adjusted_pvalue'),1 if s.get('survives_fdr') else 0,s.get('markup_pct'),s.get('markup_ci_lower'),s.get('markup_ci_upper'),s.get('raw_zscore'),s.get('log_zscore'),s.get('bootstrap_percentile'),s.get('percentile_ci_lower'),s.get('percentile_ci_upper'),s.get('bayesian_prior'),s.get('bayesian_likelihood_ratio'),s.get('bayesian_posterior'),s['comparable_count'],1 if s['insufficient_comparables'] else 0,s.get('selection_params_json'),datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
        conn.commit(); conn.close()

    def _code_hash(self):
        try: return hashlib.sha256(open(__file__,'r').read().encode()).hexdigest()[:16]
        except: return 'unknown'

class InstitutionalVerification:
    def __init__(self, db_path): self.db_path = db_path

    def verify_run(self, run_id, verbose=True):
        results = {}
        if verbose: print("="*70); print(f"VERIFICATION: {run_id}"); print("="*70)
        for name, fn in [('FDR', self.verify_fdr), ('Dataset', self.verify_dataset), ('Audit', lambda: verify_audit_chain(self.db_path)), ('Complete', self.verify_complete)]:
            if name == 'Audit': ok, msg = fn()
            else: ok, msg = fn(run_id)
            results[name] = {'passed':ok,'msg':msg}
            if verbose: print(f"  {name:10s} {'PASS' if ok else 'FAIL'} - {msg}")
        results['all_passed'] = all(r['passed'] for r in results.values())
        if verbose: print(f"\n  {'ALL GATES PASSED' if results['all_passed'] else 'SOME GATES FAILED'}"); print("="*70)
        return results

    def verify_fdr(self, run_id):
        conn = sqlite3.connect(self.db_path); c = conn.cursor()
        c.execute("SELECT contract_id,raw_pvalue,fdr_adjusted_pvalue,survives_fdr FROM contract_scores WHERE run_id=? AND insufficient_comparables=0 AND raw_pvalue IS NOT NULL ORDER BY contract_id", (run_id,))
        rows = c.fetchall(); conn.close()
        if not rows: return False, "No scores"
        rp = [r[1] for r in rows]; sa = [r[2] for r in rows]; ss = [r[3] for r in rows]
        rs, ra = MultipleTestingCorrection.benjamini_hochberg(rp, alpha=0.10)
        mm = sum(1 for i in range(len(rows)) if abs((ra[i] or 0)-(sa[i] or 0)) > 1e-6 or bool(rs[i])!=bool(ss[i]))
        return (True, f"Verified ({len(rows)} scores)") if mm==0 else (False, f"{mm} mismatches")

    def verify_dataset(self, run_id):
        conn = sqlite3.connect(self.db_path); c = conn.cursor()
        try: c.execute("SELECT dataset_hash,n_contracts FROM analysis_runs WHERE run_id=?", (run_id,))
        except: c.execute("SELECT dataset_hash,contracts_analyzed FROM analysis_runs WHERE run_id=?", (run_id,))
        rr = c.fetchone()
        if not rr: conn.close(); return False, "Run not found"
        sh, en = rr
        c.execute("SELECT cs.contract_id,co.raw_data_hash FROM contract_scores cs JOIN contracts co ON cs.contract_id=co.contract_id WHERE cs.run_id=?", (run_id,))
        rows = c.fetchall(); conn.close()
        if len(rows) != en: return False, f"Count: expected {en}, got {len(rows)}"
        rc = compute_dataset_hash([{'contract_id':r[0],'raw_data_hash':r[1]} for r in rows])
        return (True, f"Hash matches ({len(rows)})") if rc==sh else (False, "Hash mismatch")

    def verify_complete(self, run_id):
        conn = sqlite3.connect(self.db_path); c = conn.cursor()
        try: c.execute("SELECT n_contracts FROM analysis_runs WHERE run_id=?", (run_id,))
        except: c.execute("SELECT contracts_analyzed FROM analysis_runs WHERE run_id=?", (run_id,))
        rr = c.fetchone()
        if not rr: conn.close(); return False, "Not found"
        c.execute("SELECT COUNT(*) FROM contract_scores WHERE run_id=?", (run_id,))
        a = c.fetchone()[0]; conn.close()
        return (True, f"All {a} scored") if a==rr[0] else (False, f"Expected {rr[0]}, got {a}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/sunlight.db')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--verify', type=str, default=None)
    parser.add_argument('--bootstrap', type=int, default=1000)
    parser.add_argument('--profile', type=str, default='doj_federal', help='Calibration profile name')
    args = parser.parse_args()
    db = args.db
    if not os.path.exists(db): db = '../data/sunlight.db'
    if not os.path.exists(db): print("ERROR: No DB"); exit(1)
    if args.verify:
        InstitutionalVerification(db).verify_run(args.verify)
    else:
        result = InstitutionalPipeline(db).run(run_seed=args.seed, config={'n_bootstrap':args.bootstrap}, limit=args.limit, calibration_profile=args.profile)
        print()
        InstitutionalVerification(db).verify_run(result['run_id'])
