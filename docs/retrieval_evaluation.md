# Retrieval Evaluation Baseline

## Scope and Files

This phase evaluates the existing read-only Reader. It does not change ingestion, database structure, production data or teammate files, and adds no dependencies, answer generation or semantic models.

- `evals/retrieval/corpus.json`: frozen versions, text hashes and citation hashes for 12 current documents and 185 chunks.
- `evals/retrieval/cases.jsonl`: 20 cases with intent, actual query, group, filters, expectation, evidence and annotation rationale.
- `scripts/evaluate_retrieval.py`: offline evaluation, integrity checks and report generation.
- `evals/retrieval/results/report.json` and `report.md`: baseline metrics and per-case result order.
- `tests/test_retrieval_evaluation.py`: evaluation tests using independent temporary databases.

Annotations are an **assistant-authored draft pending human review**, not an independent expert gold standard. Cases were selected from saved evidence. Exact phrases and natural questions share intents, creating selection bias and statistical dependence. Score 17 supported cases, one filter-excluded case and two out-of-scope cases separately. Do not infer confidence intervals or production accuracy. The evaluation uses a stored evidence snapshot, not a determination of current legal effect or a new live source verification.

Documentation, comments, annotation intents and generated report labels are in English. Multilingual test queries use Unicode escapes in JSON; decoding preserves the original input and cross-language coverage. The Markdown report identifies these as non-English test inputs and points to cases.jsonl. Unicode-offset test literals likewise use escapes for CJK characters. Official originals and test snapshots retain their exact bytes, including any source-provided language-switch text.

## Reproduction

Run from the repository root:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m scripts.evaluate_retrieval --k 5
python -m pytest tests/test_retrieval_evaluation.py -q
```

Use --db to select an existing database; evaluation never creates or migrates it. The selected current corpus must match the frozen manifest exactly. Results go to the results/ directory above; reruns overwrite the two evaluation reports. The script lives outside the ingestion package, so evaluation changes do not alter ingestion processing versions. Reader uses a read-only connection and consistent transaction. The database file SHA-256 must match before and after execution. Do not ingest or write concurrently; detected file changes invalidate the run.

## Annotations and Integrity

Each evidence label includes a fixed chunk_id, citation metadata, a short quote and a half-open Unicode code-point range within the chunk, `[quote_start, quote_end)`. Citations also include offsets in the full cleaned text, physical PDF pages or the HTML body selector. The script validates all chunk slices against clean_text, citation hashes, original-file SHA-256 values, labelled quotes and filters. Missing files, citation errors or corpus drift abort evaluation.

The expected field has three values:

| Value | Meaning | Scoring |
|---|---|---|
| supported | Labelled supporting evidence remains within the selected filters | Hit@k and MRR@k |
| excluded_by_filter | Explicit filters exclude the known evidence | Whether results are unexpectedly nonempty |
| unsupported | No supporting answer evidence within the frozen corpus scope | Whether results are unexpectedly nonempty |

PDFs without known publication dates are excluded by bounded publication-date filters. Never replace publication dates with cover months or effective dates in the body. The corresponding filter case expects no results and is not counted as a retrieval miss.

Only selected supporting chunks are labelled, not every potentially relevant chunk. Contents pages or term-only mentions do not establish support for a specified clause. Unlabelled results are not automatically errors. The two broad_phrase cases deliberately use underspecified phrases with explicit annotation intents to diagnose ranking ambiguity. Interpret them separately: the system cannot infer information omitted from its query.

After corpus changes, do not automatically replace the manifest to suppress mismatch errors. Review version differences, recheck quotes and intents, create a new evaluation version and retain old cases, manifests and reports. The script never regenerates labels automatically.

## Metrics and Recorded Results

Hit@k is the fraction of supported cases with at least one labelled evidence chunk among the first k results. MRR@k averages the reciprocal rank of the first labelled chunk, assigning zero to misses. Expected-empty cases have a separate unexpected-result rate and do not enter the positive denominator. Without exhaustive relevance judgments, do not report overall recall, precision or answer accuracy. Empty results alone do not prove unanswerability detection.

Default k=5:

| Group | Supported-case hits | MRR@5 |
|---|---|---|
| Exact phrases | 6/6 | 1.000 |
| English natural questions | 0/6 | 0.000 |
| Chinese-language test questions | 0/2 | 0.000 |
| Broad phrases | 1/2 | 0.125 |
| Positive date-filter case | 1/1 | 1.000 |
| Total | 8/17 (47.1%) | 0.426 |

All three expected-empty cases returned no results. Repeated runs with identical inputs produced identical full JSON reports. Real-database, original-file and evidence checks passed. Evaluation did not download documents again or verify additional sources.

Recorded validation: 16 evaluation-specific tests and 141 full regression tests passed (84.43 seconds). Coverage includes metric denominators/ranks, duplicate results, quote/offset/citation errors, corpus drift, original-file tampering, unknown-date exclusion, repeatability and unchanged database bytes. The real database retains 12 documents, 13 document_versions, 17 extractions, 417 chunks and 22 html_observations. The 185 current chunks are Reader's selected extraction set; historical chunks remain intact.

## Next Steps

Review the 20 intents and evidence labels manually, adding difficult negative cases and additional relevant chunks. Then add English token matching and relevance ranking as a separate search mode while preserving exact phrase queries, and compare natural-question and broad-phrase results against the same frozen cases. Chinese cross-language retrieval needs its own approach and evaluation. These baseline results do not determine an embedding model or establish readiness for answer generation.
