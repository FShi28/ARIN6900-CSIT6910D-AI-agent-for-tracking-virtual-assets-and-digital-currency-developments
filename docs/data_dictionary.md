# Regulatory Data Dictionary

The original dictionary is version 1, with the schema v2 HTML-observation extension documented below. It follows [schema.sql](../db/schema.sql). Fields use snake_case and entity-specific keys such as document_id, not a generic `id`. Store canonical values; translate interface aliases through an adapter.

## General Rules

Provenance: **S** = official source/response fact; **C** = source configuration; **D** = deterministic calculation or system observation; **A** = AI-generated content. SQL types are TEXT or INTEGER. Fields marked not nullable have NOT NULL constraints. JSON is stored as TEXT in metadata_evidence; asset-class lists use an association table.

- UTC timestamps use `YYYY-MM-DDTHH:MM:SSZ`, at second precision, independent of machine timezone.
- published_at, updated_at and effective_at are source-local calendar dates in `YYYY-MM-DD`, not UTC instants. If the exact day is unknown, retain NULL and preserve the original month/year in metadata_evidence. Never invent the first day of a month.
- Empty strings do not represent unknown values. Use NULL for unknown scalars, unknown for lifecycle stage and other for document type. Without reliable asset evidence, insert no association rows.
- Hashes and derived entity IDs are 64-character lowercase SHA-256 values. See the architecture for identity formulas. SQL checks their shape; the application verifies the actual calculation.
- This database stores no AI fields and generates no risk ratings, confidence estimates or review statuses.

## sources

A persisted projection of verified source configuration. HKMA is implemented first; MAS is reserved. Changing a source_id's regulator or jurisdiction would change historical attribution, so the application must prohibit those changes after onboarding. A different regulator requires a new source_id. discovery_url, verified_at and enabled may change.

| Field | SQL type | Nullable | Provenance | Meaning and constraints |
|---|---|---|---|---|
| source_id | TEXT | No | C | Primary key; stable identifier such as hkma, independent of entry URL changes |
| source_name | TEXT | No | C | Official full name: Hong Kong Monetary Authority or Monetary Authority of Singapore |
| jurisdiction | TEXT | No | C | Hong Kong / Singapore; validated against regulator |
| regulator | TEXT | No | C | HKMA / MAS |
| source_type | TEXT | No | C | primary_regulator only in this pilot |
| discovery_url | TEXT | Yes | C | Verified HTTPS discovery entry; NULL if unverified |
| verified_at | TEXT | Yes | D | Actual verification UTC timestamp; do not fabricate second precision from a design date |
| enabled | INTEGER | No | C | 0/1, default 0; 1 requires entry URL and verification time; collector acceptance is application-enforced |

Only persistence-relevant configuration is stored here. Collector names, allowed hosts, timeouts, retries, asset_focus and verification notes remain in `config/sources.yaml`. A readable entry point and an accepted collector are distinct states; see the source registry.

## documents

One row represents a canonical URL within a source. Text and changeable metadata belong elsewhere.

| Field | SQL type | Nullable | Provenance | Meaning and constraints |
|---|---|---|---|---|
| document_id | TEXT | No | D | Primary key; deterministic identity from source_id and canonical URL |
| source_id | TEXT | No | C | Foreign key to sources.source_id |
| source_url | TEXT | No | S to D | Conservatively canonicalized official resource URL; unique with source_id |

## document_versions

One row represents original response bytes for a document; document_id/content_sha256 is unique. A version may be registered after download without a successful extraction.

| Field | SQL type | Nullable | Provenance | Meaning and constraints |
|---|---|---|---|---|
| version_id | TEXT | No | D | Primary key derived from document_id and content hash |
| document_id | TEXT | No | D | Foreign key to documents.document_id |
| content_sha256 | TEXT | No | D | SHA-256 of actual saved original bytes, never a cleaned-text hash |
| downloaded_url | TEXT | No | S | Final HTTPS URL on first acquisition of this version; validate the official host after redirects |
| parent_url | TEXT | Yes | S | Official page where the resource was first discovered; discovery context, not clause evidence |
| raw_path | TEXT | No | D | Repository-relative data/raw/hash.html or hash.pdf; reject absolute paths/traversal and verify the file |
| media_type | TEXT | No | S to D | text/html / application/pdf; check headers and content, not only the extension |
| collected_at | TEXT | No | D | UTC time of first acquisition of these bytes; immutable |
| last_collected_at | TEXT | No | D | UTC time of latest confirmation; initially collected_at and monotonically nondecreasing |

URLs, hashes, original paths and first collection times are immutable. Additional discovery parents and request details go to logs. Logs preserve collection history; last_collected_at is not a substitute for the full audit trail.

## extractions

Only validated successful results are stored. version_id/pipeline_version is unique. Changed processing rules require a new result.

| Field | SQL type | Nullable | Provenance | Meaning and constraints |
|---|---|---|---|---|
| extraction_id | TEXT | No | D | Primary key derived from version_id and pipeline_version |
| version_id | TEXT | No | D | Foreign key to document_versions.version_id |
| pipeline_version | TEXT | No | D | Processing-manifest SHA-256 covering dependencies, rules, chunking and configuration; retain the manifest |
| processed_at | TEXT | No | D | UTC creation time of this result |
| title | TEXT | No | S | Title located in the original; fail if unreliable rather than inventing one from the URL |
| language | TEXT | Yes | S to D | en / zh-Hant / zh-Hans; NULL without evidence; pilot processes English only |
| published_at | TEXT | Yes | S | Explicit document publication date; never a global footer or collection date |
| updated_at | TEXT | Yes | S | Explicit document revision date, not HTTP Last-Modified; cannot precede known published_at |
| effective_at | TEXT | Yes | S | Explicit date applicable to the whole document; not inferred from publication or stage; future dates allowed |
| document_type | TEXT | No | S to D | Controlled type mapped from explicit labels; other without reliable evidence |
| lifecycle_stage | TEXT | No | S to D | Explicitly supported regulatory stage; unknown otherwise; not a legal-validity conclusion |
| raw_text | TEXT | No | D | Nonempty text extracted before cleaning; distinct from original HTTP bytes |
| clean_text | TEXT | No | D | Nonempty full cleaned body preserving clause content/order; NUL prohibited |
| metadata_evidence | TEXT/JSON | No | S to D | JSON object with original metadata values, extraction evidence, locations and rules |

metadata_evidence contains keys title, language, published_at, updated_at, effective_at, document_type and lifecycle_stage. The application requires all keys. Nonempty values other than unknown/other require raw_value and locator; mapped fields also require rule_id. A locator identifies a page, heading or HTML metadata location within that version, not simply the official website. Unknown values may use `{"raw_value":null,"reason":"not_stated"}`; other reasons include partial_date, ambiguous and multiple_effective_dates. SQL requires a JSON object; the application validates field semantics.

Implementation note, 2026-10-15: cover-date lookup failures use not_located_on_cover. Missing or unsupported PDF language metadata uses metadata_missing_or_unsupported. updated_at, effective_at and lifecycle_stage use not_extracted where extraction has not been implemented. A rule that did not extract a field does not establish that the original omitted it. Month-only cover dates use partial_date with the original value and page.

HTML implementation note, 2026-10-16: title, published_at and document_type evidence uses locator.selector; language uses `{"selector":"html","attribute":"lang"}`. Publication dates must be full English dates in the article container's direct .date child. Do not substitute URL dates, sidebar dates, historical dates in the body or last-modified metadata. Missing dates use not_located_in_article_header; unsupported formats use unsupported_date_format; invalid full calendar dates are rejected. metadata_evidence.body adds locator.selector and rule html-dom-text-v1 without duplicating body text. HTML raw_text is the body-container text after script/style removal with block boundaries preserved; complete original bytes remain in raw_path. Chunk offsets refer to clean_text; page_start/page_end/section remain NULL. A selector is not a section heading. These are source facts or deterministic results, not AI outputs. Do not backfill PDF dates from associated HTML announcements.

The second cover rule recognizes Consultation Conclusions, which has no matching document_type enum, so store other and preserve the label, first-page locator and unmapped_source_type. Earlier consultation dates quoted in the original and digits in URLs do not establish this document's publication date. No SQL schema change is needed.

The following illustrates structure only, not actual regulatory facts:

```json
{
  "title": {"raw_value": "<original title>", "locator": {"page": 1}},
  "language": {"raw_value": "en", "locator": {"metadata": "html.lang"}, "rule_id": "language-v1"},
  "published_at": {"raw_value": null, "reason": "not_stated"},
  "updated_at": {"raw_value": null, "reason": "not_stated"},
  "effective_at": {"raw_value": null, "reason": "not_stated"},
  "document_type": {"raw_value": null, "reason": "not_stated"},
  "lifecycle_stage": {"raw_value": null, "reason": "not_stated"}
}
```

Choose locators appropriate to the format; PDFs do not use HTML locators. published_at must not exceed the source-local collection date, and processed_at must not precede collected_at. The application validates cross-table and timezone comparisons, logging and rejecting invalid successful results. effective_at may precede or follow publication; do not impose a universal ordering.

## chunks

| Field | SQL type | Nullable | Provenance | Meaning and constraints |
|---|---|---|---|---|
| chunk_id | TEXT | No | D | Primary key from extraction_id and ordinal; never reuse a historical version's ID |
| extraction_id | TEXT | No | D | Foreign key to extractions.extraction_id |
| ordinal | INTEGER | No | D | Zero-based document order, unique with extraction_id; continuity checked by application |
| text | TEXT | No | D | Exact contiguous clean_text slice; never a summary |
| char_start | INTEGER | No | D | Zero-based Unicode code-point offset, inclusive |
| char_end | INTEGER | No | D | Exclusive end; greater than char_start and within text length |
| page_start | INTEGER | Yes | D | One-based physical PDF page number; NULL for HTML |
| page_end | INTEGER | Yes | D | At least page_start; equal in the initial page-bounded PDF implementation |
| section | TEXT | Yes | S | Original heading or clause number; never invented |
| is_table | INTEGER | Yes | D | 1 = table, 0 = confirmed non-table, NULL = undetermined; extraction failure is not 0 |

page_start/page_end must both be NULL or both valid. SQL checks exact chunk length and content against clean_text. The application checks physical PDF pages, HTML ranges, NUL characters and original mappings. JavaScript implementations must count Unicode code points rather than UTF-16 code units. Assemble citations by JOINing original URL, title, version_id, pages and section; do not persist duplicated citation.label/url values that can become stale.

## extraction_asset_classes

| Field | SQL type | Nullable | Provenance | Meaning and constraints |
|---|---|---|---|---|
| extraction_id | TEXT | No | D | Foreign key to extractions; composite primary key with asset_class |
| asset_class | TEXT | No | D | Deterministic topic label, not a legal classification |
| rule_id | TEXT | No | C | Rule identifier traceable to the processing manifest |
| evidence_chunk_id | TEXT | No | D | Supporting chunk; composite foreign key requires the same extraction |

Retain one representative evidence chunk per label. AI judgments requiring multiple evidence chunks belong in future development_evidence, not an expansion of this table.

## Canonical Values

| Classification | Canonical values and decisions |
|---|---|
| jurisdiction | Hong Kong, Singapore only; additional jurisdictions require a later schema migration |
| source_type | primary_regulator only; other source types are not enabled |
| asset_class | stablecoin, cryptocurrency, tokenized_security, tokenized_deposit, rwa, cbdc |
| document_type | press_release, consultation_paper, circular, guideline, speech, legislation, policy_statement, enforcement_notice, market_update, other |
| lifecycle_stage | proposal, consultation, enacted, implementation, enforcement, guidance, unknown |
| language | en, zh-Hant, zh-Hans; reserved Chinese values do not imply implemented Chinese parsing |

tokenized_deposit explicitly extends the skills' basic asset list because the proposal and existing fixtures distinguish it from stablecoins. enforcement_notice and market_update follow the source-onboarding skill's broader document-type list. Determine document type and lifecycle independently; consultation conclusions do not automatically imply enacted.

## Legacy Mapping and Migration

These are future real-data adapter rules, not permission to import fixtures. The existing four documents, four chunks, four developments and three market observations remain in demo files. Example IDs, pages, dates, hashes, paths, review labels and confidence values must not enter production records.

| Legacy field or value | New model or handling |
|---|---|
| documents.document_id | Recompute from canonical URL; retain an old/new ID map for a real legacy database, never reuse demo IDs |
| title, language, lifecycle_stage | Same-named extractions fields, revalidated against real originals |
| source_url | documents.source_url; final download address stored separately in downloaded_url |
| source_type=primary_regulatory | sources.source_type=primary_regulator after source identity verification |
| jurisdiction=HK / SG | Hong Kong / Singapore; EU, UK and other unsupported jurisdictions cannot be automatically imported |
| regulator | sources.regulator; must match jurisdiction |
| publication_date | extractions.published_at; NULL if precision or evidence is insufficient |
| retrieved_at | document_versions.collected_at; maintain last_collected_at for repeated collection |
| content_sha256 | Recompute from actual saved bytes; demo-* and sha256:demo-* are invalid |
| text_path | No direct mapping; use raw_path for originals and raw_text/clean_text for extracted text |
| asset_classes | Multiple extraction_asset_classes rows with a rule and evidence from the same extraction |
| topics | Not persisted in this phase; future retrieval labels need explicit rules |
| supersedes_document_id | Future document_relations, not a byte version at the same URL |
| provenance.connector / retrieval_id | Future source configuration, pipeline manifests and logs; demo_fixture is not a real source |
| chunks.document_id | Replace with extraction_id foreign key; obtain document identity by JOIN |
| chunks.chunk_id | Rebuild from new extraction_id and ordinal |
| chunks.text, section, is_table | Same-named fields; is_table nullable; every chunk must trace to a real original |
| chunks.page | page_start/page_end after physical-page verification; NULL for HTML |
| chunks.char_start / char_end | Recompute against new clean_text; never copy example offsets |
| chunks.citation | Assemble URL, title, version and locator at query time |
| chunks.retrieval_terms | Future retrieval-derived field; not stored now |
| lifecycle_stage=policy_update / supervisory_statement | No one-to-one legal-stage mapping; review the source, otherwise unknown |
| asset_class=tokenized_rwa | Normalize to rwa while preserving market/document entity boundaries |
| developments.effective_date | Future developments.effective_at; extraction.effective_at requires an explicit whole-document date |
| Other developments fields | Retain in demo; future AI tables, not ingestion tables |
| All market_observations.csv fields | Retain in demo; future separate market table with metric units and collection time |

Future AI provenance: development_id, evidence associations and generation time are system-derived (D). obligation_summary, affected_actors, impact_tags, risk_rating and confidence are AI-derived (A). risk_rating remains NULL until assessment criteria are defined; confidence remains NULL until its estimation method is defined and cannot be displayed as a probability by default. review_status starts as pending and changes only after actual review consistent with run records. jurisdiction/regulator derive from source relations and cannot be arbitrarily rewritten by a model.

Future UI integration requires a separate adapter and explicit demo/real modes, handling empty tables, missing metadata and unreviewed results. Do not display a fixed All critic-checked label for real results. Existing teammate files remain unchanged.

## Schema v2: HTML Observations

The added html_observations table is defined in [HTML change detection](html_incremental.md#observation-fields), including types, nullability, provenance and constraints. The six original tables retain their meaning. document_versions stores parsing evidence originals; html_observations stores each actual response and links through extraction_id. Ignoring the verified dynamic token can avoid a new evidence version, but full bytes and observations are still retained. Never substitute response_fingerprint or article_fingerprint for content_sha256.
