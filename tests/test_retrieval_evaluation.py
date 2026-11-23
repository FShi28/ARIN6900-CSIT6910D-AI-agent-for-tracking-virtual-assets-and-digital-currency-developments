"""Independent scoring expectations and temporary evidence-integrity checks."""

import copy
import json
from pathlib import Path

import pytest

from scripts import evaluate_retrieval as ev
from virtual_asset_agent.common import identity
from virtual_asset_agent.reader import Reader
from virtual_asset_agent.storage import connect, init_database


def case(cid='a', expected='supported'):
    return {'id': 'q1', 'group': 'test', 'query': 'reserve', 'intent': 'Find reserve evidence',
            'expected': expected, 'filters': {}, 'rationale': 'Synthetic test only',
            'evidence': [{'chunk_id': cid}] if expected == 'supported' else []}


def test_metrics_use_positive_denominator_and_actual_rank():
    first = ev.score_case(case(), ['x', 'a', 'y'], 3)
    second = ev.score_case(case(), ['x', 'y', 'a'], 2)
    negative = ev.score_case(case(expected='unsupported'), ['x'], 3)
    summary = ev.aggregate([first, second, negative])
    assert first['reciprocal_rank'] == 0.5
    assert second['hit'] is False
    assert summary == {'cases': 3, 'supported_cases': 2, 'hit_at_k': 0.5,
                       'mrr_at_k': 0.25, 'empty_expected_cases': 1, 'unexpected_result_rate': 1.0}
    assert ev.aggregate([negative])['hit_at_k'] is None
    assert ev.aggregate([])['unexpected_result_rate'] is None
    with pytest.raises(ValueError, match='Duplicate result'):
        ev.score_case(case(), ['a', 'a'], 2)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    project = Path(__file__).resolve().parents[1]
    raw = tmp_path / 'data/raw/example.html'
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'<p>Reserve evidence.</p>')
    reader_file = tmp_path / 'src/virtual_asset_agent/reader.py'
    reader_file.parent.mkdir(parents=True)
    reader_file.write_bytes((project / 'src/virtual_asset_agent/reader.py').read_bytes())
    db_path = tmp_path / 'test.sqlite'
    init_database(db_path, project / 'db/schema.sql')
    did, vid, eid, cid = [identity(label) for label in ('doc', 'version', 'extraction', 'chunk')]
    text = 'Reserve evidence.'
    with connect(db_path) as db:
        db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                   ('hkma', 'Synthetic', 'Hong Kong', 'HKMA', 'primary_regulator', None, None, 0))
        db.execute('INSERT INTO documents VALUES (?,?,?)', (did, 'hkma', 'https://example.invalid/doc'))
        db.execute('INSERT INTO document_versions VALUES (?,?,?,?,?,?,?,?,?)',
                   (vid, did, ev.digest(raw.read_bytes()), 'https://example.invalid/doc', None,
                    'data/raw/example.html', 'text/html', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'))
        db.execute('INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (eid, vid, identity('pipeline'), '2025-01-01T00:00:00Z', 'Synthetic', 'en', None,
                    None, None, 'press_release', 'unknown', text, text, '{}'))
        db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (cid, eid, 0, text, 0, len(text), None, None, None, None))
    db.close()
    monkeypatch.setattr(ev, 'ROOT', tmp_path)
    with Reader(db_path) as reader:
        snapshot, chunks = ev.snapshot(reader)
    labelled = case(cid)
    labelled['evidence'][0].update(quote='Reserve', quote_start=0, quote_end=7, citation=chunks[cid]['citation'])
    manifest_path, cases_path = tmp_path / 'corpus.json', tmp_path / 'cases.jsonl'
    manifest_path.write_text(json.dumps({'corpus': snapshot, 'dataset_version': 'test', 'annotation_status': 'synthetic'}))
    cases_path.write_text(json.dumps(labelled))
    return db_path, manifest_path, cases_path, labelled, chunks, raw


def test_read_only_and_reproducible(corpus):
    db, manifest, cases, *_ = corpus
    before = db.read_bytes()
    report = ev.evaluate(db, manifest, cases)
    assert report == ev.evaluate(db, manifest, cases)
    assert report['metrics']['hit_at_k'] == 1
    assert report['documents'] == report['chunks'] == 1
    assert db.read_bytes() == before


@pytest.mark.parametrize('problem', ['quote', 'offset', 'citation', 'missing_chunk', 'duplicate_case',
                                    'supported_outside_filter', 'invalid_empty_scope', 'unsupported_with_evidence'])
def test_invalid_labels_fail_before_scoring(corpus, problem):
    _, _, _, original, chunks, _ = corpus
    item = copy.deepcopy(original)
    cases = [item]
    label = item['evidence'][0]
    if problem == 'quote': label['quote'] = 'invented'
    if problem == 'offset': label['quote_start'] = -1
    if problem == 'citation': label['citation']['source_url'] = 'https://example.invalid/wrong'
    if problem == 'missing_chunk': label['chunk_id'] = '0' * 64
    if problem == 'duplicate_case': cases.append(copy.deepcopy(item))
    if problem == 'supported_outside_filter': item['filters'] = {'published_from': '2025-01-01'}
    if problem == 'invalid_empty_scope': item['expected'] = 'excluded_by_filter'
    if problem == 'unsupported_with_evidence': item['expected'] = 'unsupported'
    with pytest.raises(ValueError):
        ev.validate_cases(cases, chunks)


def test_unknown_date_is_excluded_not_a_positive_miss(corpus):
    _, _, _, item, chunks, _ = corpus
    item['expected'] = 'excluded_by_filter'
    item['filters'] = {'published_from': '2025-01-01'}
    ev.validate_cases([item], chunks)
    metrics = ev.aggregate([ev.score_case(item, [], 5)])
    assert metrics['supported_cases'] == 0
    assert metrics['unexpected_result_rate'] == 0


def test_corpus_drift_is_rejected(corpus):
    db, manifest, cases, *_ = corpus
    value = json.loads(manifest.read_text())
    value['corpus']['documents'][0]['extraction_id'] = 'f' * 64
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Frozen corpus mismatch'):
        ev.evaluate(db, manifest, cases)


def test_original_tampering_is_rejected(corpus):
    db, manifest, cases, _, _, raw = corpus
    raw.write_bytes(b'changed original')
    with pytest.raises(ValueError, match='Raw evidence'):
        ev.evaluate(db, manifest, cases)


@pytest.mark.parametrize('k', [0, 101, True])
def test_invalid_k_fails_without_opening_database(k):
    with pytest.raises(ValueError, match='k must'):
        ev.evaluate(Path('does-not-exist.sqlite'), k=k)
