# SUNLIGHT — To-Do List

**Last updated:** April 13, 2026
**Current commit on main:** `27c0d79`

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
- [ ] **15. Sub-task 2.3.2 — Corpus expansion, UK SFO DPAs.** Extract 12-15 UK SFO Deferred Prosecution Agreement cases from 2014-2025 into the existing `prosecuted_cases_global_v0.1.json` schema. Target cases: Rolls-Royce 2017, Airbus 2020, Standard Bank 2015, Tesco 2017, Sarclad 2016, Güralp 2019, Airline Services 2020, Amec Foster Wheeler 2021, NatWest 2021, and others. Estimate: 6-10 hours research.  In progress: 9/15 UK SFO cases extracted (Rolls-Royce 2017, Airbus 2020, Standard Bank 2015, Tesco 2017, Sarclad 2016, Guralp 2019, Serco 2019, Amec Foster Wheeler 2021, Petrofac 2021 — first UK SFO criminal conviction in the corpus, distinct from the eight DPA cases). Note: NatWest 2021 evaluated and excluded — FCA prosecution under Money Laundering Regulations, not SFO, jurisdictional mismatch with UK_SFO partition tag. Tesco 2017 is the architectural milestone case for sub-task 2.3.7 because Tesco's overstatement ratio (£250M / £499M = 0.501) undercuts the US DOJ DynCorp 2005 floor (0.75), causing the MJPIS intersection methodology to automatically recompute `markup_floor_ratio` from 0.75 to 0.501 with zero code change at call sites — empirical proof that the load-bearing property of item 20 MVP is real. All non-markup cases (Sarclad, Guralp, Serco, Amec Foster Wheeler, Petrofac) are load-bearing invariant tests: none tagged `markup_based`, they correctly leave `markup_floor_ratio` pinned at 0.501, demonstrating that the dimensional partition in `derive_mjpis_parameters()` correctly routes each case to its own derivation path. UK SFO bribery_channel ratio coverage now spans Standard Bank ~1%, Amec Foster Wheeler 0.58% (Petrobras/Unaoil), Guralp ~50%, and Petrofac ~1.26%, providing real multi-scale data for the future bribery-channel consumer module. UK SFO is the strongest non-DOJ jurisdiction in the corpus at 9 cases, now including the first criminal conviction alongside eight DPAs. Phase B also has 6/12 French PNF cases.
- [ ] **16. Sub-task 2.3.3 — Corpus expansion, French PNF CJIPs.** Extract 8-12 French PNF CJIP cases from 2017-2025. Target cases: HSBC 2017, Société Générale 2018, Airbus 2020, Bolloré 2021, Bolloré 2023, McDonald's France 2022, Google France 2019, and others. Estimate: 5-8 hours research.  In progress: 6/12 French PNF cases extracted (Airbus 2020 cross-jurisdictional, Bollore 2021 standalone, Societe Generale 2018 cross-jurisdictional, Egis Avia 2019 procurement infrastructure, Bouygues/Linkcity 2023 procurement favoritism, Airbus 2022 follow-on France-only for Libya/Kazakhstan/IPA facts procedurally severed from the 2020 global resolution). HSBC Private Bank Suisse 2017 evaluated and excluded per dimensional relevance filter — underlying conduct is aggravated laundering of tax fraud proceeds, not procurement bribery; out of scope for SUNLIGHT statistical calibration. Foundational French CJIP case for legal-precedent reference only.
- [ ] **17. Sub-task 2.3.4 — Corpus expansion, World Bank INT Sanctions Board.** Extract 10-15 World Bank INT Sanctions Board cases from recent fiscal years. Administrative-sanctionable at "more likely than not" standard. Estimate: 6-10 hours.  In progress: 6/15 World Bank INT cases extracted (SNC-Lavalin 2013 Padma Bridge, Alstom Hydro France 2012 Zambia hydropower with USD 9.5M restitution, Siemens AG 2009 global multi-institutional settlement with USD 100M anti-corruption payment, Macmillan Limited 2010 Sudan MDTF education textbooks, Alcatel-Lucent 2015 Iraq Emergency PSD telecommunications — first short-duration WB INT debarment in corpus at 18 months, CRBC/NRIMP1 2009 Philippines National Roads Improvement bid-rigging cartel — first cartel/collusive-bid-rigging case in corpus, first permanent debarment, first successor-liability extension doctrine, new evidentiary standard `wb_sanctions_board_decision` registered). WB INT slice now spans 6 sectors and duration range 18 months to permanent. Corpus at 30 cases across 4 jurisdictions (9 US DOJ + 9 UK SFO + 6 FR PNF + 6 WB INT).
- [ ] **18. Sub-task 2.3.5 — Dimensional classification system.** Classify every case in the expanded corpus as markup_based, bribery_channel, administrative_sanctionable, or multi-category. Estimate: 3-5 hours.
- [ ] **19. Sub-task 2.3.6 — Cross-jurisdictional normalization.** Currency conversion at historical exchange rates, date normalization, evidentiary standard translation layer, legal basis taxonomy mapping. Estimate: 4-6 hours.
- [ ] **20. Sub-task 2.3.7 — Real intersection methodology.** Replace the `NotImplementedError` in `mjpis_derivation.py` with the actual intersection methodology: markup floor from US DOJ, bribery-channel pattern from UK SFO + French PNF, administrative-sanctionable threshold from World Bank INT. Estimate: 6-10 hours. Depends on 2.3.2 through 2.3.6.  Minimum-viable increment shipped: methodology version `mjpis_v0.2` derives `markup_floor_ratio` empirically via cross-jurisdictional intersection, consumed by FIN-001 as a second threshold alongside the local legal tolerance. New `derivation_metadata` field on `GlobalParameters` carries the provenance trail (per-jurisdiction floors, intersection floor, contributing case IDs). FIN-001 is now a two-threshold rule (Check A = local legal tolerance, Check B = MJPIS empirical floor) with an evidence string that surfaces MJPIS provenance when Check B trips under a profile referencing `mjpis_draft_v0`. DOJ regression byte-identical (100% recall, precision 31.0%, CI Gate PASS, flags/1K 138.8). Five new tests in `tests/test_mjpis_v02_consumption.py` lock in the derivation and consumption paths. The bribery-channel and administrative-sanctionable consumers await their own dimensional categories gaining corpus coverage (Phase B items 15-17) and consumer rules.
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

## Phase E — Legal citations architecture hardening

Items identified by the legal_citations depth audit (session of April 13, 2026). Recommendation 1 (hardcoded US statutes in CRI) shipped at commit `39b5d65`. Recommendation 6 (universal_citations expansion) shipped at commit `8fe487c`. Recommendation 3 (us_federal deepening) shipped at commit `3286aad`. Recommendation 3 completion (uk_central_government deepening to 12-key parity) shipped at commit `2f8caf8`. Recommendation 2 (retire dead competition_law key) shipped at commit `e573060`. Recommendation 4 (WB_INT profile) shipped at commit `14dfab1`. Recommendation 5 (FRANCE_PNF profile) shipped at commit `2274506`. **PHASE E COMPLETE** — all six audit recommendations shipped. Corpus jurisdiction surface and operational jurisdiction surface now match exactly (US_DOJ, UK_SFO, FR_PNF, WB_INT).

- [x] **29. Audit recommendation 1 — Decouple CRI legal citations from hardcoded US statutes.** Add `false_claims_law`, `false_records_law`, `anti_kickback_law`, `extreme_markup_precedent` keys to `legal_citations` on `JurisdictionProfile`. Modify `ProsecutorEvidencePackage._determine_tier()` to read from profile instead of hardcoding. Shipped at commit `39b5d65`. DOJ regression byte-identical.
- [x] **30. Audit recommendation 2 — Retire dead `competition_law` key.** `competition_law` was defined on both profiles ("Sherman Antitrust Act" on us_federal, "Competition Act 1998" on uk_central_government) but consumed by zero rules. Verified zero consumers by grep across code/ and tests/. Removed from both profiles and from schema documentation. Canonical legal_citations surface is now 11 keys, locked by explicit enumeration and negative-assertion tests. Shipped at commit `e573060`. DOJ regression byte-identical.
- [x] **31. Audit recommendation 3 — Deepen existing profiles.** Both existing profiles now at 12-key institutional depth. us_federal deepened from 7 to 12 keys at commit `3286aad`: added `foreign_bribery_law` (FCPA), `audit_oversight_law` (IG Act + FMFIA), `sanctions_debarment_law` (FAR 9.4 + EO 12549 + 2 C.F.R. 180), `conflict_of_interest_law` (18 U.S.C. § 208 + Procurement Integrity Act), `whistleblower_protection_law` (FCA anti-retaliation + 41 U.S.C. § 4712). Deepened `procurement_law` to cover FAR Parts 6, 13, 15. Deepened `case_authority` to aggregate five DOJ corpus cases. uk_central_government deepened to 12-key parity at commit `2f8caf8`: added `foreign_bribery_law` (Bribery Act 2010 ss.6-7), `audit_oversight_law` (NAA 1983, GRAA 2000), `sanctions_debarment_law` (PA 2023 Part 5), `conflict_of_interest_law` (BA 2010 ss.1-2, Nolan Principles), `whistleblower_protection_law` (PIDA 1998). Deepened `procurement_law` to cover PA 2023, PCR 2015, CCR 2016, UCR 2016. Deepened `case_authority` to aggregate six UK SFO corpus cases. Schema documentation lists all 12 expected keys. Key parity test enforces alignment. DOJ regression byte-identical on both commits.
- [x] **32. Audit recommendation 4 — Create WB_INT jurisdiction profile.** Third operational profile covering World Bank Group — Integrity Vice Presidency. WB-specific local parameters: USD currency, July–June fiscal year, USD 250K ICB competitive threshold, USD 10M mega contract threshold, 4% base rate corruption prevalence, 'more_likely_than_not' evidentiary standard (WB Sanctions Board civil-administrative, distinct from US/UK criminal). Global params reference mjpis_draft_v0 (WB INT uses the living MJPIS standard as an intersection jurisdiction). 11-key canonical legal_citations with WB Group equivalents: WB Procurement Regulations + Anti-Corruption Guidelines + Consultant Guidelines as procurement_law; SNC-Lavalin/Alstom/Siemens/Macmillan corpus cases as case_authority; WB Anti-Corruption Guidelines §§ 1(a)(i)/(iv) as anti_kickback_law/false_claims_law; WB Sanctions Procedures + April 2010 MDB Mutual Enforcement Agreement as sanctions_debarment_law; UNCAC Art. 16 + OECD Convention + WB Staff Rule 03.01 as foreign_bribery_law. Nine new tests including three-way key parity (US/UK/WB). Import-time sanity check validates WB_INT against mjpis_draft_v0 registry. Shipped at commit `14dfab1`. DOJ regression byte-identical.
- [x] **33. Audit recommendation 5 — Create FRANCE_PNF jurisdiction profile.** Fourth and final operational profile completing MJPIS jurisdiction coverage. France-specific local parameters: EUR currency, December fiscal year (calendar-year alignment), EUR 143K competitive threshold (Code de la commande publique, EU Directive 2014/24/EU), EUR 5.35M mega contract threshold, 2.5% base rate (TI CPI parity with UK), 'french_cjip_admission_of_facts' evidentiary standard (PNF CJIP under Art. 41-1-2 CPP). Global params reference mjpis_draft_v0. 11-key canonical legal_citations with French statutory equivalents: Code de la commande publique + EU Directives + Sapin II as procurement_law; six PNF CJIP corpus cases as case_authority; Code pénal Art. 441-1/441-6/313-1 as false_claims_law; Art. 433-1/432-11/433-2 as anti_kickback_law; Art. 435-3/435-4 + Sapin II + UNCAC as foreign_bribery_law; Cour des comptes + HATVP + AFA as audit_oversight_law; L. 2141 + EU Directive Art. 57 + Code pénal Art. 131-39 as sanctions_debarment_law; Sapin II Ch. II + Loi 2022-401 + Défenseur des droits as whistleblower_protection_law. Ten new tests including four-way key parity (US/UK/WB/FR). Shipped at commit `2274506`. DOJ regression byte-identical. **PHASE E COMPLETE.**
- [x] **34. Audit recommendation 6 — Expand universal_citations to full UNCAC + OECD coverage.** Replaced the 4-item default with a 9-item ordered list covering UNCAC Art. 9(1), 9(2), 12, 15, 16, 17, 18, OECD Anti-Bribery Convention 1997, and OECD Recommendation on Public Procurement 2015. Removed institution-specific dead items (UNDP POPP, OECD Public Procurement Principles, World Bank Procurement Framework) — these belong in per-jurisdiction `legal_citations`, not in universal layer. Removed `[:2]` slice in PROC-001 so the full list propagates. 12 new regression tests. Shipped at commit `8fe487c`. DOJ regression byte-identical.

---

## Critical path

Phase 0 items 1-3 → Phase A items 5-12 (skipping 13 initially) → Phase B items 14-17 (first corpus expansion pass, skipping full derivation initially) → Phase C item 23 → Phase D items 24-27 → send the Scharff document.

Item 13 and items 18-22 can run in parallel with later phases or happen after the Scharff outreach lands. Item 28 is a 3-month track that runs alongside everything else.

**Total critical-path estimate:** Roughly 30-50 hours of focused Claude Code work across Phase A, plus 20-30 hours of research work across Phase B, plus 1-2 hours of strategic writing for Phase C, plus 2-3 hours of personal action for Phase D. Call it 55-85 hours of total effort, spread across 8-15 sessions. Realistic elapsed time: 3-6 weeks if sessions are frequent and focused.

---

## How to use this file

This is the durable source of truth for session planning. When a sub-task ships, mark its checkbox in place and append the commit hash to the item description. Update the "Last updated" and "Current commit on main" fields at the top. The file is the memory anchor that makes drift visible the moment it happens — if a session starts producing work that is not on this list, the work either belongs on the list (add it explicitly) or it does not belong in the session (defer it).
