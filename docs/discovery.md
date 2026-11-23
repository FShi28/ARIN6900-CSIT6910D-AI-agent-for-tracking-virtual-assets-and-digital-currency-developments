# HKMA Topic Discovery and Bounded Batch Ingestion

## Supported Scope

Read `ul.template-related-information li.related-information-item` from the verified stablecoin topic page. Accept only English press-releases paths on www.hkma.gov.hk, titles containing stablecoin/stablecoins, and explicit listing dates between configured published_from and the collection date. Dates come from listing elements, never URL digits. Record exclusion reasons for other PDFs, speeches, inSight pages, external hosts and unknown dates.

Deduplicate URLs and reject conflicting listing metadata. At most 20 candidates are allowed; exceeding this limit fails explicitly rather than silently truncating coverage. A batch defaults to three documents, with a maximum of ten, processed sequentially from newest to oldest listing date. No pagination, recursion or attachment traversal is performed. Discovery does not establish target availability: target_verified=false describes the discovery stage. A target is supported only after successful download, parsing, validation and persistence.

## Commands

Run from the repository root. The existing local database is schema v2 and needs no additional migration for discovery. For a fresh clone, initialize a database using the [ingestion guide](ingestion.md).

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'

# Save candidates and the topic snapshot; do not download articles or write to SQLite.
python -m virtual_asset_agent discover --source hkma

# Default batch of three; check known articles for updates and ingest new articles.
python -m virtual_asset_agent ingest-discovered --source hkma

# Validate the current topic-page sample, up to ten documents.
python -m virtual_asset_agent ingest-discovered --source hkma --limit 10

# Only new documents or documents without a successful extraction; skip known-document updates.
python -m virtual_asset_agent ingest-discovered --source hkma --limit 10 --new-only

# The original fixed-target mode remains available.
python -m virtual_asset_agent ingest --source hkma

python -m pytest tests -q -p no:cacheprovider
```

In discover output, new means the URL has no document record, known means a successful extraction exists, and retry means a document exists without a successful extraction. A download that failed before document registration may still appear as new; failure history is recorded in logs. These are local database states, not claims that the website has just published a document.

ingest-discovered fetches one current topic snapshot and uses it to verify all candidates in the batch. Each publication date is independently extracted from the article header. Missing dates or conflicts with the listing date fail validation; listing dates are not copied into publication metadata. Each target is fetched again using a shared HTTP session, a minimum one-second interval across documents, timeouts, finite retries and TLS verification.

Single-document parsing or validation failures allow the batch to continue. HTTP 401/403/429 or Retry-After indicates a source-access restriction and stops the entire batch, reporting unattempted documents. Partial failure returns exit code 1; complete success or no eligible candidates returns 0. `--url` applies only to the original ingest mode and cannot bypass discovery rules.

## Evidence and Compatibility

- `data/raw/<sha256>.html`: full original response bytes for topic pages and announcements.
- `data/discovery/<run_id>.json`: source/final URLs, topic snapshot hash, collection time, selection configuration, candidate date evidence, states and exclusion reasons.
- `data/discovery/<run_id>-batch.json`: immutable per-document results, errors, batch limit, attempted count and remaining count.
- Each successful result includes discovery_evidence linking the topic snapshot, candidate link and listing date. Originals and HTML observations use schema v2 without additional tables; the three original fixed-target URLs remain unchanged.

`status=created/reused` describes the processing result; `change_type` describes HTML comparison. Verified token-only changes reuse existing evidence and extraction while preserving the actual response as an observation. See [HTML change detection](html_incremental.md). A first run with changed code may create a new processing version without deleting older results.

## Limitations

Coverage is limited to relevant English press releases directly listed on the current topic page, not the whole site or historical archive. Review the scope before increasing the 20-candidate or ten-document batch limit. Default batches do not rotate automatically between runs; known documents are checked again in date order. Use --new-only to progress to older documents not yet ingested. Scheduling, MAS, RAG, agents, OCR and UI integration are not implemented. Tables retain text and originals, but their structure is not verified.
