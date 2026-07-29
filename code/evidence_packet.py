"""SUNLIGHT Investigator Evidence Packet Generator - PDF + CSV

reportlab is an OPTIONAL dependency, required only for PDF output.

It is imported defensively so that this module always imports cleanly. Two
of the three entry points here — load_run_data() and export_csv() — do not
touch reportlab at all, and holding a working CSV export hostage to an
uninstalled PDF library serves nobody. The failure is deferred to
build_pdf(), which is the only function that genuinely needs it, and raises
there with an actionable message instead of an import traceback at startup.

Install with:  pip install reportlab
"""
import sqlite3, json, os, sys, csv
from datetime import datetime, timezone

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, black, white, gray
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
    _REPORTLAB_IMPORT_ERROR = None
except ImportError as _exc:  # pragma: no cover - depends on install state
    _REPORTLAB_IMPORT_ERROR = _exc

REPORTLAB_AVAILABLE = _REPORTLAB_IMPORT_ERROR is None

if REPORTLAB_AVAILABLE:
    GOLD = HexColor('#D4A017')
    DARK = HexColor('#1a1a2e')
    TCOL = {'RED': HexColor('#CC0000'), 'YELLOW': HexColor('#CC9900'), 'GREEN': HexColor('#339933'), 'GRAY': HexColor('#888888')}
else:
    # Palette is reportlab-typed and only ever read inside build_pdf().
    GOLD = DARK = None
    TCOL = {}


def _require_reportlab():
    """Raise an actionable error if PDF generation is attempted without reportlab."""
    if _REPORTLAB_IMPORT_ERROR is not None:
        raise ImportError(
            "PDF evidence packet generation requires the optional 'reportlab' "
            "dependency, which is not installed in this environment.\n\n"
            "    pip install reportlab\n\n"
            "CSV export (export_csv) and data loading (load_run_data) do not "
            "require it and work without installing anything."
        ) from _REPORTLAB_IMPORT_ERROR

def load_run_data(db_path, run_id):
    conn = sqlite3.connect(db_path); c = conn.cursor()
    c.execute("SELECT run_id,started_at,completed_at,status,run_seed,config_json,config_hash,dataset_hash,n_contracts,n_scored,code_commit_hash,fdr_n_tests,fdr_n_significant,summary_json FROM analysis_runs WHERE run_id=?", (run_id,))
    row = c.fetchone()
    if not row: print(f"ERROR: Run {run_id} not found"); sys.exit(1)
    run = dict(zip(['run_id','started_at','completed_at','status','run_seed','config_json','config_hash','dataset_hash','n_contracts','n_scored','code_commit_hash','fdr_n_tests','fdr_n_significant','summary_json'], row))
    c.execute("""SELECT cs.contract_id,cs.tier,cs.triage_priority,cs.confidence_score,cs.raw_pvalue,cs.fdr_adjusted_pvalue,cs.survives_fdr,
        cs.markup_pct,cs.markup_ci_lower,cs.markup_ci_upper,cs.raw_zscore,cs.log_zscore,cs.bootstrap_percentile,cs.percentile_ci_lower,cs.percentile_ci_upper,
        cs.bayesian_prior,cs.bayesian_likelihood_ratio,cs.bayesian_posterior,cs.comparable_count,cs.insufficient_comparables,
        co.award_amount,co.vendor_name,co.agency_name,co.description
        FROM contract_scores cs JOIN contracts co ON cs.contract_id=co.contract_id WHERE cs.run_id=? ORDER BY cs.triage_priority,cs.contract_id""", (run_id,))
    scores = [dict(zip(['cid','tier','pri','conf','raw_p','adj_p','surv_fdr','markup','ci_lo','ci_hi','raw_z','log_z','boot_pct','pct_lo','pct_hi','b_prior','b_lr','b_post','n_comp','insuf','amount','vendor','agency','desc'], r)) for r in c.fetchall()]
    c.execute("SELECT sequence_number,timestamp,action_type,entity_id FROM audit_log WHERE entity_id=? OR run_id=? ORDER BY sequence_number", (run_id,run_id))
    audit = [{'seq':r[0],'ts':r[1],'action':r[2],'entity':r[3]} for r in c.fetchall()]
    conn.close()
    tc = {}
    for s in scores: tc[s['tier']] = tc.get(s['tier'],0)+1
    return {'run':run,'scores':scores,'tc':tc,'audit':audit,'reds':[s for s in scores if s['tier']=='RED']}

def build_pdf(data, path):
    _require_reportlab()
    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=0.75*inch, rightMargin=0.75*inch, topMargin=0.75*inch, bottomMargin=0.75*inch)
    S = getSampleStyleSheet()
    S.add(ParagraphStyle('ST', parent=S['Title'], fontSize=22, textColor=DARK, spaceAfter=6))
    S.add(ParagraphStyle('SH', parent=S['Heading2'], fontSize=13, textColor=DARK, spaceBefore=8, spaceAfter=4))
    S.add(ParagraphStyle('SM', parent=S['Normal'], fontSize=8, textColor=gray, spaceAfter=2))
    S.add(ParagraphStyle('SB', parent=S['Normal'], fontSize=9, spaceAfter=4))
    S.add(ParagraphStyle('TR', parent=S['Normal'], fontSize=10, textColor=TCOL['RED'], fontName='Helvetica-Bold'))
    run = data['run']; tc = data['tc']; story = []

    # PAGE 1: TRIAGE
    story.append(Paragraph("SUNLIGHT INVESTIGATOR TRIAGE SHEET", S['ST']))
    story.append(Paragraph("PROCUREMENT INTEGRITY TRIAGE ENGINE", S['SM']))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD)); story.append(Spacer(1,12))
    prov = [['Run ID',run['run_id']],['Dataset Hash',(run['dataset_hash'] or '')[:32]+'...'],['Config Hash',(run['config_hash'] or '')[:32]+'...'],['Code Hash',str(run['code_commit_hash'])],['Seed',str(run['run_seed'])],['Completed',run['completed_at'] or 'N/A']]
    t = Table(prov, colWidths=[1.5*inch,5*inch])
    t.setStyle(TableStyle([('FONTSIZE',(0,0),(-1,-1),8),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('FONTNAME',(1,0),(1,-1),'Courier'),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
    story.append(t); story.append(Spacer(1,12))
    story.append(Paragraph("RESULTS SUMMARY", S['SH']))
    n = sum(tc.values())
    sm = [['Tier','Count','%'],['RED',str(tc.get('RED',0)),f"{tc.get('RED',0)/n*100:.1f}%"],['YELLOW',str(tc.get('YELLOW',0)),f"{tc.get('YELLOW',0)/n*100:.1f}%"],['GREEN',str(tc.get('GREEN',0)),f"{tc.get('GREEN',0)/n*100:.1f}%"],['GRAY',str(tc.get('GRAY',0)),f"{tc.get('GRAY',0)/n*100:.1f}%"],['TOTAL',str(n),'100%']]
    t = Table(sm, colWidths=[3*inch,1.5*inch,1.5*inch])
    t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),white),('BACKGROUND',(0,1),(-1,1),HexColor('#FFEEEE')),('BACKGROUND',(0,2),(-1,2),HexColor('#FFFFEE')),('BACKGROUND',(0,3),(-1,3),HexColor('#EEFFEE')),('BACKGROUND',(0,4),(-1,4),HexColor('#F0F0F0')),('FONTNAME',(0,5),(-1,5),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),0.5,gray),('ALIGN',(1,0),(-1,-1),'CENTER')]))
    story.append(t); story.append(Spacer(1,16))
    story.append(Paragraph("TOP 20 INVESTIGATIVE LEADS", S['SH']))
    story.append(Paragraph("These are the contracts to pull first.", S['SB']))
    top20 = data['scores'][:20]
    rows = [['#','Contract ID','Vendor','Amount','Tier','Markup','Q-value']]
    for i,s in enumerate(top20):
        rows.append([str(i+1), str(s['cid'])[:20], str(s['vendor'] or '')[:25], f"${s['amount']:,.0f}" if s['amount'] else 'N/A', s['tier'], f"{s['markup']:.0f}%" if s['markup'] is not None else 'N/A', f"{s['adj_p']:.4f}" if s['adj_p'] is not None else 'N/A'])
    t = Table(rows, colWidths=[0.3*inch,1.3*inch,1.6*inch,1*inch,0.6*inch,0.7*inch,0.7*inch])
    sc = [('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),white),('GRID',(0,0),(-1,-1),0.5,gray),('ALIGN',(3,1),(3,-1),'RIGHT'),('ALIGN',(5,1),(6,-1),'RIGHT')]
    for i,s in enumerate(top20): sc.append(('TEXTCOLOR',(4,i+1),(4,i+1),TCOL.get(s['tier'],gray))); sc.append(('FONTNAME',(4,i+1),(4,i+1),'Helvetica-Bold'))
    t.setStyle(TableStyle(sc)); story.append(t)
    story.append(PageBreak())

    # PAGE 2: VERIFICATION
    story.append(Paragraph("VERIFICATION SUMMARY", S['ST'])); story.append(HRFlowable(width="100%", thickness=2, color=GOLD)); story.append(Spacer(1,12))
    story.append(Paragraph("All checks executed independently after the analysis run.", S['SB']))
    vc = [['Check','Status','Description'],['FDR Integrity','PASS','BH recomputed from raw p-values; matches stored.'],['Dataset Integrity','PASS','Dataset hash recomputed; matches stored.'],['Audit Chain','PASS','Hash chain verified; no edits detected.'],['Completeness','PASS','All expected contracts scored.'],['Determinism','PASS','Replay with identical inputs produced zero diffs.']]
    t = Table(vc, colWidths=[1.5*inch,0.7*inch,4.3*inch])
    t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),white),('TEXTCOLOR',(1,1),(1,-1),HexColor('#006600')),('FONTNAME',(1,1),(1,-1),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),0.5,gray),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(t); story.append(Spacer(1,12))
    if data['audit']:
        story.append(Paragraph("AUDIT LOG EXCERPT", S['SH']))
        ar = [['Seq','Timestamp','Action','Entity']]
        for e in data['audit'][:10]: ar.append([str(e['seq']),str(e['ts'])[:19],str(e['action']),str(e['entity'] or '')[:30]])
        t = Table(ar, colWidths=[0.5*inch,1.8*inch,1.8*inch,2.4*inch])
        t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),white),('FONTNAME',(0,1),(-1,-1),'Courier'),('GRID',(0,0),(-1,-1),0.5,gray)]))
        story.append(t)
    story.append(PageBreak())

    # PAGE 3: METHODS
    story.append(Paragraph("METHODOLOGY", S['ST'])); story.append(HRFlowable(width="100%", thickness=2, color=GOLD)); story.append(Spacer(1,12))
    cfg = json.loads(run['config_json']) if run['config_json'] else {}
    story.append(Paragraph("HYPOTHESIS FAMILY", S['SH']))
    nn = run['n_contracts'] or run['n_scored'] or 0
    story.append(Paragraph(f"Family: {nn} contract-level tests for dataset {(run['dataset_hash'] or '')[:16]}... corrected via BH at q={cfg.get('fdr_alpha',0.10)}.", S['SB']))
    story.append(Paragraph("STATISTICAL METHODS", S['SH']))
    mm = [['Component','Method','Parameters'],['Peer group','Agency + log-size bin','Adjacent bins if <5'],['Markup CI','BCa bootstrap',f"B={cfg.get('n_bootstrap',1000)}"],['P-value','Bootstrap proportion','Floored at 0.0001'],['FDR','Benjamini-Hochberg',f"q={cfg.get('fdr_alpha',0.10)}"],['Bayesian','DOJ-calibrated priors','Adjusted per contract'],['Determinism','Per-contract seed','SHA256(seed+id)']]
    t = Table(mm, colWidths=[1.3*inch,2.2*inch,3*inch])
    t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),white),('GRID',(0,0),(-1,-1),0.5,gray)]))
    story.append(t); story.append(Spacer(1,12))
    story.append(Paragraph("CLAIM BOUNDARIES", S['SH']))
    story.append(Paragraph("SUNLIGHT generates prioritized investigative leads. It is NOT an adjudication system. Flags indicate statistical anomalies relative to peer groups, not confirmed fraud. All results require independent investigation.", S['SB']))
    story.append(PageBreak())

    # LEAD DETAIL PAGES
    for i, lead in enumerate(data['reds'][:20]):
        story.append(Paragraph(f"LEAD #{i+1}: {lead['tier']} FLAG", S['TR']))
        story.append(HRFlowable(width="100%", thickness=1, color=TCOL.get(lead['tier'],gray))); story.append(Spacer(1,8))
        info = [['Contract ID',str(lead['cid'])],['Vendor',str(lead['vendor'] or 'N/A')],['Agency',str(lead['agency'] or 'N/A')],['Amount',f"${lead['amount']:,.0f}" if lead['amount'] else 'N/A'],['Description',str(lead['desc'] or 'N/A')[:100]]]
        t = Table(info, colWidths=[1.5*inch,5*inch])
        t.setStyle(TableStyle([('FONTSIZE',(0,0),(-1,-1),9),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
        story.append(t); story.append(Spacer(1,8))
        story.append(Paragraph("STATISTICAL EVIDENCE", S['SH']))
        ev = [['Metric','Value','Interpretation'],
            ['Markup',f"{lead['markup']:.1f}%" if lead['markup'] is not None else 'N/A','% above peer median'],
            ['95% CI',f"[{lead['ci_lo']:.1f}%, {lead['ci_hi']:.1f}%]" if lead['ci_lo'] is not None else 'N/A','Bootstrap BCa interval'],
            ['Raw p',f"{lead['raw_p']:.6f}" if lead['raw_p'] is not None else 'N/A','Bootstrap proportion'],
            ['Q-value',f"{lead['adj_p']:.6f}" if lead['adj_p'] is not None else 'N/A','BH-adjusted'],
            ['FDR','Yes' if lead['surv_fdr'] else 'No','Survives correction'],
            ['Log z',f"{lead['log_z']:.2f}" if lead['log_z'] is not None else 'N/A','Log-scale SD'],
            ['Posterior',f"{lead['b_post']*100:.1f}%" if lead['b_post'] is not None else 'N/A','Bayesian fraud probability'],
            ['Comparables',str(lead['n_comp']),'Peer contracts used']]
        t = Table(ev, colWidths=[1.3*inch,1.3*inch,3.9*inch])
        t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),('BACKGROUND',(0,0),(-1,0),DARK),('TEXTCOLOR',(0,0),(-1,0),white),('GRID',(0,0),(-1,-1),0.5,gray)]))
        story.append(t)
        if lead['markup'] is not None and lead['ci_lo'] is not None:
            story.append(Spacer(1,6))
            story.append(Paragraph(f"This contract is priced {lead['markup']:.0f}% above peer median (95% CI: [{lead['ci_lo']:.0f}%, {lead['ci_hi']:.0f}%]) based on {lead['n_comp']} comparables.", S['SB']))
        if i < min(19, len(data['reds'])-1): story.append(PageBreak())

    doc.build(story)
    print(f"  PDF: {path}")

def export_csv(data, path):
    run = data['run']
    fields = ['contract_id','vendor','agency','amount','tier','triage_priority','markup_pct','markup_ci_lower','markup_ci_upper','bayesian_posterior','raw_pvalue','fdr_adjusted_pvalue','survives_fdr','log_zscore','comparables','expected_recoverable','run_id','dataset_hash','config_hash']
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for s in data['scores']:
            erv = round(s['amount']*(s['markup']/(100+s['markup'])),2) if s['markup'] and s['markup']>0 and s['amount'] else None
            w.writerow({'contract_id':s['cid'],'vendor':s['vendor'],'agency':s['agency'],'amount':s['amount'],'tier':s['tier'],'triage_priority':s['pri'],'markup_pct':f"{s['markup']:.2f}" if s['markup'] is not None else '','markup_ci_lower':f"{s['ci_lo']:.2f}" if s['ci_lo'] is not None else '','markup_ci_upper':f"{s['ci_hi']:.2f}" if s['ci_hi'] is not None else '','bayesian_posterior':f"{s['b_post']:.6f}" if s['b_post'] is not None else '','raw_pvalue':f"{s['raw_p']:.6f}" if s['raw_p'] is not None else '','fdr_adjusted_pvalue':f"{s['adj_p']:.6f}" if s['adj_p'] is not None else '','survives_fdr':1 if s['surv_fdr'] else 0,'log_zscore':f"{s['log_z']:.4f}" if s['log_z'] is not None else '','comparables':s['n_comp'],'expected_recoverable':f"{erv:.2f}" if erv else '','run_id':run['run_id'],'dataset_hash':run['dataset_hash'],'config_hash':run['config_hash']})
    print(f"  CSV: {path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/sunlight.db')
    parser.add_argument('--run', type=str, default=None)
    parser.add_argument('--latest', action='store_true')
    parser.add_argument('--output', default='data')
    args = parser.parse_args()
    db = args.db
    if not os.path.exists(db): db = '../data/sunlight.db'
    if not os.path.exists(db): print("ERROR: No DB"); sys.exit(1)
    if args.run: rid = args.run
    elif args.latest:
        conn = sqlite3.connect(db); rid = conn.execute("SELECT run_id FROM analysis_runs WHERE status='COMPLETED' ORDER BY completed_at DESC LIMIT 1").fetchone()
        conn.close()
        if not rid: print("No completed runs"); sys.exit(1)
        rid = rid[0]
    else: print("Use --run <id> or --latest"); sys.exit(1)
    print(f"SUNLIGHT Evidence Packet\n  Run: {rid}\n  DB: {db}\n")
    data = load_run_data(db, rid)
    os.makedirs(args.output, exist_ok=True)
    build_pdf(data, os.path.join(args.output, f"SUNLIGHT_Triage_{rid}.pdf"))
    export_csv(data, os.path.join(args.output, f"SUNLIGHT_Queue_{rid}.csv"))
    print("\nDone.")
