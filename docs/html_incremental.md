# HTML Change Detection and Compatibility

## Scope and Rules

The supported HTML pages return a different csrf_token with each response. The html_observations table records the actual response for each successful observation and its referenced extraction. document_versions continues to represent parsing evidence originals; existing hashes and records remain unchanged. An unchanged observation may reference an older evidence original while preserving its own full response separately.

Comparison rule hkma-html-csrf-v1 parses and validates the supported announcement layout, serializes the full HTML DOM, and clears only the content attribute of head meta[name=csrf_token] before computing a response fingerprint. All other DOM content, body text, titles, dates, attachment href values and metadata participate in comparison. This fingerprint is separate from the original-byte SHA-256. Compare only within the same source and canonical URL. Other changes outside the article conservatively create a new evidence version.

A separate article fingerprint covers the announcement container, html.lang, date metadata and revision area. It distinguishes content_changed from page_changed; this is a structural comparison, not a legal-impact assessment. new means no successful baseline exists. unchanged means both the article content and response comparison fingerprint are unchanged. Every run still downloads, parses and validates the response.

## Additive Migration

The v1-to-v2 migration adds only html_observations, indexes and immutability triggers. Existing tables and records remain intact; historical observations are not backfilled. The script is db/migrations/002_html_observations.sql. The migrate-db CLI migrates v1 and is a no-op for v2. New databases use schema.sql v2 directly. Back up an existing database before migration and verify structure, constraints, rollback and record preservation in temporary databases first.

A successful observation commits in the same transaction as extraction/chunks/asset_classes. Failed responses retain their original files and error logs without successful observation rows. Processing-version changes may create new extractions; old results are preserved. The first run after a code update may create a new extraction. Subsequent token-only changes under identical rules reuse the evidence version, extraction and chunks, while adding one observation per successful run.

## Observation Fields

All fields are NOT NULL. observation_id is INTEGER; all other fields are TEXT. Provenance codes follow the [data dictionary](data_dictionary.md): S = source, C = configuration, D = deterministic/system-derived.

| Field | Meaning and provenance | Constraint |
|---|---|---|
| observation_id | SQLite-generated observation sequence, D | INTEGER PRIMARY KEY |
| run_id | Ingestion-run identifier, D | UNIQUE, nonempty |
| extraction_id | Successful extraction referenced by this observation, D | FK to extractions, RESTRICT; JOIN to version, document and source |
| collected_at | Actual download completion time for this response, D | UTC ISO timestamp at second precision |
| downloaded_url / parent_url | Final response URL / discovery page, S | HTTPS; official host validated by the application |
| raw_path | Original file for this full response, D | data/raw/hash.html; application verifies actual bytes |
| content_sha256 | SHA-256 of full response bytes, D | 64 lowercase hexadecimal characters |
| response_fingerprint | DOM comparison hash excluding the verified token, D | 64 lowercase hexadecimal characters |
| article_fingerprint | Comparison hash of article content and date/language metadata, D | 64 lowercase hexadecimal characters |
| rule_id | Comparison-rule version, C | hkma-html-csrf-v1 |
| change_type | Comparison against the latest successful observation, D | new / unchanged / content_changed / page_changed |

No AI-derived fields are stored. A different-byte observation does not change the collected_at of the referenced evidence original. Read the actual observation time from this table. CLI raw_path/content_sha256 describe the current response; evidence_raw_path/evidence_content_sha256 identify the original used by the extraction. These may differ.
