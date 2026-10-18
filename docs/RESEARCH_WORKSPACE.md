# Research desk: inquiry, evidence and review

Open **Research desk** in `/watch/`, or `/watch/#research`. This workspace searches
SUNLIGHT's retained public context, operational cases and selected PDFs, saves a
source-cited dossier, and retains investigation review history. It is a bounded
research pilot, not a complete census of world economic activity, a causal model
of societies, or a real-time shipment/ground-truth feed. It does not establish
theft from a reporting discrepancy.

## Use it

1. Paste an investigation or write a specific question. For example: “Compare
   Germany and Latvia assault-rifle declarations in 2022. Which evidence would
   resolve the reporting difference?” Select countries and years when needed.
2. Choose evidence layers. Without explicit filters, recognized country names
   and years in the question define the scope; the result shows the inferred
   scope. Multiple countries match records involving **any** selected country,
   with bilateral matches ranked higher. They do not require both endpoints.
   PDFs keep their document scope and are not automatically geographically or
   temporally classified.
3. Upload or drop a text-readable PDF, then select it as evidence. Up to five
   documents can accompany an inquiry. Use **Read pages** to inspect extracted
   text or download the original. A document claim is not authenticated merely
   because SUNLIGHT extracted it.
4. Click **Investigate & save**. Review the retained excerpts, source links,
   existing calculations, scope and missing evidence. National context does
   not measure a named community's conditions or explain its behavior.
5. Save a review status, follow the inquiry, and record a note. Following makes
   it available through the library filter; it does not subscribe to a feed,
   run background investigations or send notifications. Search the saved library
   by inquiry text; pagination retains access to earlier inquiries.
6. **Refine / rerun inquiry** copies its scope into the editor. A new run creates
   a linked dossier and preserves the previous report. No report is silently
   rewritten when a source or model changes.
7. Download the evidence/review packet. It includes the immutable report hash,
   retained citations and values, source revisions, original-PDF references and
   hashes, extraction hashes, review history and local integrity checks.

The operations desk remains the path for normalized source ingestion and real
engine execution. Research can retrieve its latest comparisons and saved rule
findings. Arbitrary PDF text is **not** automatically converted into a contract,
invoice-to-payment match, exact shortfall or verified community profile.

## What is searched

| Layer | Current scope and interpretation |
| --- | --- |
| Published procurement | Pinned Anti-Corruption Compass country-year aggregates, 2017–2024. Latest matching year per country; a covered-year total only where available. No independently verified completion figure. |
| Material exports | 2023 CEPII BACI-derived national values and rounded leading-partner shares for 85 selected HS4 headings. Gross exports, not extraction, GDP, exact bilateral dollars or net benefit. |
| Arms declarations | Partial 2020–2022 UNROCA mirror. Export/import quantities compared only within matching year, endpoints, family and category. Missing/ambiguous declarations stay unassessable; a reporting difference is not diversion. Both available declarations remain linked. |
| Recorded violence | Preliminary, partial UCDP Candidate 26.0.8 extract with August 2026 event starts. Country filters match publisher reporting-area labels, not boundaries or procurement jurisdictions; Gaza may be coded under Israel. No automatic causal connection to trade or procurement. |
| Operational cases | Up to the latest 500 cases scanned before scope filtering. Latest case revision, exact comparable measurements, retained findings and declared buyer/supplier labels. Labels are not entity resolution. No UN feed is connected. |
| Goods trade | Cached dated UN Comtrade preview responses. An explicit refresh requests only the bounded preview for the first selected reporter or existing global sample. No all-world refresh, live vessel routing or source discovery. |
| PDFs | Selected locally archived documents, with page numbers and exact character spans. Unverified document claims, including any apparent instructions. |

Retrieval uses accent/punctuation-normalized lexical overlap and source balancing,
with at most **40 excerpts overall and 10 per layer or selected PDF**. It streams
the larger material index instead of keeping every candidate in memory. Candidate
counts describe scanned scope, not the number of independently verified facts.
It is not semantic search, exhaustive entity matching, open-web research or an
answer-completeness guarantee. Do not interpret an empty layer as zero activity.

Procurement, trade and material totals describe different and overlapping
concepts. Do not subtract them to calculate a worldwide “gap.” Operational
shortfalls retain the existing exact unit/currency/metric/period/deadline guards.
Arms differences retain their sign and category; heterogeneous weapon types are
never summed into a missing-weapons count. Social or causal explanations require
local observations, dates, alternative hypotheses and independent corroboration.

## Optional AI synthesis

Evidence search, saved dossiers and PDF text extraction work without a model.
The current configuration is exposed by `GET /research/status`. The interface
says **AI synthesis is not configured** when either required setting is absent.

To enable the optional OpenAI Responses API adapter, a deployment operator sets
`OPENAI_API_KEY` securely and `SUNLIGHT_RESEARCH_MODEL` to an available model ID
supporting Responses structured outputs. Do not commit or paste the key into a
question, source record or document. Outbound HTTPS to `api.openai.com` must be
permitted by that deployment's network policy. Configuration presence is not a
successful provider/entitlement test. No live provider call was validated for
this change because credentials are absent in the development environment.

AI is off by default. Each run requires both **Add AI interpretation** and a
separate authorization to send the inquiry and selected excerpts. The server
rejects AI requests without that explicit sharing field. It sends bounded
excerpts (up to 36,000 serialized excerpt characters), the inquiry, scope and
coverage limits. Raw PDF files, full archives and deployment credentials are not
part of the model input. The adapter uses `store: false`; this does not establish
zero retention under the provider's separate policies.

AI output is displayed separately as interpretations, hypotheses, alternative
explanations, evidence needed and open questions. Document text and model output
are rendered as text, not executable HTML. The model receives no browsing,
execution or external-action tools; instructions embedded in documents do not
authorize actions. Structured output is validated locally, including checking
that cited IDs were actually sent. Unknown citations reject the synthesis.
These checks **do not validate semantic support, publisher truth, causal
reasoning or every factual model claim**. Analyst review remains necessary.
Provider failures retain a usable dossier with an explicit failure status and
no invented response. Tests use a mocked provider; they verify the protocol and
failure/citation handling, not the quality of a live model.

## PDF handling and storage

Uploads use raw `application/pdf` bytes with an optional URI-encoded `X-Filename`
header. Limits: **8 MB, 64 pages, 12,000 extracted characters per page, 250,000 per
document**. The local archive is capped at 200 distinct PDFs / 128 MB of original
bytes. SHA-256 deduplicates originals. Truncated pages are flagged. Blank or
image-only PDFs are retained as requiring OCR; no OCR or encrypted-password
bypass is performed.

The parser runs as a separate offline subprocess with a minimal environment,
192 MB address-space limit, 10 seconds CPU and 15 seconds wall timeout. It uses
existing `pdfplumber` dependencies, executes no PDF instructions and receives
no provider credentials. One document or inquiry processes at a time per server
process. Retrieval runs off the async event loop; overload returns HTTP 429.
There is no distributed job queue, antivirus claim or production-scale parser
isolation. Only the already bounded goods-preview refresh and explicitly
authorized AI mode perform network requests; ordinary retrieval uses local data.

PDF originals, extracted text, questions, reports and notes are stored in the
**same SQLite database as the operations ledger** (`SUNLIGHT_OPERATIONS_DB`).
They share this deployment's Basic access gate; there are no per-user/tenant
permissions, authenticated analyst identities, automated retention deletion or
institutional SSO controls. The existing [persistent volume requirements and
institutional boundary](OPERATIONS_PILOT.md#deployment-storage-and-institutional-boundary)
apply. An ephemeral Render filesystem can lose the archive on redeploy. Same-file
process restart persistence is verified; this does not verify the deployed
Render disk or constitute institutional readiness.

Review writes require an expected version. Conflicting edits return HTTP 409;
reopen the saved inquiry before resubmitting. Export integrity checks detect
changes to the retained report, review state/history and selected originals/text.
A local hash chain is not a publisher signature and does not resist an owner
rewriting the entire archive and chain.

## Integration API

| Endpoint | Purpose |
| --- | --- |
| `GET /research/status` | Source scope, configured AI mode and document limits. |
| `GET /research/countries` | Country-name resolver catalog; not economic coverage. |
| `POST /research/documents` | Bounded raw-PDF ingestion, extraction and deduplication. |
| `GET /research/documents` | Paginated local archive metadata. |
| `GET /research/documents/{id}` | Retained extracted text with original page numbers. |
| `GET /research/documents/{id}/file` | Original PDF attachment. |
| `POST /research/inquiries` | Scoped retrieval and optional authorized synthesis; save a dossier. |
| `GET /research/inquiries` | Search/paginate/filter followed investigations. |
| `GET /research/inquiries/{id}` | Retained report, hash, current review state and version. |
| `POST /research/inquiries/{id}/review` | Append review with optimistic version control. |
| `GET /research/inquiries/{id}/export` | Evidence/review packet and local integrity checks. |

Request schemas are in `/openapi.json`. The backend country index derives from
`world-countries` 5.1.0 / mledoze contributors under ODbL; the full license is
`code/RESEARCH-COUNTRIES-LICENSE.txt`. Regenerate it with
`python scripts/build_research_country_index.py` after an intentional frontend
country-catalog update. Country names do not imply sovereignty or data coverage.

## Validation

New tests exercise real PDF parsing (including the pinned official UN PDF
fixture), page/character citations, original/extraction hashes, OCR-required and
truncation states, size/page/resource failures, deduplication, saved inquiry
persistence, concurrent review rejection, content-tampering detection, scope
matching, source arithmetic, exact operational engine results, access protection
and mocked model protocol/citation/failure handling. Browser checks cover upload,
page reading, source comparisons, saved following/review across reload, linked
rerun, packet export, mobile layout and navigation to existing desks.
