# Real data in the original Streamlit workspace

**2026-10-28 update:** The original frontend has been restored with a data-only
adapter. See [current UI integration](original_ui_data_adapter.md) for current
controls, layout and refresh behavior. The fragment refresh and collection-panel
descriptions below document the earlier reader UI, not the current `app.py`.

## Run

From the repository root:

```powershell
python -m pip install -r requirements-app.txt
python -m streamlit run src/app.py --server.address 127.0.0.1
```

The original four workspace pages now use real data directly. **Overview** is
the default. **Regulatory Monitor** contains the full document reader,
**Market Signals** reads public market APIs, and **Ask the Analyst** retrieves
real source excerpts. The separate live/demo mode switch has been removed.
The original canonical demo JSONL/CSV files remain unchanged but are no longer
loaded by the application. See [dashboard data integration](dashboard_data.md)
for exact field mappings, source limitations and market refresh behavior.

## Read and collect

- Filter titles or formats, select a document, and read its full extracted text.
- Open its official URL or download the saved original. Downloads verify the
  saved bytes against the stored SHA-256 before serving them.
- Expand **Evidence chunks and provenance** for PDF page numbers, text offsets,
  version identifiers, hashes and metadata evidence. Unknown dates stay unknown.
- **Collect now** requests a background collection, including while the automatic
  schedule is paused. The page remains usable during collection.
- **Collection settings** enables or pauses automatic collection and sets an
  interval of 1 to 168 hours. The default is 24 hours.

The worker starts when any workspace page is first opened. Its first collection is
due immediately unless a persisted previous completion makes it not yet due.
Subsequent checks are due one configured interval after the last completion,
including after a failed run. Settings and completion times survive restarts.
An overdue restart performs one catch-up collection, not every missed interval.
Pausing lets an in-progress collection finish.

The background worker continues after the browser closes, but requires the
Streamlit server to remain running and the computer to remain awake. This is
not a Windows startup task or an always-on hosted scheduler. After restarting
the server, open the workspace to start its worker again. The status panel
refreshes every 5 seconds and the document view every 15 seconds while open.

## Scope and storage

Each cycle uses the existing HKMA source configuration and ingestion pipeline:
bounded discovery of at most 20 candidates, up to 10 discovered press releases,
then configured fixed targets not already attempted. Currently the fixed targets
include two English text PDFs. Previously collected documents are checked for
updates. MAS remains disabled. This does not crawl the whole site, follow every
attachment, or paginate the source website.

The worker shares one rate-limited HTTP session per source and retains configured
timeouts, retries, host restrictions and TLS verification. Source access failures
stop further requests to that source in the cycle. Individual failures remain
visible without hiding previously collected documents.

Runtime files are local and separate from demo data:

| Path | Purpose |
| --- | --- |
| `data/ingestion/hkma.sqlite` | Real documents and immutable processing history |
| `data/ingestion/automation/settings.json` | Shared schedule and manual request |
| `data/ingestion/automation/state.json` | Latest cycle status and per-document results |
| `data/ingestion/automation/*.lock` | OS-managed collection/settings locks |
| `data/raw/` | Saved official bytes |
| `data/processed/` | Processing artifacts and manifests |
| `logs/` | Existing pipeline diagnostics |

A missing database is initialized from `db/schema.sql`. An existing database must
use schema version 2; the app does not silently migrate it. Use the documented
ingestion migration procedure and a backup for older databases.

An OS lock and persisted deadlines prevent overlapping app workers from
collecting twice. The existing standalone ingestion CLI does not acquire this
app lock; avoid running it concurrently with the app collector. Schedule settings
are shared by local browser sessions. The supplied launch command binds locally.

## Implementation and validation

- `src/app.py`: preserves the original theme and launches the real workspace.
- `src/dashboard_ui.py`: connects the four workspace pages to real data.
- `src/dashboard_data.py`: current-version regulatory data and evidence retrieval.
- `src/market_data.py`: public APIs, validated market snapshots and stale fallback.
- `src/live_documents.py`: read-only document display, provenance and downloads.
- `src/collection_service.py`: background scheduling and bounded collection.
- `requirements-app.txt`: installs both existing UI and ingestion dependencies.
- `tests/test_collection_service.py` and `tests/test_live_documents.py`: scheduler,
  concurrency, recovery, download validation and Streamlit UI tests.

Run the local test suite:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m pytest tests -q -p no:cacheprovider
```

In the initial live-reader integration on 2026-10-26, all 160 local tests passed.
The first live app cycle successfully
processed 12 existing real HKMA documents (10 HTML and 2 PDF). A new processing
result is not necessarily a new document: changed source bytes or a changed
processing version can create history for an existing document. Two PDFs have
unknown publication dates, which remain null rather than being inferred from
their URLs or PDF file metadata.

The 24-hour timing is tested with a controllable clock; a full 24-hour production
interval has not been observed. Live audit results are stored locally in
`data/ingestion/automation/live_app_validation.json`. The pre-integration database
backup is `data/ingestion/backups/hkma-before-live-ui-20261026.sqlite`.
A second collection triggered from the page reused all 12 processing results.
Document, original-version, extraction, chunk and asset-class counts were
unchanged; 10 HTML observation events were appended as intended. SQLite integrity
and foreign-key checks passed, and all 12 current original hashes and 185 current
chunk offsets matched the persisted evidence.
Frozen retrieval evaluation manifests must continue to use their corresponding
corpus snapshot; automatic collection can legitimately change the live corpus.
