"""Offline evaluation of Reader against a frozen, explicitly labelled corpus."""

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from virtual_asset_agent.reader import Reader, filters

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / 'evals' / 'retrieval'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_hash(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8'))


def snapshot(reader):
    documents, chunks = [], {}
    offset = 0
    while True:
        page = reader.list_documents(limit=100, offset=offset)
        if not page:
            break
        for document in page:
            if document['state'] != 'ready':
                raise ValueError('Corpus contains an unprocessed document')
            extraction = reader.get_extraction(document['extraction_id'], include_text=True)
            entries = []
            for start in range(0, document['chunk_count'], 100):
                for chunk in reader.list_chunks(document['extraction_id'], limit=100, offset=start):
                    if extraction['clean_text'][chunk['char_start']:chunk['char_end']] != chunk['text']:
                        raise ValueError('Chunk is not an exact clean_text slice')
                    chunks[chunk['chunk_id']] = chunk
                    entries.append({'chunk_id': chunk['chunk_id'], 'text_sha256': digest(chunk['text'].encode()),
                                    'citation_sha256': json_hash(chunk['citation'])})
            documents.append({key: document[key] for key in (
                'document_id', 'version_id', 'extraction_id', 'source_id', 'source_url',
                'published_at', 'raw_path', 'content_sha256')})
            documents[-1].update(clean_text_sha256=digest(extraction['clean_text'].encode()), chunks=entries)
        offset += len(page)
    return {'documents': sorted(documents, key=lambda d: d['document_id'])}, chunks


def eligible(citation, selected):
    published = citation['published_at']
    return ((not selected.get('source') or citation['source_id'] == selected['source'])
            and (not selected.get('published_from') or published is not None and published >= selected['published_from'])
            and (not selected.get('published_to') or published is not None and published <= selected['published_to']))


def validate_cases(cases, chunks):
    if not cases:
        raise ValueError('Empty evaluation set')
    seen = set()
    for case in cases:
        if not case['id'] or case['id'] in seen:
            raise ValueError('Duplicate or empty case ID')
        seen.add(case['id'])
        if not isinstance(case['query'], str) or not 1 <= len(case['query'].strip()) <= 200 or '\0' in case['query']:
            raise ValueError('Invalid query')
        if not case['group'] or not case['intent'] or not case['rationale']:
            raise ValueError('Missing annotation rationale')
        selected = case.get('filters', {})
        if set(selected) - {'source', 'published_from', 'published_to'}:
            raise ValueError('Unknown filter')
        filters(**selected)
        labels = set()
        for label in case['evidence']:
            chunk = chunks.get(label['chunk_id'])
            if chunk is None or label['chunk_id'] in labels:
                raise ValueError('Missing or duplicate evidence chunk')
            labels.add(label['chunk_id'])
            start, end = label['quote_start'], label['quote_end']
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(chunk['text']):
                raise ValueError('Invalid evidence offsets')
            if chunk['text'][start:end] != label['quote']:
                raise ValueError('Evidence quote mismatch')
            if label['citation'] != chunk['citation']:
                raise ValueError('Evidence citation mismatch')
        in_scope = [label for label in case['evidence'] if eligible(chunks[label['chunk_id']]['citation'], selected)]
        expected = case['expected']
        if expected == 'supported' and not in_scope:
            raise ValueError('Supported case has no in-scope evidence')
        if expected == 'excluded_by_filter' and (not labels or in_scope):
            raise ValueError('Filtered case must have evidence excluded by its filters')
        if expected == 'unsupported' and labels:
            raise ValueError('Unsupported case cannot have evidence labels')
        if expected not in ('supported', 'excluded_by_filter', 'unsupported'):
            raise ValueError('Unknown expectation')


def score_case(case, hit_ids, k):
    if len(hit_ids) != len(set(hit_ids)):
        raise ValueError('Duplicate result IDs')
    relevant = {item['chunk_id'] for item in case['evidence']}
    ranks = [rank for rank, cid in enumerate(hit_ids[:k], 1) if cid in relevant]
    positive = case['expected'] == 'supported'
    return {'id': case['id'], 'group': case['group'], 'expected': case['expected'],
            'query': case['query'], 'filters': case.get('filters', {}), 'returned_chunk_ids': hit_ids[:k],
            'labelled_chunk_ids': sorted(relevant), 'hit': bool(ranks) if positive else None,
            'reciprocal_rank': 1 / ranks[0] if positive and ranks else 0.0 if positive else None,
            'empty_result': not hit_ids[:k],
            'diagnostic': ('labelled_evidence_found' if ranks else 'no_results' if not hit_ids[:k]
                           else 'results_without_labelled_evidence') if positive else
                          ('expected_empty' if not hit_ids[:k] else 'unexpected_results')}


def aggregate(rows):
    positives = [row for row in rows if row['expected'] == 'supported']
    negatives = [row for row in rows if row['expected'] != 'supported']
    return {'cases': len(rows), 'supported_cases': len(positives),
            'hit_at_k': sum(row['hit'] for row in positives) / len(positives) if positives else None,
            'mrr_at_k': sum(row['reciprocal_rank'] for row in positives) / len(positives) if positives else None,
            'empty_expected_cases': len(negatives),
            'unexpected_result_rate': sum(not row['empty_result'] for row in negatives) / len(negatives) if negatives else None}


def evaluate(db_path, manifest_path=EVAL / 'corpus.json', cases_path=EVAL / 'cases.jsonl', k=5):
    if type(k) is not int or not 1 <= k <= 100:
        raise ValueError('k must be 1..100')
    before = digest(db_path.read_bytes())
    manifest_bytes, cases_bytes = manifest_path.read_bytes(), cases_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    cases = [json.loads(line) for line in cases_bytes.decode('utf-8').splitlines() if line.strip()]
    with Reader(db_path) as reader:
        corpus, chunks = snapshot(reader)
        if corpus != manifest['corpus']:
            raise ValueError('Frozen corpus mismatch; review and version labels before evaluating')
        for document in corpus['documents']:
            raw = (ROOT / document['raw_path']).resolve()
            if not raw.is_relative_to(ROOT / 'data' / 'raw') or digest(raw.read_bytes()) != document['content_sha256']:
                raise ValueError('Raw evidence hash/path mismatch')
        validate_cases(cases, chunks)
        rows = [score_case(case, [hit['chunk_id'] for hit in reader.search(case['query'], limit=k,
                    **case.get('filters', {}))], k) for case in cases]
    after = digest(db_path.read_bytes())
    if before != after:
        raise ValueError('Database file changed during evaluation; discard this run')
    return {'dataset_version': manifest['dataset_version'], 'annotation_status': manifest['annotation_status'],
            'baseline': 'Reader literal phrase search, date/document/ordinal order', 'k': k,
            'python_version': sys.version.split()[0], 'sqlite_version': sqlite3.sqlite_version,
            'documents': len(corpus['documents']), 'chunks': len(chunks),
            'cases_sha256': digest(cases_bytes), 'manifest_sha256': digest(manifest_bytes),
            'reader_sha256': digest((ROOT / 'src/virtual_asset_agent/reader.py').read_bytes()),
            'evaluator_sha256': digest(Path(__file__).read_bytes()),
            'database_sha256_before': before, 'database_sha256_after': after,
            'metrics': aggregate(rows), 'groups': {group: aggregate([row for row in rows if row['group'] == group])
                for group in sorted({row['group'] for row in rows})}, 'cases': rows}


def markdown(report):
    def number(value):
        return '—' if value is None else f'{value:.3f}'
    lines = ['# Keyword Retrieval Baseline Evaluation', '',
             f"Frozen corpus: {report['documents']} documents / {report['chunks']} chunks; k={report['k']}.",
             'Labels are an assistant-authored draft pending human review, not exhaustive relevance judgments. '
             'Hit rate and MRR measure labelled evidence only, not overall recall or answer accuracy.', '',
             '| Group | Supported cases | Hit@k | MRR@k | Expected-empty cases | Unexpected-result rate |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for group, metrics in [('all', report['metrics']), *report['groups'].items()]:
        lines.append(f"| {group} | {metrics['supported_cases']} | {number(metrics['hit_at_k'])} | "
                     f"{number(metrics['mrr_at_k'])} | {metrics['empty_expected_cases']} | {number(metrics['unexpected_result_rate'])} |")
    lines += ['', '## Per-Case Results', '', '| ID | Query | Result |', '| --- | --- | --- |']
    for row in report['cases']:
        query = row['query'] if row['query'].isascii() else 'Non-English test input; see cases.jsonl'
        lines.append(f"| {row['id']} | {query.replace('|', '/')} | {row['diagnostic']} |")
    lines += ['', 'See cases.jsonl for fixed evidence, English intent descriptions and filter rationales; '
              'see report.json for result order and full hashes. Non-English test inputs are stored as Unicode escapes '
              'in JSON files and remain unchanged when decoded.',
              'Unlabelled results are not automatically errors, and empty results do not establish reliable '
              'unanswerability detection. The database SHA-256 is unchanged; original hashes and evidence slices passed validation.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data/ingestion/hkma.sqlite')
    parser.add_argument('--k', type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.db, k=args.k)
        destination = EVAL / 'results'
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'report.json').write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
        (destination / 'report.md').write_text(markdown(report), encoding='utf-8')
        print(json.dumps(report['metrics'], ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'Evaluation failed: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
