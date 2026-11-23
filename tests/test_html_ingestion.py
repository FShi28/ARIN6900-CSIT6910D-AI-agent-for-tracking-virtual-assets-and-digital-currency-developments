"""Recorded official HTML; no live network and no writes to the real database."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from virtual_asset_agent.common import PipelineError, sha256
from virtual_asset_agent.config import load_sources
from virtual_asset_agent.fetching import Download
from virtual_asset_agent.html_parsing import BODY, DATE, KIND, TITLE, body_text, parse_html
from virtual_asset_agent.normalization import normalize
from virtual_asset_agent.pipeline import ingest
from virtual_asset_agent.storage import Repository, init_database

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/hkma'
SOURCES = load_sources(ROOT / 'config/sources.yaml')
URL = SOURCES['hkma']['scope']['target_urls'][2]
CONTENT = (FIXTURES / 'announcement.html').read_bytes()


class OfflineHTML:
    def __init__(self, source, log):
        pass

    def get(self, url, expected_type):
        assert expected_type == 'text/html'
        filename = 'announcement.html' if url == URL else 'listing_html.html'
        return Download((FIXTURES / filename).read_bytes(), url, 'text/html', '2026-10-16T04:06:19Z')

    def close(self):
        pass


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr('virtual_asset_agent.pipeline.utc_now', lambda: '2026-10-16T04:10:00Z')
    (tmp_path / 'db').mkdir()
    (tmp_path / 'db/schema.sql').write_bytes((ROOT / 'db/schema.sql').read_bytes())
    db = tmp_path / 'data/ingestion/test.sqlite'
    init_database(db, tmp_path / 'db/schema.sql')
    return tmp_path, db


def mutated(selector, text=None, remove=False):
    soup = BeautifulSoup(CONTENT, 'html.parser')
    node = soup.select_one(selector)
    if remove:
        node.decompose()
    else:
        node.string = text
    return str(soup).encode('utf-8')


def test_official_fixture_provenance():
    provenance = json.loads((FIXTURES / 'provenance_html.json').read_text())
    for name in ('listing_html', 'announcement'):
        assert sha256((FIXTURES / (name + '.html')).read_bytes()) == provenance[name]['sha256']
    assert provenance['announcement']['source_url'] == URL


def test_official_html_body_and_publication_evidence():
    parsed = parse_html(CONTENT)
    result = normalize(parsed)
    evidence = json.loads(result['metadata_evidence'])
    assert result['published_at'] == '2024-07-17'
    assert result['document_type'] == 'press_release'
    assert result['language'] == 'en'
    assert result['updated_at'] is result['effective_at'] is None
    assert result['lifecycle_stage'] == 'unknown'
    assert evidence['published_at']['raw_value'] == '17 Jul 2024'
    assert evidence['published_at']['locator'] == {'selector': DATE}
    assert '108 submissions' in parsed.pages[0]
    assert 'Latest Press Releases' not in parsed.pages[0]
    assert 'Last revision date' not in parsed.pages[0]
    assert 'Subscribe to Email Alert' not in parsed.pages[0]
    assert parsed.pages[0].endswith('17 July 2024')


@pytest.mark.parametrize('selector', [BODY, TITLE, KIND])
def test_missing_required_elements_fail(selector):
    with pytest.raises(PipelineError):
        parse_html(mutated(selector, remove=True))


@pytest.mark.parametrize('content', [b'<html>Access denied</html>', b'<html>\x00</html>'])
def test_invalid_html_fails(content):
    with pytest.raises(PipelineError):
        parse_html(content)


def test_missing_date_never_uses_url_body_meta_or_sidebar_date():
    result = normalize(parse_html(mutated(DATE, remove=True)))
    assert result['published_at'] is None
    assert json.loads(result['metadata_evidence'])['published_at']['reason'] == 'not_located_in_article_header'


@pytest.mark.parametrize('raw', ['July 2024', 'Yesterday'])
def test_unsupported_date_remains_unknown(raw):
    result = normalize(parse_html(mutated(DATE, raw)))
    assert result['published_at'] is None
    assert json.loads(result['metadata_evidence'])['published_at']['raw_value'] == raw


def test_invalid_calendar_date_fails():
    with pytest.raises(ValueError):
        normalize(parse_html(mutated(DATE, '31 Feb 2024')))


def test_ambiguous_date_fails():
    soup = BeautifulSoup(CONTENT, 'html.parser')
    node = soup.select_one(DATE)
    node.insert_after(BeautifulSoup('<div class="date">18 Jul 2024</div>', 'html.parser'))
    with pytest.raises(PipelineError, match='ambiguous'):
        parse_html(str(soup).encode())


def test_text_preserves_inline_punctuation_order_and_legal_values():
    node = BeautifulSoup('<div><p>Section <b>24</b>: HK$100.<br>Second line.</p>'
                         '<ol><li>One</li><li>Two</li></ol><script>bad()</script>'
                         '<style>bad{}</style><span hidden>hidden</span></div>', 'html.parser')
    text = body_text(node)
    assert 'Section 24: HK$100.' in text
    assert text.index('Second line.') < text.index('One') < text.index('Two')
    assert 'bad' not in text and 'hidden' not in text


def test_html_roundtrip_repeat_and_evidence(workspace):
    root, db = workspace
    first = ingest(root, db, SOURCES, fetcher_factory=OfflineHTML, document_url=URL)
    repeated = ingest(root, db, SOURCES, fetcher_factory=OfflineHTML, document_url=URL)
    assert first['status'] == 'created' and repeated['status'] == 'reused'
    assert {k:v for k,v in first['counts'].items() if k != 'html_observations'} == {k:v for k,v in repeated['counts'].items() if k != 'html_observations'}
    assert repeated['counts']['html_observations'] == 2
    assert first['extraction_id'] == repeated['extraction_id']
    assert first['pages'] is None and first['published_at'] == '2024-07-17'
    assert (root / first['raw_path']).read_bytes() == CONTENT
    repository = Repository(db)
    try:
        e = repository.db.execute('SELECT * FROM extractions').fetchone()
        rows = repository.db.execute('SELECT * FROM chunks ORDER BY ordinal').fetchall()
        assert all(c['page_start'] is None and c['page_end'] is None and c['section'] is None for c in rows)
        assert json.loads(e['metadata_evidence'])['body']['locator'] == {'selector': BODY}
        assert all(c['text'] == e['clean_text'][c['char_start']:c['char_end']] for c in rows)
        assert ''.join(''.join(c['text'].split()) for c in rows) == ''.join(e['clean_text'].split())
        assert repository.db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert repository.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        repository.close()


def test_html_result_rolls_back_on_asset_failure(workspace):
    root, db = workspace
    original = Repository._insert
    def fail_asset(self, table, record):
        if table == 'extraction_asset_classes':
            record = dict(record, evidence_chunk_id='f' * 64)
        return original(self, table, record)
    with patch.object(Repository, '_insert', fail_asset), pytest.raises(sqlite3.IntegrityError):
        ingest(root, db, SOURCES, fetcher_factory=OfflineHTML, document_url=URL)
    repository = Repository(db)
    try:
        counts = repository.counts()
        assert counts['document_versions'] == 1
        assert counts['extractions'] == counts['chunks'] == counts['extraction_asset_classes'] == 0
    finally:
        repository.close()


def test_volatile_html_bytes_preserve_versions_without_duplicate_document(workspace):
    root, db = workspace
    first = ingest(root, db, SOURCES, fetcher_factory=OfflineHTML, document_url=URL)
    class ChangedToken(OfflineHTML):
        def get(self, url, expected_type):
            original = super().get(url, expected_type)
            if url != URL:
                return original
            token = BeautifulSoup(original.content, 'html.parser').select_one('meta[name="csrf_token"]')['content']
            changed = original.content.replace(token.encode(), b'synthetic-test-token')
            return Download(changed, url, 'text/html', original.collected_at)
    second = ingest(root, db, SOURCES, fetcher_factory=ChangedToken, document_url=URL)
    again = ingest(root, db, SOURCES, fetcher_factory=ChangedToken, document_url=URL)
    assert first['document_id'] == second['document_id']
    assert first['version_id'] == second['version_id'] == again['version_id']
    assert first['extraction_id'] == second['extraction_id'] == again['extraction_id']
    assert second['status'] == again['status'] == 'reused'
    assert second['change_type'] == again['change_type'] == 'unchanged'
    assert second['counts']['documents'] == second['counts']['document_versions'] == second['counts']['extractions'] == 1
    assert again['counts']['html_observations'] == 3
    assert first['content_sha256'] != second['content_sha256']
    assert second['evidence_content_sha256'] == first['content_sha256']
    assert (root/second['raw_path']).is_file()
    repository = Repository(db)
    try:
        texts = repository.db.execute('SELECT DISTINCT clean_text FROM extractions').fetchall()
        assert len(texts) == 1
    finally:
        repository.close()


@pytest.mark.parametrize('fault', ['false_page', 'wrong_selector', 'invented_date', 'future_date'])
def test_html_validation_rejects_corrupt_results(workspace, fault):
    root, db = workspace
    from virtual_asset_agent.validation import validate_result
    def corrupt(root, source, version, extraction, chunks, assets, parsed, ranges):
        if fault == 'false_page':
            chunks[0]['page_start'] = chunks[0]['page_end'] = 1
        elif fault == 'wrong_selector':
            evidence = json.loads(extraction['metadata_evidence'])
            evidence['body']['locator']['selector'] = '.right-content'
            extraction['metadata_evidence'] = json.dumps(evidence)
        else:
            extraction['published_at'] = '2030-01-01' if fault == 'future_date' else '2024-07-18'
        validate_result(root, source, version, extraction, chunks, assets, parsed, ranges)
    with patch('virtual_asset_agent.pipeline.validate_result', corrupt), pytest.raises(PipelineError):
        ingest(root, db, SOURCES, fetcher_factory=OfflineHTML, document_url=URL)
