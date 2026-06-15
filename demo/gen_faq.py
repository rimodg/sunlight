#!/usr/bin/env python3
"""Generate SUNLIGHT Institutional FAQ as .docx."""

import os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, 'deliverables', 'SUNLIGHT_Institutional_FAQ_EN.docx')

NAVY = RGBColor(0x1A, 0x2A, 0x44)
DARK_GREY = RGBColor(0x33, 0x33, 0x33)

doc = Document()

# Page setup
for section in doc.sections:
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1.25)
    section.bottom_margin = Inches(1.25)
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1.25)

# Styles
style = doc.styles['Normal']
font = style.font
font.name = 'Georgia'
font.size = Pt(11)
font.color.rgb = DARK_GREY

for level in range(1, 4):
    h_style = doc.styles[f'Heading {level}']
    h_font = h_style.font
    h_font.name = 'Georgia'
    h_font.color.rgb = NAVY
    h_font.bold = True
    if level == 1:
        h_font.size = Pt(16)
    elif level == 2:
        h_font.size = Pt(12)
    else:
        h_font.size = Pt(11)


def add_accent_rule(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'<w:bottom w:val="single" w:sz="4" w:space="1" w:color="1A2A44"/>'
        f'</w:pBdr>'
    )
    pPr.append(pBdr)


def add_qa(doc, question, *answer_paragraphs):
    """Add a question-answer pair."""
    # Question as bold heading
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(question)
    run.bold = True
    run.font.name = 'Georgia'
    run.font.size = Pt(11)
    run.font.color.rgb = NAVY

    # Answer paragraphs
    for ans in answer_paragraphs:
        p = doc.add_paragraph(ans)
        p.paragraph_format.space_after = Pt(6)


# ── Title ──
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(36)
run = p.add_run('SUNLIGHT')
run.font.name = 'Georgia'
run.font.size = Pt(22)
run.font.color.rgb = NAVY
run.bold = True

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(24)
run = p.add_run(
    'Institutional Review:\n'
    'Anticipated Technical and Methodological Questions'
)
run.font.name = 'Georgia'
run.font.size = Pt(13)
run.font.color.rgb = NAVY

add_accent_rule(doc)

p = doc.add_paragraph(
    "This document pre-drafts responses to the set of predictable technical and "
    "methodological questions that institutional reviewers are likely to raise when "
    "evaluating SUNLIGHT for deployment within a multilateral procurement oversight "
    "context. Each response is written in institutional register and reflects the "
    "current state of the SUNLIGHT v4.0 Core architecture as of April 2026."
)
p.paragraph_format.space_after = Pt(18)

add_accent_rule(doc)

# ═══════════════════════════════════════════════════════════════════════════
# QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════

add_qa(doc,
    "1. How does SUNLIGHT integrate with UNDP's Quantum ERP system?",

    "SUNLIGHT implements an adapter registry pattern for data ingestion. The architecture "
    "defines a formal InputAdapter interface that transforms institution-specific data "
    "formats into the internal ContractDossier representation consumed by the analytical "
    "engines. Adapters are registered in a central registry and selected at runtime based "
    "on the data source identifier.",

    "A Quantum adapter is currently registered in the adapter registry with a status of "
    "pending UNDP schema specification. The adapter stub exists in the codebase; its "
    "implementation requires the Quantum procurement data schema \u2014 specifically, the "
    "field mappings for contract identifiers, procurement method, award values, supplier "
    "identification, and award dates. Once UNDP shares the Quantum schema documentation, "
    "completing the adapter is a bounded data-mapping task, not an engine modification or "
    "core architecture change. No analytical code is modified; only the input translation "
    "layer is extended."
)

add_qa(doc,
    "2. What is the false-positive profile on real UNDP procurement data?",

    "The current precision calibration is performed against US federal procurement data, "
    "where the engine achieves 33.3% precision at 100% recall on the nine DOJ-prosecuted "
    "reference cases, with a false-positive rate of 9.0% on a 200-contract clean sample. "
    "These numbers represent the institutional credibility floor: the minimum acceptable "
    "performance on data with known prosecution outcomes.",

    "The MJPIS thresholds that gate the Evidence Verification Gate are derived from the "
    "intersection of four mature legal systems (US DOJ, UK SFO, French PNF, World Bank INT). "
    "Because intersection thresholds are strictly tighter than any single jurisdiction's "
    "local calibration, the false-positive rate on any given data slice is bounded from "
    "above by the US federal FPR. However, the exact false-positive profile on UNDP "
    "procurement data can only be determined empirically.",

    "We propose a 500-contract pilot slice as the calibration validation step. UNDP would "
    "provide a representative sample of procurement records across country offices and "
    "procurement categories; SUNLIGHT would process the slice and report the observed "
    "flag rate, the dimensional distribution of findings, and the per-dimension threshold "
    "sensitivity. This pilot produces the empirical numbers required for institutional "
    "confidence without requiring full deployment."
)

add_qa(doc,
    "3. What is the pricing model at UNDP scale?",

    "SUNLIGHT operates on a per-verification passport model, architecturally analogous to "
    "the per-transaction fee structure of international payment networks. Each contract "
    "processed through the analytical pipeline constitutes one verification unit. The unit "
    "cost covers CRI statistical analysis, TCA structural evaluation, and EVG gate "
    "determination with full traceability output.",

    "A single multilateral institution at SUNLIGHT-relevant procurement scale \u2014 processing "
    "tens of thousands of contracts annually \u2014 produces seven-figure annual recurring "
    "revenue from contract throughput at institutional per-unit pricing. Volume tiers and "
    "institutional licensing terms are negotiable within this framework.",

    "Explicitly, SUNLIGHT does not operate on a recovery-share model. Recovery-share "
    "pricing creates incentive distortions that institutional governance bodies correctly "
    "identify and reject: a system financially incentivized to flag more contracts cannot "
    "serve as a neutral analytical layer. The per-verification model preserves analytical "
    "neutrality by decoupling revenue from findings."
)

add_qa(doc,
    "4. Who owns the IP and what is the corporate structure?",

    "SUNLIGHT is owned equally by its two founders: Rimwaya Ouedraogo, the primary "
    "developer and architect of the CRI engine and EVG gate, and Hugo Villalba, the "
    "strategic co-owner and architect of the TCA engine. The codebase resides in a "
    "private GitHub repository under founder control. All intellectual property \u2014 "
    "source code, analytical methodology, the MJPIS standard, and the jurisdiction "
    "profile architecture \u2014 is wholly owned by the two founders. No outside investor "
    "holds equity, board seats, or intellectual property rights in any SUNLIGHT asset."
)

add_qa(doc,
    "5. What happens if a country office disputes a RED finding?",

    "Every RED verdict produced by the Evidence Verification Gate ships with complete "
    "traceability: the specific rule identifiers that fired (e.g., PROC-001, FIN-001, "
    "TIME-001), the legal citations rendered from the applicable jurisdiction profile "
    "(drawn from UNCAC, OECD, FAR, and other frameworks as appropriate), the evidence "
    "dimension scores with their applicable thresholds, and the case precedents from "
    "the MJPIS corpus that anchor the threshold derivation.",

    "A country office dispute is adjudicated against this traceability record. The "
    "institutional investigator can examine each rule that fired, verify the threshold "
    "that was exceeded, and evaluate the legal citations that apply. SUNLIGHT does not "
    "make allegations and does not determine intent. It surfaces structured risk "
    "indicators with audit-trail provenance. The institutional investigator retains "
    "full authority over case disposition, including the determination that a RED "
    "finding does not warrant further action."
)

add_qa(doc,
    "6. Can SUNLIGHT run inside the UNDP Compass environment without data leaving UNDP infrastructure?",

    "Yes. The SUNLIGHT API service is stateless and deterministic. It is deployed as a "
    "containerized application (Docker image, non-root user, health-check configured) "
    "that processes contract data in-memory and returns analytical results without "
    "persisting contract data to disk or transmitting it to external infrastructure. "
    "The container can be deployed inside UNDP's network perimeter \u2014 whether within "
    "the Compass environment, a dedicated UNDP-managed cluster, or behind an "
    "authenticated API gateway.",

    "No contract data ever transits to infrastructure outside UNDP's control. The "
    "architecture documentation explicitly requires private-network or authenticated-gateway "
    "deployment as a deployment precondition, not as an optional configuration. "
    "Authentication and authorization at the deployment boundary are institutional "
    "configuration decisions managed by UNDP's infrastructure team, not SUNLIGHT code "
    "changes."
)

add_qa(doc,
    "7. How is the MJPIS standard maintained and who decides when it updates?",

    "The MJPIS corpus is stored as versioned JSON (prosecuted_cases.json) with each case "
    "recording the jurisdiction, fraud type, documented markup, settlement amount, and "
    "legal citations. Parameter derivation runs deterministically at module-reload time, "
    "producing the intersection thresholds from the current corpus contents. Every "
    "parameter update is auditable through the git commit history on the corpus file, "
    "with the DOJ regression suite verifying that no parameter change degrades recall "
    "on the reference cases.",

    "The question of who approves corpus additions and parameter revisions is an "
    "institutional governance decision appropriate for discussion with UNDP if MJPIS "
    "is adopted as a shared standard. Currently, the founders maintain the corpus with "
    "a published derivation methodology. A natural governance evolution would establish "
    "a review board \u2014 potentially including UNDP, academic, and legal representatives "
    "\u2014 to approve corpus additions from new jurisdictions and validate the intersection "
    "derivation methodology."
)

add_qa(doc,
    "8. What is the relationship between SUNLIGHT and GTI's Compass methodology?",

    "Complementary, not competitive. The Government Transparency Institute's CRI "
    "methodology is the wide-angle indicator dashboard that institutional procurement "
    "oversight teams use to identify contracts warranting closer examination. SUNLIGHT "
    "is the deep structural analysis layer an investigator drops into when an indicator "
    "fires. The two systems operate at different analytical depths and serve different "
    "institutional moments in the oversight workflow.",

    "SUNLIGHT's CRI engine implements the same Fazekas-style statistical methodology "
    "that GTI pioneered \u2014 peer-group comparison, bootstrap confidence intervals, "
    "percentile-based scoring. The architectural differentiation is the TCA topological "
    "engine (structural contract analysis through directed graph evaluation) and the "
    "EVG multi-dimensional gate (requiring convergent evidence across independent "
    "analytical dimensions for a RED verdict). These layers do not replace the "
    "statistical method; they add structural depth that statistical indicators alone "
    "cannot provide."
)

add_qa(doc,
    "9. What is the academic pedigree of the TCA engine?",

    "The Topological Contract Analysis engine operationalizes the i* (i-star) Strategic "
    "Dependency Framework for procurement integrity analysis. The i* formalism, which "
    "models intentional actor dependencies through directed graphs of goals, tasks, "
    "resources, and softgoals, provides the theoretical foundation for TCA's approach "
    "to representing procurement relationships as topological structures with typed "
    "edges (EXPRESSES, BOUNDS, SEEKS, REMOVES, VERIFIES).",

    "Dr. Christelle Scharff, Associate Dean of Pace University's Seidenberg School "
    "of Computer Science and Information Systems and a two-time Fulbright Scholar, "
    "has published extensively on the i* framework and its applications. She is "
    "familiar with this work directly and has provided the academic grounding that "
    "connects TCA's operational methodology to the established requirements engineering "
    "literature."
)

add_qa(doc,
    "10. What engineering rigor has the codebase been subjected to?",

    "The SUNLIGHT codebase maintains 682 automated tests covering statistical correctness "
    "(CRI bootstrap confidence intervals, Bayesian posterior calculations, peer-group "
    "selection), structural rule evaluation (all 16 TCA rules across four jurisdiction "
    "profiles), EVG gate logic (three-verdict tier evaluation, boundary conditions, "
    "null-input handling, integration with real TCA output), API endpoint behavior, and "
    "security hardening.",

    "The 100% DOJ recall invariant is preserved byte-identically across the jurisdiction "
    "profile architecture rollout, the MJPIS derivation arc, the EVG wiring, and the "
    "security hardening: Precision 33.3%, Recall 100.0%, FPR 9.0%, PR-AUC 0.746, "
    "Flags/1K 129.2. A security audit covering 8 of 8 checks passed clean, including "
    "SQL identifier allowlist validation preventing injection through dynamic query "
    "construction. The integration-readiness arc completed 9 of 9 sub-tasks covering "
    "API design, authentication, containerization, and developer documentation.",

    "The EVG key-mismatch incident (commit 706df82) is disclosed transparently: a "
    "dictionary key inconsistency between the TCA analyzer output and the EVG reader "
    "was identified, fixed, and closed by an integration test with counterfactual "
    "verification documenting that the test would have caught the original bug. The "
    "incident and its resolution are described in the technical note accompanying "
    "this package."
)

add_qa(doc,
    "11. How do you calibrate for jurisdictions without mature prosecution corpora?",

    "Through the MJPIS living standard. The Minimum Jurisdictional Prosecutorial "
    "Intersection Standard derives analytical thresholds from the intersection of four "
    "mature legal systems \u2014 US DOJ, UK SFO, French PNF, and World Bank INT \u2014 producing "
    "parameter values that would survive evidentiary scrutiny in all four jurisdictions "
    "simultaneously. This intersection is a strictly tighter bar than any single "
    "jurisdiction's local calibration.",

    "For the approximately 150 UNDP-operational countries that lack deep local prosecution "
    "corpora, MJPIS serves as the primary calibration layer. The architectural design "
    "choice is deliberate: in the absence of local prosecutorial data to calibrate against, "
    "the system defaults to thresholds that are over-defensible rather than under-defensible. "
    "A RED verdict under MJPIS thresholds means the contract would warrant scrutiny in "
    "Washington, London, Paris, and at the World Bank simultaneously. As local prosecution "
    "corpora mature in additional jurisdictions, their cases can be added to the MJPIS "
    "corpus, and the intersection recalculated \u2014 the derivation is deterministic and "
    "auditable."
)

add_qa(doc,
    "12. What is the time-to-deployment from a go-decision inside UNDP?",

    "Deployment timeline is contingent on UNDP data and integration specifications. From "
    "a UNDP go-decision with Quantum schema access and a pilot procurement data slice, "
    "the registered stub adapter becomes a functional adapter in bounded engineering time. "
    "A pilot run against a representative UNDP contract volume can produce initial "
    "institutional reporting within weeks rather than months.",

    "The critical-path dependencies are on the UNDP side: Quantum schema documentation, "
    "a representative pilot data slice, infrastructure access for container deployment, "
    "and institutional authorization for the pilot scope. On the SUNLIGHT side, the "
    "analytical engines, the EVG gate, the jurisdiction profile architecture, and the "
    "API layer are production-ready and regression-tested. We do not commit to a specific "
    "calendar timeline in the absence of UNDP-side specifications, but the engineering "
    "work between schema access and first pilot results is bounded and well-characterized."
)

# ── Save ──
doc.save(OUTPUT_PATH)
print(f"FAQ saved to: {OUTPUT_PATH}")
