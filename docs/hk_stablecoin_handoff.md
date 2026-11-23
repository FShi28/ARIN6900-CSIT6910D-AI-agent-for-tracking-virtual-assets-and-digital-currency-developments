# Hong Kong stablecoin handoff — 2026-11-23

This release contains the collection implementation, reviewed source configurations, tests, source inventory and gap records. It does not contain the local SQLite databases, downloaded documents, runtime logs or full-text export. The inventory describes the existing local snapshot (68 documents, 1553 chunks), not data bundled with a fresh checkout.

## Run

From the repository root:

```powershell
python -m pip install -r requirements-app.txt
python scripts/collect_hk_stablecoins.py
python scripts/collect_hk_stablecoins.py --status
python scripts/validate_hk_stablecoins.py
```

Use `--resume` only for a matching recent interrupted run; use a fresh run after code/configuration changes. `--export-only` exports existing local records. Exported documents/chunks, coverage and relationships are under `data/exports/hk_stablecoins/`.

The six discovery publishers are HKMA, SFC, HKSAR Government, Charltons, ASIFMA and Linklaters; HKMA has two entry points. Fixed URL refreshing also covers the reviewed EY/KPMG/Deloitte publications. Daily scheduling requires the Streamlit collection worker to be running. No operating-system scheduler is installed.

Previously discovered and reviewed source metadata is included in the static catalogue to retain those URLs on a fresh checkout. Source availability and bounded historical discovery mean a fresh collection is not guaranteed to reconstruct the exact existing 68-document snapshot. To use that precise snapshot, transfer its SQLite database plus referenced raw/processed files and research snapshots, or use its document/chunk JSONL export for downstream retrieval.

## Limitations and continuation

- 39 predefined evidence checks are not proof of complete Hong Kong law coverage.
- Cap 656 official XML identity conflict remains quarantined; original statute PDF TLS and commencement gazette access remain unresolved.
- Three of four reviewed document relationships have both source and target evidence. SFC 23EC67 remains unavailable; legal status stays not_assessed.
- Other professor channels and historical archives still require review. Do not bypass extraction restrictions, certificate checks or access controls.
- Read `docs/hk_stablecoin_data.md`, `config/hk_stablecoin_gaps.json`, and the inventory for details. Local detailed continuation state stays in `data/ingestion/hk_stablecoins/work_checkpoint.json`.
- Hong Kong CBDC work is excluded from this release and remains local.
