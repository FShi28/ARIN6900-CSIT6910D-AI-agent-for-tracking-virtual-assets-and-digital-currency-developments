# Regulatory Source Registry

Core coverage extension (2026-11-20): SFC circulars 26EC26 and 25EC44 have
verified HTML ingestion; HKMA banking custody circular 20260527-6-EN and its
20260527-7-EN annex have verified PDF ingestion. All four are primary sources,
with entity/activity scope retained and fixed-URL refresh enabled. SFC current-year circular discovery is now implemented through the public e-Distribution search API (see update below). The 39-check evidence map is in
`config/hk_stablecoin_coverage.json`; generated locations and remaining statutory
gaps are in `data/exports/hk_stablecoins/coverage.md`. Content changes invalidate
the prior evidence review instead of silently asserting current legal coverage.

2026-11-20: bounded daily new-publication discovery is implemented for the HKMA
stablecoin topic page, Charltons Hong Kong newsletters, ASIFMA public search, and
Linklaters Financial Regulation blog search. Configuration is deliberately kept
in `config/hk_discovery.json` because the legacy `sources.yaml` validator supports
only its fixed primary-source schema. Source adapters are in
`src/virtual_asset_agent/collectors/hk_channels.py`; see the [daily collection details](hk_stablecoin_data.md).
All four entry points were live-tested; the second scan added no duplicates.
This is bounded channel coverage, not whole-site or all-professor-channel coverage.

Latest extension (2026-11-19): [Hong Kong stablecoin data](hk_stablecoin_data.md).
The focused catalogue adds official attachments, consultations, circulars and
government responses, plus selected Charltons, Linklaters, ASIFMA and EY full texts.
Its reviewed URLs are in `config/hk_stablecoin_sources.json`; runtime counts are in
`data/exports/hk_stablecoins/summary.json`. This extension uses the existing
research JSON store rather than changing the legacy SQLite schema. The old pilot
counts below are historical. Known missing statutory texts and channel-review
status are explicitly recorded in `config/hk_stablecoin_gaps.json`.

Latest extension (2026-10-28): [four-region pilot](four_region_pilot.md).
MAS, ESMA and FCA now have verified fixed-publication collection, stored in a
separate regional database and shown by the original UI. New-publication
discovery for these three sources remains pending. The HKMA-only counts and
limitations below describe the earlier milestone.

Updated: 2026-10-16. The three original fixed targets remain available alongside automatic topic-page press-release discovery and bounded sequential batches. The real-data sample contains two PDFs and ten HTML documents, twelve in total.

Paths under data/ and logs/ refer to local runtime or historical validation artifacts excluded from the October submission. See the [ingestion guide](ingestion.md) for reproduction.

| Source | Jurisdiction | Type | Current status |
|---|---|---|---|
| Hong Kong Monetary Authority (HKMA) | Hong Kong | primary_regulator | Twelve real documents validated; topic discovery, batches and token-only reuse supported |
| Monetary Authority of Singapore (MAS) | Singapore | primary_regulator | Not implemented; enabled=false; no verified entry point |

## Official Sources and Verification

- Discovery entry: [Regulatory Regime for Stablecoin Issuers](https://www.hkma.gov.hk/eng/key-functions/international-financial-centre/stablecoin-issuers/).
- First PDF: [Guideline on Supervision of Licensed Stablecoin Issuers](https://www.hkma.gov.hk/media/eng/doc/key-functions/ifc/stablecoin-issuers/Guideline_on_supervision_of_licensed_stablecoin_issuers_eng.pdf).
- Second PDF: [Consultation Conclusions](https://www.hkma.gov.hk/media/eng/doc/key-information/press-release/2024/20240717e3a1.pdf).
- HTML: [Consultation conclusions for legislative proposal to implement regulatory regime for stablecoin issuers in Hong Kong released](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2024/07/20240717-3/).

PDF verification records are in tests/fixtures/hkma/provenance.json and provenance_two_documents.json. The HTML announcement and topic entry were verified by download at 2026-10-16T04:06:19Z; snapshots and hashes are recorded in provenance_html.json. Runtime originals and logs are separate. HKMA identifies the collection source, not sole authorship of joint FSTB/HKMA publications.

Fixed mode matches allowlisted links. Discovery validates the topic h1 and related-information list, accepting only official English press-release paths, stablecoin titles and listing dates within scope. Every target must appear in the current topic snapshot. See [discovery and batch ingestion](discovery.md). URL extensions select expected formats; response MIME and content are still checked. Requests are restricted to www.hkma.gov.hk, validating HTTPS/host on every redirect. TLS verification remains enabled, with an explicit User-Agent, a one-second minimum interval, 30-second timeout, at most two retries and a 10 MiB size cap. HTTP 401/403/429 or Retry-After stops access. Local runs use trust_env=false for direct connections without disabling certificate verification.

## Text and Date Rules

| Document | Physical pages | Chunks per extraction | published_at | document_type |
|---|---:|---:|---|---|
| Supervision guideline PDF | 61 | 113 | NULL: cover states only August 2025 | guideline |
| Consultation conclusions PDF | 32 | 51 | NULL: cover states only July 2024 | other |
| Consultation conclusions HTML announcement | Not applicable | 2 | 2024-07-17 | press_release |

PDF parsing retains two verified cover rules. Consultation conclusions has no matching controlled type, so retain other, the original label and unmapped_source_type without extending the enum.

HTML uses the verified `.layout-press-release-detail .content-area` container: title from `.press-release-title`, type from `.press-release-tag`, date only from the direct `.date` child, body from `.template-content-area`, and language from html.lang. Remove scripts, styles and hidden nodes while preserving body-block order, inline punctuation and legal values. Exclude sidebar news, navigation and footers. Missing or ambiguous layout fails explicitly.

metadata_evidence retains original values, CSS selectors and deterministic rules; body.locator identifies the article body. HTML chunks use Unicode code-point ranges in clean_text; pages and unextracted sections are NULL. Missing or unsupported-precision dates remain NULL; invalid full dates reject the result. Never use URL, unrelated body or sidebar dates as publication dates or backfill PDFs from HTML. updated_at/effective_at remain NULL and lifecycle_stage remains unknown because extraction is not implemented, not because the source necessarily omits them. stablecoin labels indicate text-topic relevance only.

## Validation Results

Recorded offline run: `python -m pytest tests -q -p no:cacheprovider`, with 105 tests passing in 96.43 seconds. Coverage includes PDF/HTML regression, incremental comparison, migration, candidate date/path filters, duplicate links, batch limits, shared sessions, document-failure isolation, source-access stopping and new-only behavior.

Initial live discovery found ten press releases: nine not yet ingested and one with an extraction. Two batches successfully processed all ten. The second returned status=reused and change_type=unchanged for every document, adding no documents, evidence versions, extractions or chunks; it added ten HTML observations. A third new-only run found zero pending documents.

- Initial batch: data/discovery/413a44761126433f98646d4e409e8ba1-batch.json.
- Repeat batch: data/discovery/4b38d63902d7411c9959bb38ee2df7e4-batch.json.
- New-only run: data/discovery/4741216712974351940b308473eb5eba-batch.json.

| Entity | Database total |
|---|---:|
| sources | 2 |
| documents | 12 |
| document_versions | 13 |
| extractions | 17 |
| chunks | 417 |
| extraction_asset_classes | 17 |
| html_observations | 22 |

Current extractions contain 185 chunks. Totals include byte versions from earlier HTML rules and historical processing results; no historical records were deleted or overwritten. The first batch created a processing version for the known announcement because the code had changed.

The [sample review](sample_review.md) lists all twelve documents, official URLs, dates and chunk counts. The local data/ingestion/discovery_validation_report.json includes original/observation hashes, processing manifests, date and text locations, historical chunks, foreign keys, integrity_check and repeat-run results. Earlier validation_report.json, html_validation_report.json and incremental_validation_report.json are historical snapshots, not current counts.

Discovery uses schema v2 without another migration. The earlier pre-migration backup is data/ingestion/backups/hkma-before-v2.sqlite.

## Limitations and Next Steps

- Supports relevant English press releases directly listed on the current topic page and the two fixed PDFs. No whole-site, pagination or complete historical coverage. The CLI supports manual execution; the Streamlit workspace now also runs a configurable collection worker (default 24 hours). See [live app](live_app.md).
- Only the verified head csrf_token content attribute is ignored. Other changes such as sidebar updates produce page_changed and preserve a new evidence version. Article, date and attachment changes produce content_changed, not a legal-impact conclusion. Original files and observations continue to grow.
- No OCR, generic cover parsing, reliable table structure, complete section extraction, legal-effect inference or supersession extraction; is_table is NULL.
- Sidebar articles are outside the ingested content; linked attachments are not automatically downloaded. MAS, RAG and agents remain pending. UI integration and app-owned scheduling are implemented.
- The 10-20-document target is met. Read-only lists, literal phrase searches and historical chunk references are implemented; see [queries](query.md). Retrieval evaluation can guide later semantic retrieval. Execution is single-process; concurrency and large historical scans are unverified.

Read-only validation is recorded locally in data/ingestion/query_validation_report.json. All twelve documents and 185 current chunks passed fixed-ID lookup and text-slice checks, with identical database SHA-256 before/after and no new ingestion or processing results.

## Market sources and dashboard integration (2026-10-26)

The original four workspace pages now read real data. Secondary market sources
are registered separately in `config/market_sources.json`: DefiLlama stablecoin
circulation and individual RWA protocol TVL, plus CoinGecko Bitcoin market data.
All three configured market endpoints returned real responses during validation.
Their metrics, refresh intervals, missing-data handling and provenance are defined
in [dashboard data integration](dashboard_data.md). They are not primary regulatory
evidence and are stored separately from the regulatory SQLite database.


## Official discovery extension — 2026-11-20

Six configured discovery channels now include HKSAR Government and SFC.

- Government: official English RSS `https://www.info.gov.hk/gia/rss/general_en.xml`; title and description stablecoin filter, followed by full article validation. The observed feed holds 100 releases spanning approximately two days. It is not a historical archive and downtime or high release volume can cause missed items. Print/ordinary URL variants share a publication identity for discovery.
- SFC: the public e-Distribution app exposes `POST https://apps.sfc.hk/edistributionWeb/api/circular/search`. The endpoint and payload were verified against its published JavaScript and live response. Each run scans the current calendar year, at most six pages of 20 results, with at most eight new bodies ingested. Title filter: stablecoin, or both virtual asset and custody. This does not discover every SFC news release, consultation, or broad AML circular. The RSS endpoint returned 403 and is not used. No access protections were bypassed.
- The live scan read three SFC pages (46 circulars), found one matching already-collected document, and added zero. The government feed contained zero matching releases. Production remains 61 documents and 1,510 chunks.
- Isolated live SFC ingestion checks first-time storage and repeated-run deduplication; government saved-body tests verify extraction, publication date, provenance and persistence.
- Both use the existing 24-hour collection worker. No always-on process or OS task was started. EY remains fixed-link refresh only.
- Run all configured discovery: `python src/hk_discovery.py`. Full HK refresh: `python scripts/collect_hk_stablecoins.py`.
- Implementation: `src/virtual_asset_agent/collectors/hk_official.py`, `src/hk_discovery.py`, `src/virtual_asset_agent/fetching.py`; config remains in `config/hk_discovery.json`, because the legacy YAML registry only accepts its fixed source schema.

2026-11-21: HKMA BRDR public search adapter implemented and live-tested (four pages, 65 search hits, four stablecoin-title English candidates). Added one PDF, second scan no duplicates. Seven scan entries across six publishers; 63 documents after manual SFC 25EC57 inclusion. Full suite 232 passed; corpus validation passed. See work_checkpoint.json for remaining scope.


2026-11-21 additional source review: corpus now 66 documents (30 PDFs, 36 HTML pages), 1,545 chunks. Added KPMG Digital payments, Deloitte Q3 2026 frontier-technology regulatory report, and government LCQ10 Regulation of digital assets (2025-09-10). KPMG and Deloitte remain secondary mixed-context sources, not Hong Kong-only rules; publication day unknown, never inferred from URL. They have fixed-link refresh but no new-article discovery. Duplicate saves returned reused. Eight relevant parser/export tests passed. Ashurst old article now resolves to a generic migrated Insights directory; DLA returned 429; neither admitted. PwC PDF extraction restrictions and statutory identity/TLS gaps remain. Full previous implementation suite: 232 passed; no pipeline code changed in this source-only extension.
