# Read-Only Queries for Real Regulatory Data

Use the Reader interface or standalone CLI in `src/virtual_asset_agent/reader.py`. It adds no dependencies, tables, network service or UI and preserves the ingestion CLI. Demo files are never used as fallback data.

## Commands

Run from the repository root:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'

# Default page size: 20; maximum: 100. Results are JSON.
python -m virtual_asset_agent.reader documents
python -m virtual_asset_agent.reader documents --source hkma --published-from 2024-01-01 --published-to 2025-12-31

# Literal phrase matching, case-insensitive for ASCII English, on current chunks only.
python -m virtual_asset_agent.reader search --query "reserve assets" --limit 5

# Assign returned IDs to these variables; fixed historical records do not switch versions.
python -m virtual_asset_agent.reader document --document-id $documentId
python -m virtual_asset_agent.reader extraction --extraction-id $extractionId
python -m virtual_asset_agent.reader extraction --extraction-id $extractionId --include-text
python -m virtual_asset_agent.reader chunks --extraction-id $extractionId --limit 20 --offset 0
python -m virtual_asset_agent.reader chunk --chunk-id $chunkId
```

--db defaults to data/ingestion/hkma.sqlite. The CLI accepts only .sqlite files under data/ingestion. Missing files or schemas other than v2 fail explicitly; queries never create or migrate a database. Empty searches return an empty list; unknown IDs return an error and exit code 1. Date filters exclude documents with unknown publication dates. Without date filters, these documents remain visible with NULL dates.

## Python Interface

```python
from virtual_asset_agent.reader import Reader

with Reader("data/ingestion/hkma.sqlite") as reader:
    documents = reader.list_documents(limit=20, source="hkma")
    hits = reader.search("reserve assets", limit=5)
    if hits:
        fixed = reader.get_chunk(hits[0]["chunk_id"])
        assert fixed["text"] == hits[0]["text"]
```

Reader uses SQLite URI mode=ro and query_only=ON, with one consistent read transaction for the connection lifetime. Close it after use. It does not load source configuration, access the network or write logs/data. Methods are list_documents, get_document, get_extraction, list_chunks, get_chunk and search.

## Current Versions and Fixed References

Document lists and searches first select the most recently observed original per document. Events come from document_versions.last_collected_at and html_observations.collected_at. At the same second, observation-table events take precedence, followed by insertion order; observations use observation_id to represent reversions to older originals correctly. The selected original's latest extraction is chosen by processed_at, then insertion rowid for ties. This is observation/processing order, not a legal-validity determination.

If the latest registered original has no successful extraction, the document returns state=unprocessed, extraction_id=NULL and chunk_count=0. Search does not fall back to an older extraction. HTML failures before version registration appear only in originals and logs; Reader does not read those logs and does not expose all download failures.

Explicit extraction_id/chunk_id queries return fixed historical records regardless of later ingestion or code changes. Each chunk includes citation metadata: canonical source URL, title, date, document_id, version_id, extraction_id, chunk_id, evidence raw_path and original SHA-256. PDF citations retain physical pages; HTML citations retain the body selector. Character ranges are half-open Unicode code-point offsets in clean_text. `chunk:<chunk_id>` is a stable application reference, not a website URL.

evidence_collected_at/evidence_last_collected_at describe the cited evidence original; last_observed_at describes the current document observation. These may differ after token-only changes. Queries return stored evidence metadata without recomputing every original-file hash; independent audits verify file integrity.

## Search Limitations and Compatibility

search performs literal phrase matching on current chunks, ordered deterministically by publication date, document ID and chunk ordinal. It supports limit/offset, source and publication-date filters. SQLite lower mainly supports ASCII case conversion; other scripts, including Chinese, can match literally. Stemming, synonyms, spelling correction, BM25, semantic retrieval and relevance scores are not implemented. No summaries or answers are generated.

This step does not change schema v2 or reingest real documents. The processing manifest hashes all Python files in the ingestion package, so adding reader.py changes the processing version for a future ingestion run. Read-only queries do not change versions or counts. Historical citations remain valid.

## Real-Database Validation

Document listing, the reserve assets query and fixed chunk_id lookup were run against the local database, checking 12 documents and 185 current chunks. Citations matched text slices, original hashes and PDF/HTML locations, and historical chunks remained accessible. The database file SHA-256 was identical before and after querying, with unchanged counts. The local record is data/ingestion/query_validation_report.json.

The following chunk ID belongs to that local validation snapshot. The database and originals are not committed with the code. After reingestion, obtain actual IDs through search or chunks before lookup; different processing versions may produce different IDs.

```powershell
python -m virtual_asset_agent.reader chunk --chunk-id ca1d2ef0de481b380aab3ad485c177b49dd49a9312d9e7328b8ecd87f22b006f
```

Recorded results: 20 Reader-specific tests and 125 full regression tests passed (92.46 seconds). Coverage includes write protection, unchanged file hashes, version reversions, same-second observation ordering, unprocessed latest originals, fixed historical references, NULL dates, pagination, literal queries, empty databases and invalid inputs.

These checks establish interface and evidence integrity, not natural-language retrieval quality. Retrieval evaluation, semantic search and model generation are subsequent work excluded from the October submission.
