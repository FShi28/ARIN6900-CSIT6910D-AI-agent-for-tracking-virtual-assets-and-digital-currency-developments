# Four-region regulatory data pilot

The original Streamlit interface now reads real publications from four regions.
Layout, CSS, navigation and charts are retained. The asset filter splits
multi-class records into individual choices without duplicating publication rows.

| Jurisdiction | Publisher | Collection | Publication date | Evidenced classes |
|---|---|---|---|---|
| Hong Kong | HKMA | Existing discovery and PDF pipeline: 12 documents | Per document | stablecoin |
| Singapore | MAS | MAS Announces Plans to Support Commercialisation of Asset Tokenisation (PDF) | 2024-11-04 | tokenized_security, tokenized_deposit |
| European Union | ESMA | ESMA suggests amendments to the DLT Pilot Regime to make it permanent (HTML) | 2025-06-25 | tokenized_security |
| United Kingdom | FCA | FCA seeks further views on stablecoins and crypto custody (HTML) | 2025-05-28 | stablecoin, cryptocurrency |

Exact live-verified official URLs, selectors, date formats, verification times
and HTTP limits are in `config/regional_sources.json`. The MAS-authored PDF is
hosted by the Singapore Government Press Centre. Direct requests to the MAS
Project Guardian page returned a service-unavailable page and were rejected.

The three additional sources are **partially implemented**: they collect approved
publications, not new publication listings or complete archives. The current
corpus contains 15 documents and 199 current evidence chunks. Historical raw
versions and processing results are additional records, not extra documents.

## Compatibility and provenance

`src/regional_ingestion.py` reuses the existing HTTP, cleaning, chunking and
transactional persistence components. `db/regional_schema.sql` expands only the
v2 source jurisdiction/regulator constraints. It initializes a separate
`data/ingestion/regional.sqlite`; the existing HKMA database is not migrated.
`src/app_data.py` combines both databases using the existing Reader contract.

The separate configuration and module deliberately depart from the skills'
preferred `sources.yaml` / collector layout to avoid changing the HKMA pipeline's
package-wide processing hash merely to add regional samples. The disabled MAS
placeholder in `sources.yaml` belongs to the original pipeline; the approved PDF
is enabled in `regional_sources.json`. A future unified database requires an
explicit migration for source constraints and configuration consolidation.

Jurisdiction and regulator come from configuration. Dates come from the PDF
cover or configured publication-date element. Unknown effective/update dates
and language stay null; document type is `other`, lifecycle is `unknown`.
Analysis fields remain unassessed. No AI component was added.

Asset classes are deterministic text matches linked to persisted evidence chunks.
`tokenized_deposit` already exists in the schema. These tags indicate topics,
not legal conclusions or named instruments. These publications do not establish
CBDC or RWA regulatory coverage. Market cards retain their separate providers.

Raw responses retain exact bytes and SHA-256 under `data/raw/`. Processing
manifests include code, parser versions, source configuration and schema hashes.
Title/date/body locators and exact text slices preserve traceability. Extraction,
chunks and classifications are committed together.

## Repeat behavior and scheduling

Source and URL define document identity. Identical raw bytes and processing
manifest reuse the existing version and result. Changed bytes create immutable
versions; processing changes create historical results, never replacements.
FCA responses have variable script and sharing-link attributes: a live repeat
can create a raw version and extraction even with unchanged article text. The
UI still shows one current publication. Regional HTML volatility normalization
has not been implemented; raw snapshots are intentionally preserved.

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m regional_ingestion
python -m streamlit run src/app.py --server.port 8501
```

The CLI initializes the regional database when absent. The existing app-owned
cycle checks enabled regional URLs after HKMA, using the persisted interval
(default 24 hours). The server and computer must remain running. This checks
approved publications for changes, not new articles. The adapter refreshes after
its 60-second cache expires and the page reruns. No frontend controls were added.

## Verification and limits

`tests/test_regional.py` uses saved official responses for metadata, parsing,
exact text slices, repeated persistence, foreign keys, integrity and error-page
rejection. App tests cover preserved styles and multi-class filtering. Live
audit results are recorded locally in `data/ingestion/regional_validation.json`.

There is no OCR, whole-site discovery, attachment crawling, legal-effect
inference or model analysis. Changed titles/selectors fail for manual review.
Next steps are verified publication discovery for each new region and a
conservative regional HTML change detector.
