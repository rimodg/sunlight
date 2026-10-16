#!/usr/bin/env python3
"""Create a self-contained institutional briefing from an actual API reading.

Uses an explicitly fictional procurement record. The output is a demonstration,
not a field observation or an evaluation of real-world detection performance.
"""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    request = {"profile": "us_federal", "contract": {
        "ocid": "synthetic-institutional-briefing-001",
        "buyer": {"id": "EXAMPLE-AUTHORITY", "name": "Illustrative public authority"},
        "tender": {"procurementMethod": "direct", "numberOfTenderers": 1,
                   "title": "Illustrative medical supplies", "value": {"amount": 1000000, "currency": "USD"},
                   "tenderPeriod": {"startDate": "2025-01-01", "endDate": "2025-02-01"}},
        "awards": [{"id": "EXAMPLE-AWARD", "date": "2025-02-15",
                    "value": {"amount": 1000000, "currency": "USD"},
                    "suppliers": [{"id": "EXAMPLE-SUPPLIER", "name": "Illustrative supplier"}]}]}}
    with urlopen(Request(args.base_url.rstrip('/') + '/analyze',
                         data=json.dumps(request).encode(),
                         headers={'Content-Type': 'application/json'}), timeout=30) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError(result['errors'])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    packet = {'request': request, 'response': result, 'input_origin': 'Synthetic briefing example'}
    packet_path = args.output_dir / 'evidence-packet.json'
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False))
    findings = result['structure']['contradictions']
    rows = ''.join(f'<article class="finding"><code>{escape(f["rule_id"])}</code>'
                   f'<h3>{escape(f["description"])}</h3><p>{escape(f["legal_citation"])}</p></article>'
                   for f in findings)
    quality = result['ingestion_quality']
    missing = ', '.join(quality['missing_fields']) or 'None reported by the presence heuristic'
    receipt = result['analysis_receipt']
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>SUNLIGHT | An instrument for institutional review</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#e9ece2;color:#19342b;font:14px/1.65 Arial,sans-serif}}
.page{{width:210mm;min-height:297mm;padding:19mm 20mm;background:#f9f9f0;margin:20px auto;position:relative;break-after:page}}
.brand{{letter-spacing:4px;font-size:20px;font-weight:700;border-bottom:1px solid #c9d5bf;padding-bottom:15px}}
.brand span{{float:right;font-size:8px;letter-spacing:1.4px;line-height:32px;font-weight:400}}
.eyebrow{{font-size:9px;letter-spacing:2px;margin:34px 0 20px;text-transform:uppercase;color:#5d7256}}
h1{{font-size:62px;line-height:1.03;letter-spacing:-3px;font-weight:400;margin:0 0 25px}}h1 span{{color:#849576}}
.lead{{font-size:17px;max-width:560px;line-height:1.7}}h2{{font-size:29px;line-height:1.15;letter-spacing:-1px;font-weight:400;margin:25px 0 18px}}
h3{{font-size:15px;font-weight:500;line-height:1.5}}p{{color:#53694e}}.flow{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;border-top:1px solid #c9d5bf;border-bottom:1px solid #c9d5bf;padding:20px 0;margin:30px 0}}
.flow b{{display:block;font-size:9px;color:#7e906b;margin-bottom:10px}}.flow span{{font-size:12px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:25px}}.grid p{{font-size:12px}}
.note{{background:#edf0da;border-left:3px solid #98ac52;padding:15px 18px;font-size:12px;margin:24px 0}}.foot{{font-size:9px;color:#6f8063;border-top:1px solid #c9d5bf;margin-top:30px;padding-top:12px}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);border-block:1px solid #c9d5bf;padding:18px 0;gap:15px;margin:24px 0}}.metrics small{{display:block;font-size:9px;color:#6d7e60;margin-bottom:8px}}.metrics strong{{font-weight:400;font-size:22px;text-transform:capitalize}}
.finding{{padding:16px 0;border-bottom:1px solid #d7dfca}}code{{font-size:10px;background:#e8edcc;padding:4px 6px}}.finding p{{font-size:11px}}.finding h3{{margin:10px 0}}.hash{{word-break:break-all;font:9px/1.6 monospace;color:#586e4d}}li{{margin:14px 0;color:#53694e}}a{{color:#365a32}}.small{{font-size:11px}}
@media print{{body{{background:white}}.page{{margin:0;min-height:297mm}}@page{{size:A4;margin:0}}}}
</style>
<section class="page"><div class="brand">SUNLIGHT<span>THE GLOBAL HUMANITARIAN WATCH</span></div>
<div class="eyebrow">An instrument for institutional review</div>
<h1>Public value.<br><span>Made inspectable.</span></h1>
<p class="lead">Follow a commitment through its records. Expose contradictions with their basis. Keep what remains unknown visible.</p>
<div class="flow"><span><b>01 / NORM</b>What is required?</span><span><b>02 / RECORD</b>What was filed?</span><span><b>03 / TRACE</b>What can be followed?</span><span><b>04 / ACTION CHAIN</b>Who can review?</span></div>
<div class="grid"><div><h2>A shared problem</h2><p>Procurement, delivery, and payment records can appear plausible individually while their relationships conflict. Review capacity is scarce, and evidence is fragmented across systems.</p></div><div><h2>An inspectable response</h2><p>SUNLIGHT reads supplied procurement data against explicit rules and jurisdiction calibration. Each reading exposes findings, analytical dimensions, input gaps, and a reproducible content receipt.</p></div></div>
<div class="note">Operational entry point: procurement review. Wider charter: arms, commodities, aid, and documented human need. Each additional category requires its own validated evidence and implementation.</div>
<p class="small">For international relations: reporting obligations and institutional action chains. For economics: transparent measurement and review allocation. For trade: records, counterpart consistency, and traceability across flows.</p>
<div class="foot">Decision support / Human authority / Documented limits</div></section>
<section class="page"><div class="brand">SUNLIGHT<span>A LIVE ANALYTICAL READING</span></div>
<div class="eyebrow">Fictional record / Actual engine output</div><h2>A direct award.<br>A visible basis for review.</h2>
<p>A synthetic USD 1,000,000 direct award is submitted under the US federal calibration. This page is generated from the API response, not an animated or invented result.</p>
<div class="metrics"><div><small>STRUCTURAL READING</small><strong>{escape(result['structure']['verdict'])}</strong></div><div><small>EVIDENCE GATE</small><strong>{escape(result['gate_verdict'])}</strong></div><div><small>NORMALIZED FIELDS PRESENT</small><strong>{quality['fields_present']} / {quality['fields_total']}</strong></div></div>
{rows}
<div class="note">A structural concern and a green evidence gate answer different questions. Neither establishes wrongdoing. A green gate does not certify integrity.</div>
<h3>Input limitations travel with the result</h3><p class="small">Missing normalized fields: {escape(missing)}. Presence is not truth; defaults can count as present and the v1 heuristic treats numeric zero as missing.</p>
<h3>The reading can be checked</h3><p class="small">The accompanying <a href="evidence-packet.json">JSON packet</a> carries the request, response, calibration hashes, Python source manifest, and runtime versions. Use the offline verifier to check content equality. Hashes are not signatures or source authentication.</p>
<p class="hash">RESULT SHA-256<br>{receipt['result_sha256']}</p>
<div class="foot">Synthetic demonstration / No claim about real-world detection performance</div></section>
<section class="page"><div class="brand">SUNLIGHT<span>THE INSTITUTIONAL PATH</span></div>
<div class="eyebrow">A bounded pilot with measurable acceptance</div><h1 style="font-size:49px">From a finding<br><span>to accountable review.</span></h1>
<ol><li><strong>Agree the question.</strong> Select an institution-approved dataset, jurisdiction, review team, and acceptance criteria.</li><li><strong>Validate the mapping.</strong> Check that supplied source fields reach the analytical dossier and that missing evidence stays unknown.</li><li><strong>Compare the review process.</strong> Measure coverage, false positives, unassessable cases, workload, and reviewer dispositions against the institution's existing process.</li><li><strong>Establish the controls.</strong> Approve access, retention, corrections, disclosure, independent security review, and named action owners.</li><li><strong>Verify the handoff.</strong> Track acknowledgement, review, disposition, and any authorized action. Operational benefit needs observed evidence.</li></ol>
<div class="note">SUNLIGHT has no authority to freeze, recover, redirect, or disburse funds. Those capabilities require separate mandates and operational integrations.</div>
<h2>Evidence before adoption claims.</h2><p>Historical metrics belong to their exact corpus and sampling protocol. The complete reference database is required to reproduce the published floor. A synthetic demonstration, a green test suite, and field effectiveness are different forms of evidence.</p>
<p class="small">Companion documents: docs/INSTITUTIONAL_REVIEW.md and docs/CHARTER_v2_global_humanitarian_watch.md. No institutional endorsement or deployment approval is implied.</p>
<div class="foot">An inspectable instrument earns trust through reproducible results.</div></section></html>'''
    (args.output_dir / 'SUNLIGHT-Briefing.html').write_text(html)
    print(json.dumps({'briefing': str(args.output_dir / 'SUNLIGHT-Briefing.html'),
                      'packet': str(packet_path), 'packet_sha256': sha256(packet_path.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
