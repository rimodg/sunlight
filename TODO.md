# SUNLIGHT — To-Do List

**Last updated:** April 11, 2026
**Current commit on main:** `61874e3`

**Filter for everything below:** does this make SUNLIGHT more ready to be pointed at real UNDP contracts and produce correct, actionable, defensible output the day Dr. Scharff's introduction lands? Items that do not clear that bar are deferred, cut, or moved to post-meeting work.

---

## Phase 0 — Loose ends (close before new work starts)

- [x] **1. Canonical doc update.** Shipped at commit `9ad0ca4`. `SUNLIGHT_SYSTEM_REFERENCE.md` now reflects the architectural state of main through the REST API layer, including section 3.5 (REST API Layer), section 5.4 (REST API end-to-end validation), updated section 10 priorities, and corrected commit count.
- [ ] **2. Project instructions re-paste.** Copy the updated `SUNLIGHT_SYSTEM_REFERENCE.md` contents into Claude project settings so future sessions auto-load correct state. 30-second UI action. (Rim's own action, not Claude Code.)
- [ ] **3. Security baseline — 15 minutes.** Verify FileVault enabled on the Mac (`System Settings → Privacy & Security → FileVault`). Verify 2FA enabled on Rim's and Hugo's GitHub accounts. Verify `sunlight.db` and `prosecuted_cases.json` are not in any cloud sync folder (iCloud Drive, Google Drive, Dropbox). (Rim's own action, unblocked by anything else.)
- [x] **4. Stored memory cleanup decision.** Three stale items flagged in auto-loaded context: the Paraguay 500-contract validation that never happened, the "six engine builds" list that does not match current architecture, and the GitHub auth friction note that is no longer accurate. Decision: explicit cleanup via the memory tool, or leave to age out naturally.  Decision: leave stale items to age out naturally. No active purge.

---

## Phase A — Integration-readiness arc

Critical path. Make SUNLIGHT deployable and testable on real UNDP data. Every item below blocks the Scharff outreach v2 draft because the outreach references the system's actual state.

### Cluster A1 — Mathematical correctness

- [x] **5. Sub-task 2.2.7i — Capacity-calibrated threshold layer.** Adds `capacity_budget` to POST /batch, computes the max of statistical and capacity thresholds, populates `recommended_for_investigation` on responses, reports binding threshold in response metadata. Spec already written in session conversation, ready to paste. Estimate: 2-4 hours. Blocks: nothing in this cluster. Shipped at commit `0f0c3f9`.
- [x] **6. Sub-task 2.2.7h — Sample-size scaling for bootstrap.** Surgical change replacing hardcoded `clean_sample=200` with `max(200, int(sqrt(total_contracts)))` in the evaluation path so bootstrap confidence intervals sharpen correctly with scale. Estimate: 2-3 hours. Blocks: nothing, surgical fix. Shipped at commit `799f298`.

### Cluster A2 — Fourth-engine engineering proof

- [x] **7. Sub-task 2.2.7k — Empirical self-calibration layer.** The engineering proof of the monotonic-learning property. SUNLIGHT maintains running empirical distributions of rule fire rates and risk scores per profile, continuously sharpened by operational flow, with the fraud-pattern side strictly anchored in the Jurisprudence corpus (never self-learned) so circular drift cannot occur. Spec needs to be written before paste. Estimate: spec writing 1 hour, Claude Code implementation 4-6 hours. Depends on: 2.2.7i and 2.2.7h landing first. Phase one (observation layer) shipped at commit `de69410`. Phase two (consumption layer, provisional 2.2.7l) reserved for future work.

### Cluster A3 — Deployment hardening

- [x] **8. Sub-task 2.2.7d — Dockerfile and containerized deployment artifact.** Multi-stage Dockerfile producing a reproducible container image for the API service. Dependency pinning, non-root user, health check configuration, environment variable configuration, minimal attack surface. Estimate: 2-4 hours. Depends on: 2.2.7k. Shipped at commit `ea4f2ec`.
- [x] **9. Sub-task 2.2.7c — Output serialization hardening with roundtrip tests.** Defensive hardening of every Pydantic response model to ensure JSON roundtrip stability. Estimate: 2-3 hours. Parallel with 2.2.7d. Shipped at commit `a65f0db`.
- [x] **10. Sub-task 2.2.7e — Integration test suite against live HTTP server.** Actual uvicorn server spun up in a test fixture, hit with real HTTP requests, verifying end-to-end behavior including the Dockerized deployment path. Estimate: 2-3 hours. Depends on: 2.2.7d. Shipped at commit `1f9b71b`.

### Cluster A4 — Flexibility

- [x] **11. Sub-task 2.2.7b — Input format adapter architecture.** Pluggable ingestion layer with adapters for canonical OCDS (exists, wrapped in adapter interface), placeholder for Quantum format, placeholder for Compass format. Estimate: 3-5 hours. Best shipped after 2.2.7c. Shipped at commit `231702b`.

### Cluster A5 — Documentation

- [x] **12. Sub-task 2.2.7f — `docs/INTEGRATION.md` developer guide.** Deployment instructions, API reference with example curl commands for every endpoint, profile selection guidance, capacity budget calibration guidance, troubleshooting section, security deployment notes. Estimate: 3-4 hours. Depends on: everything else in Phase A being stable. Shipped at commit `e3ca5ba`.

### Cluster A6 — Empirical validation

- [ ] **13. Sub-task 2.2.7j — Rule fire rate invariance measurement.** Run SUNLIGHT against progressively larger samples (42K US federal, UK corpus, UNDP-adjacent data when accessible) and measure per-rule fire rates with confidence intervals. Artifact is the measurement report. Estimate: 6-12 hours, research-heavy. Can parallelize with Phase B.

---

## Phase B — Jurisprudence Engine arc (the fourth engine)

Fixes the 9-DOJ-cases validation weakness and makes the living multi-jurisdiction standard real rather than aspirational. Critical for the Timilsina pitch, much stronger if at least partially in place when the Scharff reply lands.

- [x] **14. Sub-task 2.3.1 — Naming decision.** "Jurisprudence Engine" proposed because it signals legal grounding, works in English and French, has scholarly gravity. Alternatives open.  Locked as **Jurisprudence Engine**. Signals legal grounding, works in English and French, scholarly gravity.
- [ ] **15. Sub-task 2.3.2 — Corpus expansion, UK SFO DPAs.** Extract 12-15 UK SFO Deferred Prosecution Agreement cases from 2014-2025 into the existing `prosecuted_cases_global_v0.1.json` schema. Target cases: Rolls-Royce 2017, Airbus 2020, Standard Bank 2015, Tesco 2017, Sarclad 2016, Güralp 2019, Airline Services 2020, Amec Foster Wheeler 2021, NatWest 2021, and others. Estimate: 6-10 hours research.  In progress: 3/15 UK SFO cases extracted (Rolls-Royce 2017, Airbus 2020, Standard Bank 2015 — the first-ever UK DPA and first Bribery Act 2010 s.7 prosecution, bribery-channel dimensional anchor at USD 6M/USD 600M = 1.0%). Phase B also now has 1/12 French PNF cases (Airbus 2020) via the cross-jurisdictional Airbus resolution.
- [ ] **16. Sub-task 2.3.3 — Corpus expansion, French PNF CJIPs.** Extract 8-12 French PNF CJIP cases from 2017-2025. Target cases: HSBC 2017, Société Générale 2018, Airbus 2020, Bolloré 2021, Bolloré 2023, McDonald's France 2022, Google France 2019, and others. Estimate: 5-8 hours research.  In progress: 2/12 French PNF cases extracted (Airbus 2020 via cross-jurisdictional Airbus resolution, Bolloré 2021 Togo port concession bribery). HSBC Private Bank Suisse 2017 evaluated and excluded per dimensional relevance filter — underlying conduct is aggravated laundering of tax fraud proceeds, not procurement bribery; out of scope for SUNLIGHT statistical calibration. Foundational French CJIP case for legal-precedent reference only.
- [ ] **17. Sub-task 2.3.4 — Corpus expansion, World Bank INT Sanctions Board.** Extract 10-15 World Bank INT Sanctions Board cases from recent fiscal years. Administrative-sanctionable at "more likely than not" standard. Estimate: 6-10 hours.
- [ ] **18. Sub-task 2.3.5 — Dimensional classification system.** Classify every case in the expanded corpus as markup_based, bribery_channel, administrative_sanctionable, or multi-category. Estimate: 3-5 hours.
- [ ] **19. Sub-task 2.3.6 — Cross-jurisdictional normalization.** Currency conversion at historical exchange rates, date normalization, evidentiary standard translation layer, legal basis taxonomy mapping. Estimate: 4-6 hours.
- [ ] **20. Sub-task 2.3.7 — Real intersection methodology.** Replace the `NotImplementedError` in `mjpis_derivation.py` with the actual intersection methodology: markup floor from US DOJ, bribery-channel pattern from UK SFO + French PNF, administrative-sanctionable threshold from World Bank INT. Estimate: 6-10 hours. Depends on 2.3.2 through 2.3.6.
- [ ] **21. Sub-task 2.3.8 — Recall validation loop.** Run SUNLIGHT's engines against every case in the expanded corpus under the new MJPIS thresholds and verify 100% recall. Estimate: 4-6 hours. Depends on 2.3.7.
- [ ] **22. Sub-task 2.3.9 — Dimensional coverage tracking and living update interface.** Mechanism by which new prosecuted cases entering the corpus trigger automatic re-derivation and re-validation. Estimate: 3-5 hours. Depends on 2.3.8.

**Phase B total estimate:** 40-60 hours, spread across 4-8 focused sessions, producing a corpus of 40-60 cases from four jurisdictions spanning all three dimensional categories.

---

## Phase C — Scharff outreach document v2

- [ ] **23. Scharff outreach document v2 draft.** Written directly in conversation, not a Claude Code task. Anchored in Dr. Timilsina's published implementation-gap framing, shared Fazekas methodological lineage, explicit mapping to Compass five indicators, and the current architectural state. Sent only after Phase A is complete and Phase B has at least 2.3.2-2.3.4 done. Estimate: 45-90 minutes of careful writing, several iterations. Blocks: Phase A completion, partial Phase B.

---

## Phase D — IP and architectural framing

Executed after the build is stable, before any public claims about the architectural methodology are made, ideally before the Scharff outreach actually lands in her inbox.

- [x] **24. Architecture name lock.** Decide on the final name for the architectural methodology — "Perpetual Intelligence Architecture" or alternative. Blocks all of 25-27.  Locked as **Invariant Detection Architecture (IDA)**. SUNLIGHT is the first reference implementation. Documented in docs/ARCHITECTURE.md.
- [ ] **25. Trademark filing.** USPTO TEAS Plus form, Classes 9 + 42 minimum, possibly 41. Approximately $500-750 total. One hour. Establishes legal priority on the architecture name.
- [ ] **26. Domain registration.** .com, .org, .net at minimum for the chosen name. Under $100, 15 minutes.
- [ ] **27. Public GitHub prior-art repo.** New public repo with a markdown file describing the seven architectural principles and the SUNLIGHT case study. Establishes cryptographically timestamped prior art against any later patent claim by anyone else. 3-4 hours writing.
- [ ] **28. Methodology paper draft.** Target venue: peer-reviewed journal (*Governance*, *Public Administration Review*) or major conference. Dr. Scharff as co-author ideal, or at minimum as acknowledged academic supervisor. Cites Fazekas 2018 and Dr. Scharff's i* framework. Uses SUNLIGHT as the worked example. Includes mathematical treatment of scale-invariance properties. 3-month drafting horizon, 6-12 months peer review.

---

## Critical path

Phase 0 items 1-3 → Phase A items 5-12 (skipping 13 initially) → Phase B items 14-17 (first corpus expansion pass, skipping full derivation initially) → Phase C item 23 → Phase D items 24-27 → send the Scharff document.

Item 13 and items 18-22 can run in parallel with later phases or happen after the Scharff outreach lands. Item 28 is a 3-month track that runs alongside everything else.

**Total critical-path estimate:** Roughly 30-50 hours of focused Claude Code work across Phase A, plus 20-30 hours of research work across Phase B, plus 1-2 hours of strategic writing for Phase C, plus 2-3 hours of personal action for Phase D. Call it 55-85 hours of total effort, spread across 8-15 sessions. Realistic elapsed time: 3-6 weeks if sessions are frequent and focused.

---

## How to use this file

This is the durable source of truth for session planning. When a sub-task ships, mark its checkbox in place and append the commit hash to the item description. Update the "Last updated" and "Current commit on main" fields at the top. The file is the memory anchor that makes drift visible the moment it happens — if a session starts producing work that is not on this list, the work either belongs on the list (add it explicitly) or it does not belong in the session (defer it).
