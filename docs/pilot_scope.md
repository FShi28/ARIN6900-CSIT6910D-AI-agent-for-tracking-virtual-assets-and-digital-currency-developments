# Phase 1 Pilot Scope

Design date: 2026-10-14. This document preserves the initial design baseline. By 2026-10-16, topic-page press-release discovery, batch ingestion and HTML change detection were implemented, with two real PDFs and ten HTML documents. See the [source registry](source_registry.md) and [ingestion guide](ingestion.md) for current capabilities. The 10-20-document sample target and read-only database queries are complete; MAS onboarding and semantic retrieval remain pending. References to unimplemented components below describe the original design baseline.

This phase establishes the architecture, database and preprocessing foundation scheduled for October 2026 in the proposal. The pilot covers Hong Kong stablecoin regulation, starting with HKMA to validate one traceable pipeline before extending to MAS.

## Repository Baseline and Gaps

Reviewed materials: `Project proposal v2.docx`, `README.md`, `src/app.py`, `data/canonical/` and the three `skills/regulatory-*/SKILL.md` files. No applicable `AGENTS.md` was found in the repository or its ancestor directories.

| Area | Original baseline | Design decision |
|---|---|---|
| Streamlit | Four pages reading local JSONL/CSV files | Preserve the interface; defer database integration |
| Regulatory examples | Four documents, four chunks and four developments; all fictional | Do not import into the real database |
| Market examples | Three fictional observations | Exclude from the regulatory pilot |
| Questions and answers | Keyword substring matching | Defer RAG and model integration |
| Review labels | Fixtures contain `critic_checked`; the UI displays `All critic-checked` | These do not represent real review; correct them before using real data |
| Provenance | Example URLs, hashes and text paths without corresponding originals | Establish original-version, processing-version and chunk references |
| Ingestion and storage | No collector, parser, SQLite implementation, scheduler or tests | Initial design delivery: documentation and executable DDL |
| Field conventions | Examples use `publication_date`, `retrieved_at` and jurisdiction abbreviations; skills use different names | Standardize through the data dictionary and document legacy mappings |
| Classification conventions | Values such as `primary_regulatory` and `policy_update` differ from the skills | Map explicitly; retain unknown values where meaning is uncertain |
| Proposal coverage | Eight jurisdictions in the description; US regulators also appear in the methodology | Limit the pilot to Hong Kong, with MAS as the next source |

## Pilot Boundaries

| Dimension | Decision |
|---|---|
| Jurisdiction and regulator | `Hong Kong` / `HKMA` |
| Asset | `stablecoin`; labels require body-text evidence and cannot be inherited from the source topic |
| Topics | Reserve assets, custody and segregation, redemption, licensing requirements and implementation dates |
| Materials | Official HKMA English HTML and text-based PDFs, including consultations, guidelines and announcements |
| Initial set | Topic page and directly relevant official documents within a manually confirmed boundary; no unrestricted site crawl |
| Time range | Initial backfill from 2022-01-01 to the first actual run date, followed by discovery of new or updated files; retain undated documents for separate review |
| Sample target | 10-20 distinct relevant documents across HTML/PDF; report the actual count if fewer are available |
| Resource granularity | One canonical URL per resource; preserve HTML announcements and PDF attachments separately, with discovery context in parent_url |
| Storage | Original bytes in files; metadata, text, processing results and chunks in SQLite |
| Execution | Start with manually triggered CLI runs; add scheduling later |

The initial design delivery excluded collectors, parsers, NER, RAG, agents, MCP, market data and UI integration. OCR, translation, legal-effect inference and complete table-structure extraction are outside the first ingestion POC. Retain original PDFs and physical page references for tables; record extraction limitations rather than treating misordered numeric content as reliable evidence.

## Source Verification and Onboarding Plan

The following official resources were checked by web access on 2026-10-14. This established that the resources were readable, not that the project's collector, selectors, download policy or parser had passed testing.

| Source | Verified resource | Purpose and status at design time |
|---|---|---|
| HKMA | [Regulatory Regime for Stablecoin Issuers](https://www.hkma.gov.hk/eng/key-functions/international-financial-centre/stablecoin-issuers/) | HTML discovery entry containing guideline and consultation links; collector not yet implemented |
| HKMA | [Guideline on Supervision of Licensed Stablecoin Issuers](https://www.hkma.gov.hk/media/eng/doc/key-functions/ifc/stablecoin-issuers/Guideline_on_supervision_of_licensed_stablecoin_issuers_eng.pdf) | Opened from the topic page; readable text-based PDF for parser implementation |
| MAS | No endpoint verified in this phase | Reserve `Singapore` / `MAS` source identity only; keep disabled |

The planned approach uses topic-page HTML discovery and separate downloads. No suitable API/RSS feed was verified. The implementation phase creates `config/sources.yaml` and `docs/source_registry.md`, checking access rules, target URLs, redirects and historical coverage. Sources start with `enabled=false` and are enabled only after collector acceptance. The schema does not insert source seed records.

## Acceptance Criteria

Initial design acceptance:

- Deliver the four design files, with consistent architecture and entities; define field types, nullability, provenance and constraints.
- Create an empty SQLite database successfully; verify keys, uniqueness, original versions and reprocessing behavior.
- Trace chunks through extractions, original versions, documents and sources; repeated originals must not create duplicate versions.
- Distinguish SQL constraints from application validation; SQL tests alone do not establish live ingestion success.
- Preserve the existing UI, example data and user changes; design validation must not create or modify production data.

Subsequent ingestion acceptance:

- Complete discovery, download, parsing, cleaning, normalization, validation and persistence for HKMA.
- Preserve a readable original, real SHA-256, official URL, collection time and processing version for every successful result; unknown dates remain NULL.
- Two identical runs must reuse documents, original versions and processing results; source-byte and processing-rule changes preserve separate history.
- Review titles, URLs, date evidence, text and chunk locations across the sample; PDF references use physical pages and HTML references use body or character locations.
- Log source, URL, stage, error type and diagnostics for failures, with isolation between eligible documents.
- Pass fixture parsing, duplicate persistence and a real end-to-end smoke test; report actual successes, failures and limitations.

MAS onboarding follows successful HKMA end-to-end acceptance, reusing the shared parsing, validation and storage modules with a new source configuration and collector.
