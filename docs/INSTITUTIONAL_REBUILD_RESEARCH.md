# SUNLIGHT: institutional economic watch and investigation architecture

Research and product brief · 19 October 2026 · Application baseline: 615611f

## 1. The conclusion

SUNLIGHT needs one shared economic evidence model behind its geographic watch, investigative assistant, case register and institutional actions. Separate screens around disconnected snapshots cannot provide that experience. The central object should be an attributable flow or claim, connected to its parties, places, dates, documents, related stages and review state.

Global watch should be the primary spatial workspace. A question, selected country, connection or investigation should establish a shared scope. The assistant, results table, timeline, evidence reader and case brief should all follow that scope. Analysts must also be able to maximize a table, document or case without losing the map selection. A globe is valuable for orientation; institutions still need precise tabular and documentary work.

The ambition should cover every relevant economic domain. Completeness must be earned source by source: no public source establishes every payment, shipment, arms transfer or private financial movement worldwide in real time. Published statistics, transaction records, estimates, declarations and independently corroborated delivery are different evidence classes. A live software session can continuously ingest new publications without implying that an annual statistic is a current shipment.

Research supports three immediate changes in direction: unify the underlying evidence and scope; replace decorative flow animation with a disciplined directional encoding; replace raw-data intake and JSON-first exports with guided records and readable case briefs. Genuine investigative intelligence requires tools that query, join, calculate and inspect evidence, together with a suitable model and evaluated workflows. A model summarizing a fixed excerpt list is insufficient.

This document describes proposed requirements. It does not establish implemented capabilities, institutional approval, live source availability or verified wrongdoing.

## 2. What was examined and what remains unverified

The review examined the current application code and charter, official OCDS schemas, IATI schemas and transaction codelists, UN Comtrade's official client documentation, OCHA's HDX HAPI documentation, the World Bank's public Data360 API specification, Open Ownership's BODS, SDMX REST documentation, W3C PROV and WCAG criteria, visualization-library documentation and an official tool-calling example. References S1–S14 identify the materials and their relevance.

Eight official repositories were cloned at recorded commits. Additional retrieved documents have local copies and SHA-256 hashes. Retrieval manifests accompany this brief. Development branches are documentation snapshots, not assertions that their features are deployed by every provider. In particular, the reviewed HAPI branch is `dev`, SDMX capabilities depend on each provider's implementation, and visualization GlobeView is explicitly experimental.

Direct HTTPS access to the OCDS and IATI documentation websites and the UN Comtrade API was denied by this environment's network policy. Their accessible official repositories were used instead. No attempt was made to bypass that restriction. Current endpoint availability, subscription entitlements, live records, latest publication coverage and redistribution rights still need validation with the actual providers. IMF/BIS financial datasets, SIPRI/UNROCA current public reporting, EITI disclosures, national treasury feeds and World Bank loan ledgers are identified integration candidates; they have not been live-validated in this review.

The World Bank's public Data360 specification was read. It describes metadata, indicators, data, disaggregation and search. It does not establish access to a live bank-payment ledger. No confidential institutional system was accessed.

## 3. Why the current experience falls short

| Observed implementation | Consequence | Required correction |
| --- | --- | --- |
| Operations is the default tab; map, research and session analysis have separate state and entry points. | The global context is lost when work moves between desks. | Shared scope and selection, with watch as the primary entry and persistent investigative panels. |
| Each flow completes the same 1.8-second visual lap regardless of value, reporting year or physical movement. | Movement looks like repeated particles and conveys no economic rate. | Explicit directional encoding; event playback only when timestamps exist; no implied shipment speed. |
| The map draws selected subsets: goods, material and arms layers have separate drawing budgets. | Visible routes can be mistaken for all activity or relative importance. | Server-side aggregation and explicit visible-versus-matching counts; complete paginated results within the queried source scope. |
| Sources include procurement aggregates for 2017–2024, materials for 2023, arms declarations for 2020–2022 and a partial August 2026 conflict extract. | A single screen can appear current while combining different periods. | Visible source periods and common-period filtering; distinguish mixed-period context from a comparable view. |
| Goods, materials, arms and procurement use different meanings, units and completeness. | Combining them can create double counting or meaningless totals. | Typed measures, overlap relationships, classifications and aggregation contracts. |
| The assistant receives at most 40 lexical excerpts and has no query/calculation tools. | It can summarize a sample but cannot systematically investigate an economic chain. | Permission-scoped tools, broader retrieval, entity and event joins, deterministic calculations and answer evaluation. |
| Intake requires normalized JSON; main export actions download JSON packets. | Operators must understand schemas to do ordinary work and cannot readily hand a brief to a reviewer. | Guided forms, validated spreadsheet/PDF intake, readable reports, document viewers and optional technical exports. |
| Shared Basic access, local SQLite, no verified persistent hosting volume or connected institutional payment system. | Current deployment is a pilot rather than an institutional control environment. | Durable storage, identities, source permissions, independent review, operational monitoring and authorized connectors. |

Code anchors: EvidenceWorkspace.jsx (default/tab layout); EvidenceGlobe.jsx (flow assembly and drawing budgets); flowMotion.js (visual lap); FlowCanvas.jsx (fixed heads/glow); research_evidence.py (lexical retrieval); research_ai.py (excerpt-only synthesis); OperationsDesk.jsx and FlowInspector.jsx (JSON intake/exports). These findings describe the checked-out baseline, not a live inspection of the password-protected Render deployment.

The existing exact operational comparisons, source versioning and content hashes are useful foundations. Their existence does not establish end-to-end financial reconciliation, authenticated publisher identity or legal authority to intervene.

## 4. The coverage strategy: broad domains, explicit source contracts

Every connector needs a publisher, dataset identity, source URL, license/access basis, geographic and temporal scope, measure definitions, granularity, revision strategy, expected publication schedule, actual last publication and ingestion times, and a known-gap record. Those attributes must be queryable and visible, rather than hidden in a technical disclaimer.

| Domain | Candidate primary sources and standards | Useful representation | Critical limitation and next validation |
| --- | --- | --- | --- |
| Procurement and public spending | National OCDS publishers, treasury/open-spending records, USAspending; UN/UNGM public procurement publications; institution-authorized ERP feeds. OCDS schema reviewed [S1]. | Planning, award, contract, implementation transaction, milestone, acceptance and payment as separate events. | An award amount is not a bank payment; a national aggregate is not a set of verified deliveries. Validate publisher exports and update completeness. |
| Merchandise, commodities and energy goods | UN Comtrade final/bulk data and availability metadata; licensed national customs sources. Official client documentation reviewed [S4]. | Reporter–partner–product–period values and quantities, with classification and valuation basis. | Statistical goods trade does not directly trace payments or transport paths. Final observations and estimated trade-matrix values must remain distinguishable. |
| Services trade | Relevant official UN/national/SDMX statistical datasets; dataset identity and bilateral coverage require validation. | Service category, reporter/counterparty and reporting period. | Frequently aggregate and delayed; no inferred individual invoice or procurement contract. |
| Aid and development finance | IATI publishers, OECD CRS, institution project/finance disclosures. IATI schema and codelists reviewed [S2–S3]. | Commitment, incoming funding, disbursement, expenditure, loan repayment, interest and results, separately typed. | The same money can be reported by donor, intermediary and recipient and again as expenditure. Link stages and publishers before totals. |
| Humanitarian requirements and funding | OCHA FTS and HDX HAPI. HAPI funding fields and documentation reviewed [S5]. | Appeal requirement versus reported funding for the same appeal and reference period. | A funding requirement shortfall is unmet financing, not stolen funding or a delivery gap. Reviewed HAPI funding documentation specifies annual updates; validate direct FTS access for finer freshness. |
| Public debt, lending, investment and banking statistics | World Bank loan/finance disclosures, national debt offices, IMF, BIS and national statistical sources; SDMX where supported [S8]. | Commitments, disbursements, debt service, outstanding stocks, investment flows and positions as distinct measures. | Outstanding debt and portfolio positions are stocks; changes include valuation and reclassification. API/schema access and each source's methodology remain to be validated. |
| Arms | UNROCA, ATT public reporting, national export reports, SIPRI and attributed field-tracing reports. | Authorization, order, declared transfer, delivery and recovery/tracing evidence as separate assertions. | Licenses are not deliveries; counts, monetary values and SIPRI trend-indicator values are not interchangeable. No serial-level recovery location is inferred from a national declaration. |
| Domestic fiscal activity | National budgets, execution/treasury, transfers, procurement payments and resource-revenue disclosures; fiscal specifications offer structural guidance [S14]. | Revenue, appropriation, commitment, payment and balance, with accounting basis. | Domestic flows may have no cross-border line. Cash and accrual measures must not be silently combined. |
| Ownership and accountable entities | Authorized company/ownership registers, BODS, authoritative organization identifiers and dated sanctions lists [S7]. | Versioned claims about parties and relationships, with legal role and validity dates. | Similar names do not establish identity; ownership or a list match does not establish wrongdoing. Respect source restrictions and resolve matches for review. |
| Societies, need and operating conditions | HDX HAPI/HDX, WFP prices, IPC, displacement, population and national statistical sources; UN SDG metadata [S5, S6, S13]. | Context panels, local reference periods, source-specific administrative units and analysis status. | National values cannot explain an individual community. Stocks of displaced persons cannot be summed over reporting rounds as new flows. IPC projections need a projected label. |
| Private payments and commercial logistics | Contracted payment/customs/ERP feeds, settlement providers and licensed shipping/transport sources. | Actual authorized transaction or position observations, with explicit visibility. | General public access is unavailable for much private activity. A vessel position does not establish cargo ownership, invoice settlement or destination receipt. |

The public product should maintain a coverage catalog across all countries and domains, including inaccessible or absent datasets. Economic activity must not disappear conceptually because a source is missing. Conversely, a country marker or source candidate does not justify drawing an invented flow.

“Every published flow” is a discovery and coverage objective, not a completed fact that can be certified from an incomplete source registry. The practical contract is every successfully ingested and licensed record within a declared scope, plus a clear register of known missing coverage.

## 5. The common evidence model

A flow is not simply two coordinates and a number. The minimum model needs:

- Identity: source record ID, publisher, dataset, revision and stable internal ID; relationships linking updates, duplicates and related economic stages.
- Meaning: domain, event type, instrument, legal stage, commodity/service classification and whether the value is a flow, stock, commitment, estimate or requirement.
- Parties and places: provider/payer, recipient/payee, buyer, supplier, transporter and beneficiary roles, each with identifiers and sourced geographic basis. Registered office, customs territory, physical destination and beneficiary place are distinct.
- Measures: original amount and currency, physical quantity and unit, valuation/accounting basis, explicit conversion method where used, and reporting precision. Preserve original values and exact decimal arithmetic.
- Time: event date or interval, publication date, ingestion date, validity period, revision time and due date. Store date precision; a year-only record must never acquire an invented day or second.
- Evidence: document/page/table/row locator, original hash, extraction method, source version, publisher claim, corroborating and conflicting assertions, and access classification.
- Assessment: applicable rule and version, comparability result, calculation inputs, remaining uncertainty, reviewer and case linkage.

Use a graph of assertions: a source makes a claim about a party, event or relationship. Retain conflicting claims and revisions rather than overwriting them with a single model-generated truth. BODS models statements as dated source claims; PROV distinguishes entities, activities, agents, attribution and derivation [S7, S9]. These are good precedents, not proof that any ingested claim is correct.

Entity resolution should prioritize verified identifier schemes, then source-backed crosswalks, then reviewable candidate matches. A fuzzy name match must remain provisional. Geographic identifiers need a version: HAPI explicitly notes that p-codes can be reused across reference periods [S5].

Reproducibility needs two histories: what was reportedly true at an event time, and what SUNLIGHT knew when an assessment was made. A later customs correction or changed acceptance record should update the current result while preserving the earlier brief. SDMX describes historical and incremental-query mechanisms; support must be tested per provider [S8].

A universal total must not add goods exports, their material subset, an arms subset, commitments, disbursements and expenditure of the same funds. Aggregate only within compatible measures and documented partitions. A reconciled total is a derived result with its own source lineage and coverage denominator.

## 6. What the globe should communicate

The design goal is legible economic relationships, explicit direction and immediate access to evidence. More points alone do not achieve this.

### A. A persistent operating surface

The default view should combine the globe, a compact scope bar, selected-layer controls, a time basis, coverage/freshness summary, an investigation panel and a linked results table. A saved investigation stores the same scope and filters. Selecting a table row highlights its map relationship; selecting a country filters the table and assistant tools. Unknown or unlocated records remain in the table.

Global view should aggregate by country or region and domain. Country view should reveal counterparties and sectors. Corridor view should reveal products, organizations and comparable stages. Case view should show documents and actual calculations. Domestic flows should appear in a country-local view or self-relationship summary; they must not be turned into fictional international arcs.

The map should display all matching records through defensible aggregation, while the full matching register remains paginated and searchable. Show matching, represented and unlocated counts. Rendering every transaction as an individual mark is neither an institutional requirement nor a credible completeness guarantee.

### B. Direction before decoration

Use fine, crisp connections with repeated directional chevrons or a restrained moving directional texture. Selected routes should have clearly different origin and destination symbols, endpoint labels, an arrow and a pinned evidence card. Inbound and outbound selection should be explicit. Opposing flows need offset paths or distinct inspectable directions.

Avoid glowing beads, large halos and an endless identical “shipment” loop on every annual observation. When direction is the only temporal information, animation can communicate direction while a visible mode label says it is directional animation. Discrete publication updates should appear as received events. Event playback must use actual dates or dated intervals at their recorded precision. Actual vehicle trajectories belong to a separate tracking layer with actual position timestamps.

Goods exporter → importer does not establish money payer → payee. Payment flows often pass through financiers, intermediaries and different countries. Draw a reverse money relationship only when its own evidence exists. A country-to-country geodesic is a schematic relation; do not describe it as the physical shipping path.

### C. Visual encodings with a contract

Use a small categorical palette with an explicit legend. A candidate palette is amber for public spending, teal for goods, violet for aid/development finance and a distinct blue for arms. Materials should generally be a selectable subset of goods, rather than an independently additive world economy. Keep neutral outlines for coverage and source availability. Reserve red/amber assessment badges for defined statuses; use a separate symbol/overlay for recorded violence. These palette choices require perceptual and institutional user testing.

Color cannot carry the meaning alone. Couple it to layer names, symbols, line styles and accessible tables [S10]. Financial widths may represent a disclosed comparable value scale. Quantities of weapons, percentages, people and monetary amounts must not share one width legend. If clipping or a log scale is used, disclose it; opacity is not an undocumented confidence score.

The map needs separate controls for publication time and event/reference time. An annual report ingested today remains an annual report for its covered period. Cross-layer comparisons should offer the intersection of compatible periods and explicitly mark mixed-period context.

### D. Rendering and accessibility

A GPU-based globe/flow renderer is a reasonable technical direction once data semantics and aggregation exist. Benchmark against the existing Canvas implementation. Candidate library documentation supports arcs, picking and timestamped paths, but deck.gl's GlobeView is experimental, and TripsLayer has timestamp precision and globe-culling caveats [S11]. Do not switch libraries on appearance alone.

Proposed acceptance targets, not current measurements: responsive selection under 200 ms for already loaded summaries; p95 frame interval under 33 ms on an agreed baseline laptop; no silent omission of source results; visible loading/error/freshness states; keyboard-accessible alternatives. Define device, dataset and network conditions before claiming performance.

For institutional accessibility, provide motion control in preferences and reduced-motion support, even if routine watch operation animates by default. WCAG's automatically moving/updating content criterion requires a pause/stop/hide or frequency mechanism where applicable; fast animation is not an exception merely because it is visually attractive [S10]. Reading a document should hold the investigative camera steady.

## 7. The investigative intelligence

The assistant should operate on the same selected scope and evidence graph as the globe. It should be able to answer a question, make appropriate read-only tool calls, show the evidence basis, calculate with typed data and preserve a reproducible result. It should expose a concise work log of queries, source versions and calculations, not demand access to hidden model chain-of-thought.

### Required tools

- Discover available sources, freshness, coverage and permissions for a question.
- Resolve entities and places with provisional matches visible.
- Query complete relevant registers with pagination, aggregation and time filters.
- Retrieve documents and cite precise page/table/cell spans, including OCR/extraction qualifications.
- Trace a related chain across funding, award, payment, dispatch, receipt and acceptance records.
- Call deterministic comparison, unit, currency, deadline and duplicate-handling functions.
- Compare original exporter/importer or sender/recipient assertions while preserving reporting basis.
- Save a finding or evidence request into a case with citations and calculation lineage.
- Create a readable brief and update a saved investigation when new source evidence changes it.

Official tool-calling examples illustrate an iterative model → tool → result → model pattern [S12]. That pattern enables the architecture; it does not establish analytical reliability. The application must enforce permissions, query budgets, schemas, row limits and timeouts independently of the model. Default query tools should use parameterized, reviewed operations. Do not grant unrestricted database writes or treat document instructions as authorized tool requests.

Hybrid lexical/semantic retrieval and reranking can improve discovery beyond the current keyword sample. Entity and relational queries should handle exact identifiers and complete result sets. The model should receive relevant results and explicit gaps, rather than assuming the initial retrieved excerpt budget contains the answer. Large quantitative questions should use backend aggregations, not a model adding a handful of search snippets.

For PDFs and spreadsheets, extraction needs tables, numeric locale, unit/currency checks, document dates, duplicate/version detection and exception handling. OCR results require confidence/quality checks and reviewable source images. A quoted total, inferred row or model-extracted party remains a source interpretation until validated. Document extraction and computational verification are separate steps.

### Answer structure

An answer should lead with the narrow answer supported by the data. Then show the scope/time basis; evidence and calculations; contradictions and alternative explanations; what remains unknown; and the next available investigative step. A user should be able to click each substantive factual claim back to the source or computed result.

For example: “Which funded medical-supply cases have accepted delivery below the due quantity in this region?” should query matching operational cases, apply deadline and comparability rules, return all qualifying results with pagination, and provide a ranked review queue with an explained ordering. “Why do mineral exports coexist with local food insecurity?” should return dated regional context and plausible hypotheses to test, identify what local causal evidence is absent, and avoid inferring theft or motive from a map overlap.

The model must be evaluated for numerical correctness, citation support, completeness within scope, entity-resolution errors, stale evidence, missing-data abstention, contradictory sources, multilingual extraction, access-boundary violations and document prompt injection. Add domain expert review. A count of passing application tests is not a measurement of investigative answer quality.

Credential configuration is one dependency, not the complete intelligence upgrade. Model selection, deployment/data-sharing policy, tool orchestration, source coverage and an evaluated answer set are all required. Institutional settings should establish permitted providers and data classes; avoid forcing an analyst to understand API secrets during ordinary work.

## 8. A gap is a typed assessment, not one universal number

| Gap type | Valid comparison | What it establishes |
| --- | --- | --- |
| Funding shortfall | Requirement and recorded funding for one appeal/period/basis. | Unmet recorded financing requirement. |
| Reporting difference | Comparable sender/receiver declarations with compatible classifications and periods. | A disagreement requiring reconciliation. |
| Due delivery shortfall | Latest valid due baseline versus comparable accepted/observed delivery. | A measured due shortfall on the stated evidence. |
| Documentary gap | A required record or trace absent under a stated rule and evidence search scope. | Missing evidence, not a default zero or proved loss. |
| Cash reconciliation residual | Opening balance + comparable inflows − comparable outflows − closing balance, after recorded authorized adjustments. | An unexplained residual on the defined perimeter; not automatically theft. |
| Custody/trace break | Required linked identifiers or handover evidence absent/inconsistent. | A discontinuity in the documented chain. |
| Outcome/need difference | A plan's stated result/need versus a compatible independently measured outcome. | Difference within that plan's units and evidence, not automatic causation. |

Each assessment needs a comparison perimeter, baseline version, units, period, due rules, valuation basis, adjustments, source independence and review state. Trade mirror analysis additionally needs treatment of valuation, freight/insurance, timing, re-exports, transit, product classification, exchange effects and statistical thresholds. A naive export-minus-import result is not a calculated theft amount.

There should be no global theft counter derived by adding these different gaps. A global review overview can show separately measured exposed value, comparable shortfalls, missing-document cases and unknown coverage, with their denominators and overlap disclosed.

## 9. Human-readable records and review outputs

Ordinary work should not require JSON. A record should open as an institutional case sheet with plain labels, parties, dates, money/quantity measures, stage timeline, evidence viewer, relevant rules, exact calculations, unresolved questions, reviewer and actions. Advanced machine exports remain available for integration and independent verification.

Provide structured entry forms and spreadsheet import with column mapping, preview, row-level errors and duplicate detection. PDF intake should show the extracted candidate fields alongside the source and let an authorized reviewer correct them before treating them as structured operational evidence. Imported totals should be reconciled against row counts and known subtotals.

The default export should be a readable PDF/HTML brief; tabular data can also be exported as CSV or a workbook. An advanced audit bundle can retain JSON and original files. Report rendering must preserve the original evidence snapshot, identifiers and exact displayed precision; a polished PDF must not alter a machine receipt's hashed content. Institutional archival/accessibility requirements should be specified with the adopting institution rather than claiming PDF/A or certified accessibility prematurely.

### Example case brief — synthetic, not an observed institution

Case: Medical-kit delivery review. Subject: 10,000 kits due under the current baseline. Scope: one item, one receiving authority, one covered period and one reporting cut-off. Status: evidence review; no finding of theft.

| Stage | Recorded quantity | Evidence and interpretation |
| --- | --- | --- |
| Due baseline | 10,000 kits | Latest approved contractual schedule. |
| Supplier-reported dispatch | 9,800 kits | Supplier dispatch records; claim awaiting independent reconciliation. |
| Receiving-authority receipt | 9,200 kits | Dated receiving records for the same item and period. |
| Accepted after inspection | 9,000 kits | Acceptance certificates; 200 received kits have unresolved acceptance. |

The recorded due-to-accepted difference is 1,000 kits. The chain currently contains 200 not shown dispatched, 600 dispatched without matching receipt, and 200 received without acceptance. These categories reconcile arithmetically to 1,000 only if identifiers, scope, revisions and populations match without overlap. Dispatch/receipt disagreement does not prove physical loss; acceptance delay or rejection must be investigated. Monetary exposure cannot be inferred without compatible contractual valuation, tax/freight treatment and verified item matching.

The readable brief should state the question, concise finding, table above, relevant terms, source locators, exact computation, source disagreements, independent evidence still required and the assigned reviewer. The next action is to reconcile item/lot identities, dispatch and receiving cut-off dates, acceptance decisions and any authorized baseline amendment. A signed technical annex should be introduced only after an actual signing/identity system is implemented.

## 10. Institutional verification and intervention

Public observation, internal verification and authorized intervention are distinct operating modes. Public evidence can identify a review lead. An institutional connector can validate records against internal documents and balances. Stopping or holding an actual transaction requires the institution's mandate, identity controls, connected system and a permitted workflow state.

A future intervention workflow should show: proposed action and grounds; affected transaction and expected version; required approvals; dry-run result; authorized submission; destination-system acknowledgment; confirmed state; failure or permitted reversal/compensating action. A pending instruction must not appear as a successfully held payment. Idempotency, concurrency protection, timeout handling and independent approval must be designed before a live action is enabled.

The model can prepare an evidence-backed action proposal. The institution's permissions and policy engine determine who can approve and execute it. A discrepancy is not sufficient authorization. A completed transfer cannot universally be “stopped”; available controls depend on the financial system and legal stage. No present SUNLIGHT connector supplies those powers.

## 11. Implementation sequence and completion gates

### Stage 1 — shared foundation and operator outputs

Implement the typed source/flow/claim registry, common scope and current-versus-as-of history. Add durable storage and a coverage/freshness catalog. Make global watch the main spatial entry while preserving tabular and document work. Deliver readable case sheets, guided record intake and PDF/HTML exports. Retain exact comparisons and technical evidence bundles.

Gate: one selected country/corridor/case produces the same scope, identifiers and numbers across map, assistant tools, tables and report. An updated source creates a new assessment without erasing the earlier brief. Ordinary operators can complete intake and review without editing JSON.

### Stage 2 — validated source expansion

Build repeatable adapters for actual contract-level OCDS and IATI transaction data, fuller UN Comtrade final/bulk observations, humanitarian needs/funding context, arms declarations and selected institutional data. Register known coverage and exclusions per source. No prototype snapshot should be marketed as a live worldwide feed.

Gate: a representative extraction is reconciled to publisher controls and source totals; pagination, revisions, deletions, limits and duplicate stage reporting are tested. Licensing, credentials and expected update cadence are recorded. An unavailable connector visibly degrades without drawing substitute flows.

### Stage 3 — directional map and real investigative tools

Replace fixed glowing-particle loops with the directional encoding described above. Introduce semantic zoom, server-side compatible aggregation, reliable picking, linked tables and time-basis controls. Integrate the model's bounded tool loop, hybrid retrieval, entity tracing and deterministic calculations.

Gate: analysts can correctly identify direction, measure, period, source and coverage in realistic tasks; complete scoped query results remain accessible beyond rendering limits. The assistant meets a pre-agreed domain evaluation for correctness, citation support, abstention and permission enforcement. Targets must be measured rather than asserted.

### Stage 4 — institutional operations

Deploy institution-approved identity, role/source permissions, durable backups and restore tests, operational monitoring, document retention, restricted-data handling, source agreements and validated adapters. Only then introduce institution-specific approval and action connectors.

Gate: a representative institutional pilot demonstrates source-to-record-to-finding-to-review and, if authorized, action acknowledgment end to end. Independent legal/security/domain reviewers assess the deployment. Adoption by UN entities or the World Bank cannot be guaranteed by an interface or an architectural document.

Do not promise calendar dates or hosting costs until source entitlements, expected data volumes, retention, evaluation and deployment requirements are measured. The current small single-service pilot should not be presumed sufficient for global-scale ingestion and institutional document workloads.

## 12. Technical shape and evaluation

Start with a modular application: connector jobs, raw-document/object storage, a durable relational store with temporal/source identity, explicit domain assessment services, query/retrieval services, model orchestration, map aggregates, case/report rendering and policy-enforced actions. PostgreSQL plus appropriate spatial/search extensions is a reasonable candidate; columnar analytical storage can be added if measured volume demands it. A graph-shaped model does not require choosing a graph database before evaluating query needs.

Use background jobs for fetching and large extraction tasks. Retain raw source responses with checksums and immutable version references, then normalize with documented transformations and quarantine invalid rows. Report source lag, rejected/quarantined rows, changed totals and partial successes. Stream actual new data events to the UI where warranted; a continuously spinning globe is not evidence of a functioning ingestion pipeline.

Acceptance should be task-based: follow a selected flow to its parties and original record; distinguish goods from payment direction; identify a same-period comparable gap; reconcile a revised source; answer a question using complete authorized scope; inspect multilingual PDF evidence; export and independently reproduce a readable finding; restore retained records from backup; and reject unauthorized cross-institution queries/actions. Validate on the intended institutional roles and devices.

The proposed architecture advances the charter's norm–record–trace–action structure while keeping each domain's evidentiary standard. It requires better connected evidence and usable workflows before adding more animated categories.

## Primary references and evidence register

[S1] Open Contracting Partnership, OCDS release schema, Implementation, Transaction, Milestone, Value, party identifiers and Document definitions. Reviewed 1.1-dev commit 7876f2d57223caedc0c7359af9e93a8c8202e8ba. https://github.com/open-contracting/standard/blob/7876f2d57223caedc0c7359af9e93a8c8202e8ba/schema/release-schema.json

[S2] IATI, activity schema 2.03: transactions, dates, provider/receiver organizations, values, locations and results. Commit b4ead00528d3785b336d9847928274c207704deb. https://github.com/IATI/IATI-Schemas/blob/b4ead00528d3785b336d9847928274c207704deb/iati-activities-schema.xsd

[S3] IATI TransactionType codelist: outgoing commitment, disbursement, expenditure, interest and loan repayment definitions. Commit e83832716be342b63e7b9fb9cb694220bd3551b2. https://github.com/IATI/IATI-Codelists/blob/e83832716be342b63e7b9fb9cb694220bd3551b2/xml/TransactionType.xml

[S4] UN Comtrade official API package: preview versus final/bulk access, availability/publication filters, bilateral comparison, and estimated trade matrices. Retrieved 19 October 2026; local copy and hash in retrieval-manifest.json. Numeric access limits describe the retrieved documentation, not verified subscription entitlement. https://github.com/uncomtrade/comtradeapicall/blob/main/README.md

[S5] OCHA HDX HAPI metadata and data-usage documentation, reviewed dev commit 1187a59ff27d4907f779abca5aa3e3433f7eef5c. Funding summary specifies annual update frequency; conflict-event summary specifies monthly series/weekly updates. Metadata explains simplification and versioned geographical codes. https://github.com/OCHA-DAP/hdx-hapi/blob/1187a59ff27d4907f779abca5aa3e3433f7eef5c/docs/data_usage_guides/metadata.md ; https://github.com/OCHA-DAP/hdx-hapi/blob/1187a59ff27d4907f779abca5aa3e3433f7eef5c/docs/data_usage_guides/subcategory_details/funding_details.yaml ; https://github.com/OCHA-DAP/hdx-hapi/blob/1187a59ff27d4907f779abca5aa3e3433f7eef5c/docs/data_usage_guides/affected_people.md

[S6] World Bank, public Data360 API specification v1, data/metadata/indicators/disaggregation/search paths. Commit bbf93b34a3c78948d18f2ae40f5a31e4aa7a45a6. Public specification reviewed; no live query or payment-ledger access established. https://github.com/worldbank/open-api-specs/blob/bbf93b34a3c78948d18f2ae40f5a31e4aa7a45a6/Data360%20Open_API.json

[S7] Open Ownership, BODS 0.4 concepts: dated source statements, entities, people, relationship claims and updates. Commit acdc7fd13db478fb9ed17dbef3e6bf48768cd7ce. https://github.com/openownership/data-standard/blob/acdc7fd13db478fb9ed17dbef3e6bf48768cd7ce/docs/standard/concepts.rst

[S8] SDMX Technical Working Group, REST data queries: dimensions, updatedAfter, includeHistory and asOf. Commit 46bba52cb8a8a21704019f949987ee21adefdd5e. Features require provider-specific conformance checks. https://github.com/sdmx-twg/sdmx-rest/blob/46bba52cb8a8a21704019f949987ee21adefdd5e/doc/data.md

[S9] W3C, PROV Primer, published 30 April 2013: entities, activities, agents, attribution, derivation and revision. Repository commit aa82bd71b6bb1f7b735bf3f7f5b948fae87764f0. https://github.com/w3c/prov/blob/aa82bd71b6bb1f7b735bf3f7f5b948fae87764f0/primer/NOTE-prov-primer-20130430/Overview.html

[S10] W3C WCAG success-criterion source text: Use of Color; Pause, Stop, Hide; Non-text Contrast; Animation from Interactions (AAA). Retrieved 19 October 2026 with local hashes. https://github.com/w3c/wcag/blob/main/guidelines/sc/20/use-of-color.html ; https://github.com/w3c/wcag/blob/main/guidelines/sc/20/pause-stop-hide.html ; https://github.com/w3c/wcag/blob/main/guidelines/sc/21/non-text-contrast.html

[S11] vis.gl deck.gl documentation: ArcLayer, experimental GlobeView and TripsLayer timestamp/GlobeView caveats. Retrieved 19 October 2026 with local hashes. This is implementation documentation, not independent evidence of SUNLIGHT performance. https://github.com/visgl/deck.gl/blob/master/docs/api-reference/layers/arc-layer.md ; https://github.com/visgl/deck.gl/blob/master/docs/api-reference/core/globe-view.md ; https://github.com/visgl/deck.gl/blob/master/docs/api-reference/geo-layers/trips-layer.md

[S12] OpenAI, Managing Function Calls With Reasoning Models, official example. Reviewed for iterative tool orchestration; dated model availability statements in the notebook are not used as current capability claims. https://github.com/openai/openai-cookbook/blob/main/examples/reasoning_function_calls.ipynb

[S13] UN Statistics Division, SDG repository README: high-quality, timely, reliable and disaggregated indicator data and national statistical systems. Reviewed as context, not a current count or dataset-coverage audit. https://github.com/UNStats/SDG/blob/master/README.md

[S14] Fiscal Data Package project README: budget/spending data structures. Reviewed as an older structural reference, not as a current guaranteed provider interface. https://github.com/openspending/fiscal-data-package/blob/master/README.md

Additional exploratory client material: WBGAPI README was inspected but is not used as a normative World Bank statement or as proof of access to transaction records. Failed source lookups and unqueried provider websites are not counted as reviewed primary evidence. Application behavior findings come from source inspection at 615611f; previously passing tests are not presented as a fresh institutional-readiness assessment.
