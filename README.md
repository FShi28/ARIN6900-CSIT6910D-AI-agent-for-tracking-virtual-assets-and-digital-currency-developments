# Virtual Asset Intelligence

A file-first Streamlit prototype for tracking regulatory and market developments in virtual assets and digital currencies across Hong Kong, Singapore, Mainland China, India, Japan, Australia, the UK, and the EU. The demo UI reads illustrative local JSONL/CSV fixtures and provides regulatory monitoring, market signals, and citation-aware keyword search.

> The included records and URLs are fictional demo data. Replace them with approved sources before research use.

## Data schema

Canonical data is stored under [`data/canonical/`](data/canonical):

- `documents.jsonl`: publication metadata and provenance. Key fields: `document_id`, `title`, `source_url`, `source_type`, `jurisdiction`, `regulator`, `publication_date`, `retrieved_at`, `asset_classes`, `lifecycle_stage`, `text_path`, and `content_sha256`.
- `chunks.jsonl`: citation-preserving evidence excerpts. Key fields: `chunk_id`, `document_id`, `text`, `page`, `section`, `is_table`, `citation`, and `retrieval_terms`.
- `developments.jsonl`: normalized regulatory findings. Key fields: `development_id`, `document_id`, `jurisdiction`, `regulator`, `asset_class`, `lifecycle_stage`, `affected_actors`, `obligation_summary`, `impact_tags`, `risk_rating`, `evidence_chunk_ids`, `confidence`, and `review_status`.
- `market_observations.csv`: market indicators. Columns: `observation_id`, `instrument`, `asset_class`, `venue`, `metric`, `value`, `currency`, `observed_at`, `source_url`, `provider`, and `data_quality`.

JSONL uses one JSON object per line. Dates and timestamps use ISO 8601; machine timestamps are UTC. Raw source files should remain immutable, and every generated claim should reference one or more `chunk_id` values.

## Setup and run

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

If PowerShell blocks activation for the current user, run PowerShell as permitted by your environment and use:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Launch the UI

From the repository root:

```powershell
streamlit run src\app.py
```

The sidebar provides these views:

- **Overview:** summary metrics and regulatory pulse.
- **Regulatory Monitor:** filter developments and inspect supporting evidence.
- **Market Signals:** view illustrative market observations.
- **Ask the Analyst:** run local keyword matching against `chunks.jsonl`.

Stop the app with `Ctrl+C`. Deactivate the environment with:

```powershell
deactivate
```

## Project files

- [`src/app.py`](src/app.py): Streamlit UI.
- [`data/canonical/`](data/canonical): demo records following the schema above.
- [`requirements.txt`](requirements.txt): Python dependencies.
- [`proposal.txt`](proposal.txt): original project proposal.
