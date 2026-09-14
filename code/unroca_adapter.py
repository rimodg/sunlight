import sys, csv, hashlib, re, pdfplumber
BALKAN = ("Serbia","Bulgaria","Bosnia and Herzegovina","Croatia","Czech Republic","Czechia","Montenegro","Romania","Slovakia")
GULF = ("Saudi Arabia","Jordan","United Arab Emirates","Turkey","Türkiye")
CAT_RE = re.compile(r'^(I|II|III|IV|V|VI|VII)\.?$|^\d{1,2}\.$')
def rows_of(page):
    rows = {}
    for w in page.extract_words(use_text_flow=False):
        rows.setdefault(round(w['top']/4)*4, []).append(w)
    return [sorted(rows[k], key=lambda w: w['x0']) for k in sorted(rows)]
def bands_from_rows(rows):
    for i, r in enumerate(rows):
        t = {w['text']: w['x0'] for w in r}
        if 'Number' in t and 'Intermediate' in t:
            num = t['Number']; inter = t['Intermediate']
            org = min([w['x0'] for w in r if w['text']=='State' and w['x0'] > num] or [inter-40])
            imp = None; desc = None; com = None
            for rr in rows[max(0,i-2):i+3]:
                for w in rr:
                    if w['text'] in ('Final','Trading') and imp is None: imp = w['x0']
                    if w['text'].startswith('Description') and desc is None: desc = w['x0']
                    if w['text'].startswith('Comments') and com is None: com = w['x0']
            if imp is None: imp = num - 110
            return imp-3, num-3, org-3, inter-3, (desc or 380)-3, (com or 475)-3
    return None
def parse(pdf_path, symbol, year):
    out = []; sha = hashlib.sha256(open(pdf_path,'rb').read()).hexdigest()[:16]
    with pdfplumber.open(pdf_path) as pdf:
        state = None; bands = None; table = None; cat = None; last_state = None
        for pno, page in enumerate(pdf.pages, 1):
            rows = rows_of(page)
            b = bands_from_rows(rows)
            if b: bands = b
            for i, r in enumerate(rows):
                txt = " ".join(w['text'] for w in r)
                if re.search(r'Original language|\[Original:|Original:', txt):
                    for back in range(1, 5):
                        if i-back >= 0:
                            cand = " ".join(w['text'] for w in rows[i-back]).strip()
                            if cand and not re.search(r'\d|A/|Original', cand) and len(cand.split()) <= 5:
                                state = cand; break
                if txt.strip() in ('Exports','Imports'): table = txt.strip()
            if not bands: continue
            imp_x, num_x, org_x, inter_x, desc_x, com_x = bands
            if state != last_state: cat = None; last_state = state
            rec = None
            def flush():
                if rec and rec['number']: out.append(dict(rec))
            for r in rows:
                cell = {'cat':[], 'imp':[], 'num':[], 'org':[], 'inter':[], 'desc':[], 'com':[]}
                for w in r:
                    x = w['x0']; t = w['text']
                    k = 'cat' if x < imp_x else 'imp' if x < num_x else 'num' if x < org_x else 'org' if x < inter_x else 'inter' if x < desc_x else 'desc' if x < com_x else 'com'
                    cell[k].append(t)
                if cell['cat'] and CAT_RE.match(cell['cat'][0]):
                    flush(); rec = None; cat = " ".join(cell['cat'])
                elif cell['cat'] and cat and rec is None and not cell['num']:
                    cat = cat + " " + " ".join(cell['cat'])
                numtxt = re.sub(r'\D', '', "".join(cell['num']))
                if numtxt:
                    flush()
                    rec = {'symbol':symbol,'year':year,'page':pno,'state':state,'table':table,'category':cat,
                           'importer':" ".join(cell['imp']),'number':int(numtxt),'origin':" ".join(cell['org']),
                           'intermediate':" ".join(cell['inter']),'description':" ".join(cell['desc']),
                           'comments':" ".join(cell['com']),'sha256_16':sha}
                elif rec is not None:
                    for k, f in (('imp','importer'),('org','origin'),('inter','intermediate'),('desc','description'),('com','comments')):
                        if cell[k]: rec[f] = (rec[f] + " " + " ".join(cell[k])).strip()
            flush()
    for r in out:
        for k in ('importer','origin','intermediate','description','comments','category'):
            r[k] = re.sub(r'\s+',' ', r[k] or '').strip()
    return out
if __name__ == '__main__':
    pdf_path, symbol, year, out_csv = sys.argv[1:5]
    recs = parse(pdf_path, symbol, int(year))
    with open(out_csv,'w',newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(recs[0].keys())); w.writeheader(); w.writerows(recs)
    states = sorted({r['state'] for r in recs if r['state']})
    print("RECORDS:", len(recs), "STATES:", len(states))
    hits = [r for r in recs if r['table']=='Exports' and r['state'] and any(b in r['state'] for b in BALKAN) and any(g in r['importer'] for g in GULF)]
    print("BALKAN->GULF/TURKEY EXPORT ROWS:", len(hits))
    for r in hits[:18]:
        print(f"  p{r['page']} {r['state'][:10]} -> {r['importer'][:20]} | {r['category'][:26]} | n={r['number']} | {r['description'][:40]} | origin={r['origin'][:14]} | via={r['intermediate'][:12]}")
