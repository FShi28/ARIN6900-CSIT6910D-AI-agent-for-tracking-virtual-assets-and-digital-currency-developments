"""Offline tests; real HTTP smoke runs are executed separately through the CLI."""

import copy
import json
import sqlite3
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from pypdf import PdfWriter

from virtual_asset_agent.cleaning import chunk_pages, clean_pages
from virtual_asset_agent.collectors.hkma import discover
from virtual_asset_agent.common import PipelineError, allowed_url, canonical_url, identity, local_path, sha256, write_immutable
from virtual_asset_agent.config import load_sources, validate_enabled
from virtual_asset_agent.fetching import Download, Fetcher
from virtual_asset_agent.normalization import classify, normalize
from virtual_asset_agent.parsing import parse_pdf
from virtual_asset_agent.pipeline import ingest
from virtual_asset_agent.storage import Repository, init_database
from virtual_asset_agent.validation import validate_result

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/hkma'
SOURCES = load_sources(ROOT / 'config/sources.yaml')
SOURCE = SOURCES['hkma']
PDF_URL = SOURCE['scope']['target_urls'][0]
SECOND_URL = SOURCE['scope']['target_urls'][1]


@pytest.fixture(autouse=True)
def fixed_processing_clock(monkeypatch):
    monkeypatch.setattr('virtual_asset_agent.pipeline.utc_now', lambda: '2026-10-15T08:00:00Z')


@pytest.fixture(scope='session')
def parsed():
    return parse_pdf((FIXTURES / 'guideline.pdf').read_bytes())


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'db').mkdir()
    (tmp_path / 'db/schema.sql').write_bytes((ROOT / 'db/schema.sql').read_bytes())
    path = tmp_path / 'data/ingestion/test.sqlite'
    init_database(path, tmp_path / 'db/schema.sql')
    return tmp_path, path


class OfflineFetcher:
    """Recorded source bytes; deliberately not represented as a live network test."""
    def __init__(self, source, log):
        self.source = source

    def get(self, url, expected_type):
        filename = 'listing.html' if expected_type == 'text/html' else 'guideline.pdf'
        if url == SECOND_URL:
            filename = 'consultation_conclusions.pdf'
        return Download((FIXTURES / filename).read_bytes(), url, expected_type, '2026-10-15T07:58:04Z')

    def close(self):
        pass


def test_fixture_hashes_match_provenance():
    provenance = json.loads((FIXTURES / 'provenance.json').read_text())
    for name, file in [('listing', 'listing.html'), ('guideline', 'guideline.pdf')]:
        assert sha256((FIXTURES / file).read_bytes()) == provenance[name]['sha256']


def test_source_configuration_and_disabled_mas():
    assert SOURCE['enabled'] is True
    assert SOURCES['mas']['enabled'] is False
    assert SOURCES['mas']['discovery_url'] is None


def test_discovery_returns_only_approved_live_link():
    result = discover((FIXTURES / 'listing.html').read_bytes(), SOURCE['discovery_url'], SOURCE)
    assert result == [{'source_url': url, 'parent_url': SOURCE['discovery_url']} for url in SOURCE['scope']['target_urls']]


@pytest.mark.parametrize('html', [b'<html><h1>Access denied</h1></html>', b'<html><h1>Regulatory Regime for Stablecoin Issuers</h1></html>'])
def test_discovery_structure_or_missing_target_fails(html):
    with pytest.raises(PipelineError):
        discover(html, SOURCE['discovery_url'], SOURCE)


def test_url_normalization_preserves_semantics():
    assert canonical_url('HTTPS://WWW.HKMA.GOV.HK:443/A/?id=7#page') == 'https://www.hkma.gov.hk/A/?id=7'


@pytest.mark.parametrize('url', ['http://www.hkma.gov.hk/x', 'https://www.hkma.gov.hk.evil.invalid/x', 'https://user@www.hkma.gov.hk/x', 'https://www.hkma.gov.hk:444/x'])
def test_unapproved_urls_fail(url):
    with pytest.raises(PipelineError):
        allowed_url(url, ['www.hkma.gov.hk'])


def test_real_pdf_metadata_is_source_grounded(parsed):
    metadata = normalize(parsed)
    assert len(parsed.pages) == 61
    assert metadata['title'] == 'Guideline on Supervision of Licensed Stablecoin Issuers'
    assert metadata['language'] == 'en'
    assert metadata['published_at'] is None
    evidence = json.loads(metadata['metadata_evidence'])
    assert evidence['published_at']['raw_value'] == 'August 2025'
    assert evidence['published_at']['reason'] == 'partial_date'
    assert metadata['effective_at'] is None
    assert metadata['lifecycle_stage'] == 'unknown'
    assert evidence['effective_at']['reason'] == 'not_extracted'
    assert 'reserve assets' in parsed.pages[4].lower()


def test_complete_cover_date_and_invalid_calendar_date(parsed):
    assert normalize(replace(parsed, cover_date_raw='29 July 2025'))['published_at'] == '2025-07-29'
    with pytest.raises(ValueError):
        normalize(replace(parsed, cover_date_raw='30 February 2025'))


def test_no_language_metadata_is_unknown(parsed):
    assert normalize(replace(parsed, language_raw=None))['language'] is None


@pytest.mark.parametrize('content', [b'not a PDF', b'%PDF-1.7\nmalformed'])
def test_malformed_pdf_fails(content):
    with pytest.raises(PipelineError):
        parse_pdf(content)


def test_image_only_or_blank_pdf_fails():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = BytesIO()
    writer.write(stream)
    with pytest.raises(PipelineError, match='non-text'):
        parse_pdf(stream.getvalue())


def test_page_chunks_preserve_every_non_whitespace_character(parsed):
    text, ranges = clean_pages(parsed.pages)
    eid = 'e' * 64
    chunks = chunk_pages(text, ranges, eid, 1800)
    assert {c['page_start'] for c in chunks} == set(range(1, 62))
    assert ''.join(''.join(c['text'].split()) for c in chunks) == ''.join(text.split())
    for c in chunks:
        assert c['text'] == text[c['char_start']:c['char_end']]
        assert c['page_start'] == c['page_end']
        assert c['is_table'] is None
        assert len(c['text']) <= 1800


def test_unicode_chunk_offsets():
    text, ranges = clean_pages(['Stablecoin \u4e2d\u6587😀 ' * 40])
    chunks = chunk_pages(text, ranges, 'e' * 64, 200)
    assert all(c['text'] == text[c['char_start']:c['char_end']] for c in chunks)


def test_immutable_files_do_not_overwrite(tmp_path):
    path = tmp_path / 'raw.pdf'
    write_immutable(path, b'first')
    write_immutable(path, b'first')
    with pytest.raises(PipelineError, match='mismatch'):
        write_immutable(path, b'second')
    assert path.read_bytes() == b'first'


def test_path_traversal_fails(tmp_path):
    with pytest.raises(PipelineError):
        local_path(tmp_path, '../outside')


def test_pipeline_twice_reuses_all_rows_and_keeps_evidence(workspace):
    root, path = workspace
    first = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    second = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    assert first['status'] == 'created' and second['status'] == 'reused'
    assert first['counts'] == second['counts']
    assert first['extraction_id'] == second['extraction_id']
    repository = Repository(path)
    try:
        assert repository.db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert repository.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        row = repository.db.execute('SELECT * FROM extractions').fetchone()
        assert row['published_at'] is None and row['title'].startswith('Guideline on')
        manifest = root / 'data/processed' / row['pipeline_version'] / 'manifest.json'
        assert sha256(manifest.read_bytes()) == row['pipeline_version']
        assert first['counts']['documents'] == first['counts']['document_versions'] == first['counts']['extractions'] == 1
        assert sha256((root / first['raw_path']).read_bytes()) == first['content_sha256']
        assert repository.db.execute("SELECT enabled FROM sources WHERE source_id='mas'").fetchone()[0] == 0
    finally:
        repository.close()


def test_changed_processing_creates_new_extraction_not_new_raw(workspace):
    root, path = workspace
    first = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    changed = copy.deepcopy(SOURCES)
    changed['hkma']['processing']['chunk_max_chars'] = 1000
    second = ingest(root, path, changed, fetcher_factory=OfflineFetcher)
    assert second['status'] == 'created'
    assert second['counts']['documents'] == second['counts']['document_versions'] == 1
    assert second['counts']['extractions'] == 2
    assert first['extraction_id'] != second['extraction_id']


def test_raw_change_creates_version_and_duplicate_reuses(workspace):
    _, path = workspace
    repository = Repository(path)
    try:
        repository.sync_sources(SOURCES)
        for data in (b'first', b'second', b'second'):
            download = Download(data, PDF_URL, 'application/pdf', '2026-10-15T07:58:04Z')
            digest = sha256(data)
            repository.register_raw('hkma', PDF_URL, download, digest, f'data/raw/{digest}.pdf', SOURCE['discovery_url'])
        assert repository.counts()['documents'] == 1
        assert repository.counts()['document_versions'] == 2
    finally:
        repository.close()


def test_result_transaction_rolls_back_on_bad_foreign_key(workspace):
    root, path = workspace
    ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    repository = Repository(path)
    try:
        before = repository.counts()
        extraction = dict(repository.db.execute('SELECT * FROM extractions').fetchone())
        chunks = [dict(r) for r in repository.db.execute('SELECT * FROM chunks ORDER BY ordinal')]
        extraction['pipeline_version'] = 'f' * 64
        extraction['extraction_id'] = identity('extraction', extraction['version_id'], 'f' * 64)
        for chunk in chunks:
            chunk['extraction_id'] = extraction['extraction_id']
            chunk['chunk_id'] = identity('chunk', extraction['extraction_id'], chunk['ordinal'])
        asset = {'extraction_id': extraction['extraction_id'], 'asset_class': 'stablecoin',
                 'rule_id': 'test-only', 'evidence_chunk_id': '0' * 64}
        with pytest.raises(sqlite3.IntegrityError):
            repository.save_result(extraction, chunks, [asset])
        assert repository.counts() == before
    finally:
        repository.close()


def test_cross_extraction_evidence_is_rejected(workspace):
    root, path = workspace
    first = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    changed = copy.deepcopy(SOURCES)
    changed['hkma']['processing']['chunk_max_chars'] = 1000
    second = ingest(root, path, changed, fetcher_factory=OfflineFetcher)
    repository = Repository(path)
    try:
        foreign_chunk = repository.db.execute('SELECT chunk_id FROM chunks WHERE extraction_id=?', (first['extraction_id'],)).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            repository.db.execute('INSERT INTO extraction_asset_classes VALUES (?,?,?,?)',
                                  (second['extraction_id'], 'rwa', 'test-only', foreign_chunk))
    finally:
        repository.close()


def test_parse_failure_preserves_raw_and_logs_stage(workspace):
    root, path = workspace
    class BrokenPDF(OfflineFetcher):
        def get(self, url, expected_type):
            result = super().get(url, expected_type)
            return replace(result, content=b'%PDF-1.7\nmalformed') if expected_type == 'application/pdf' else result
    with pytest.raises(PipelineError):
        ingest(root, path, SOURCES, fetcher_factory=BrokenPDF)
    repository = Repository(path)
    try:
        assert repository.counts()['document_versions'] == 1
        assert repository.counts()['extractions'] == 0
        raw_path = repository.db.execute('SELECT raw_path FROM document_versions').fetchone()[0]
        assert (root / raw_path).read_bytes().startswith(b'%PDF-')
    finally:
        repository.close()
    log = json.loads((root / 'logs/ingestion.jsonl').read_text().splitlines()[-1])
    assert log['stage'] == 'parsing' and log['status'] == 'failure'
    assert log['source_id'] == 'hkma' and log['url'] == PDF_URL and log['error_type']


def test_disabled_mas_never_calls_network(workspace):
    root, path = workspace
    factory = Mock()
    with pytest.raises(PipelineError, match='disabled'):
        ingest(root, path, SOURCES, 'mas', factory)
    factory.assert_not_called()


def test_reinitialization_cannot_destroy_data(workspace):
    root, path = workspace
    before = path.read_bytes()
    with pytest.raises(PipelineError, match='already exists'):
        init_database(path, root / 'db/schema.sql')
    assert path.read_bytes() == before


def response(status=200, content=b'%PDF-1.7\nfixture', **headers):
    value = Mock()
    value.status_code = status
    value.headers = {'Content-Type': 'application/pdf', **headers}
    value.iter_content.return_value = [content]
    return value


@pytest.fixture
def http_client(monkeypatch):
    monkeypatch.setattr('virtual_asset_agent.fetching.time.sleep', lambda _: None)
    session, logger = Mock(), Mock()
    session.headers = {}
    fetcher = Fetcher(SOURCE, logger, session)
    return fetcher, session, logger


def test_redirect_host_is_checked_before_next_request(http_client):
    fetcher, session, _ = http_client
    session.get.return_value = response(302, Location='https://other.invalid/private')
    with pytest.raises(PipelineError, match='outside'):
        fetcher.get(PDF_URL, 'application/pdf')
    assert session.get.call_count == 1


def test_public_search_post_preserves_transport_guards(http_client):
    fetcher, session, _ = http_client
    session.post.return_value = response(content=b'{"items":[]}', **{'Content-Type':'application/json'})
    assert fetcher.post_json(PDF_URL, {'pageNo':0}).content == b'{"items":[]}'
    assert session.post.call_args.kwargs['json'] == {'pageNo':0}
    assert session.post.call_args.kwargs['verify'] is True
    assert session.post.call_args.kwargs['allow_redirects'] is False


@pytest.mark.parametrize('status', [302, 403, 429])
def test_public_search_post_does_not_follow_denial_or_redirect(http_client, status):
    fetcher, session, _ = http_client
    session.post.return_value = response(status, Location=PDF_URL)
    with pytest.raises(PipelineError):
        fetcher.post_json(PDF_URL, {'pageNo':0})
    assert session.post.call_count == 1


@pytest.mark.parametrize('status', [401, 403, 429])
def test_access_denial_does_not_retry(http_client, status):
    fetcher, session, _ = http_client
    session.get.return_value = response(status)
    with pytest.raises(PipelineError, match=str(status)):
        fetcher.get(PDF_URL, 'application/pdf')
    assert session.get.call_count == 1


def test_bounded_retries_and_tls_stays_enabled(http_client):
    fetcher, session, logger = http_client
    session.get.side_effect = [requests.Timeout(), response(503), response()]
    assert fetcher.get(PDF_URL, 'application/pdf').content.startswith(b'%PDF-')
    assert session.get.call_count == 3 and logger.call_count == 2
    assert all(call.kwargs['verify'] is True and call.kwargs['allow_redirects'] is False for call in session.get.call_args_list)


def test_retry_exhaustion(http_client):
    fetcher, session, _ = http_client
    session.get.side_effect = requests.Timeout()
    with pytest.raises(PipelineError, match='exhausted'):
        fetcher.get(PDF_URL, 'application/pdf')
    assert session.get.call_count == 3


@pytest.mark.parametrize('reply', [response(content=b'<html>not a pdf</html>'), response(**{'Content-Type': 'text/html'})])
def test_mime_or_magic_mismatch(http_client, reply):
    fetcher, session, _ = http_client
    session.get.return_value = reply
    with pytest.raises(PipelineError):
        fetcher.get(PDF_URL, 'application/pdf')


def test_size_limit(http_client):
    fetcher, session, _ = http_client
    fetcher.options = dict(fetcher.options, max_bytes=5)
    session.get.return_value = response()
    with pytest.raises(PipelineError, match='size limit'):
        fetcher.get(PDF_URL, 'application/pdf')


def test_retry_after_stops_early(http_client):
    fetcher, session, _ = http_client
    session.get.return_value = response(503, **{'Retry-After': '120'})
    with pytest.raises(PipelineError, match='delayed access'):
        fetcher.get(PDF_URL, 'application/pdf')
    assert session.get.call_count == 1


@pytest.mark.parametrize('fault', ['raw_hash', 'invented_title', 'missing_evidence', 'future_publication', 'wrong_page', 'lost_text', 'missing_asset'])
def test_application_validation_rejects_bad_data(tmp_path, parsed, fault):
    raw = (FIXTURES / 'guideline.pdf').read_bytes()
    digest = sha256(raw)
    raw_path = f'data/raw/{digest}.pdf'
    write_immutable(tmp_path / raw_path, raw)
    version = {'version_id': 'a' * 64, 'content_sha256': digest, 'raw_path': raw_path,
               'downloaded_url': PDF_URL, 'parent_url': SOURCE['discovery_url'], 'collected_at': '2026-10-15T07:58:04Z'}
    pipeline_version = 'b' * 64
    eid = identity('extraction', version['version_id'], pipeline_version)
    text, ranges = clean_pages(parsed.pages)
    extraction = {'extraction_id': eid, 'version_id': version['version_id'], 'pipeline_version': pipeline_version,
                  'processed_at': '2026-10-15T08:00:00Z', 'raw_text': '\n\n'.join(parsed.pages),
                  'clean_text': text, **normalize(parsed)}
    chunks = chunk_pages(text, ranges, eid, 1800)
    assets = classify(chunks)
    if fault == 'raw_hash':
        (tmp_path / raw_path).write_bytes(b'corruption')
    elif fault == 'invented_title':
        extraction['title'] = 'Invented title'
    elif fault == 'missing_evidence':
        extraction['metadata_evidence'] = '{}'
    elif fault == 'future_publication':
        extraction['published_at'] = '2030-01-01'
    elif fault == 'wrong_page':
        chunks[0]['page_start'] = chunks[0]['page_end'] = 61
    elif fault == 'lost_text':
        chunks.pop()
    elif fault == 'missing_asset':
        assets = []
    with pytest.raises(PipelineError):
        validate_result(tmp_path, SOURCE, version, extraction, chunks, assets, parsed, ranges)


@pytest.fixture(scope='session')
def consultation():
    return parse_pdf((FIXTURES / 'consultation_conclusions.pdf').read_bytes())


def test_second_fixture_hashes_match_provenance():
    provenance = json.loads((FIXTURES / 'provenance_two_documents.json').read_text())
    for key, filename in [('listing', 'listing_two_documents.html'), ('consultation_conclusions', 'consultation_conclusions.pdf')]:
        assert sha256((FIXTURES / filename).read_bytes()) == provenance[key]['sha256']


def test_consultation_cover_keeps_type_and_partial_date_uncertainty(consultation):
    metadata = normalize(consultation)
    evidence = json.loads(metadata['metadata_evidence'])
    assert len(consultation.pages) == 32
    assert metadata['title'] == 'Legislative Proposal to Implement the Regulatory Regime for Stablecoin Issuers in Hong Kong Consultation Conclusions'
    assert consultation.title_raw in consultation.pages[0]
    assert metadata['document_type'] == 'other'
    assert evidence['document_type']['raw_value'] == 'Consultation Conclusions'
    assert evidence['document_type']['reason'] == 'unmapped_source_type'
    assert metadata['lifecycle_stage'] == 'unknown'
    assert evidence['published_at']['raw_value'] == 'July 2024'
    # Neither the URL's 20240717 nor the earlier consultation date in the body is a publication date.
    assert metadata['published_at'] is None
    assert metadata['language'] == 'en'


def test_second_document_chunks_cover_all_pages(consultation):
    text, ranges = clean_pages(consultation.pages)
    chunks = chunk_pages(text, ranges, 'c' * 64, 1800)
    assert len(chunks) == 51
    assert {c['page_start'] for c in chunks} == set(range(1, 33))
    assert ''.join(''.join(c['text'].split()) for c in chunks) == ''.join(text.split())
    assert all(c['text'] == text[c['char_start']:c['char_end']] for c in chunks)


def test_selected_discovery_and_missing_unselected_link():
    html = (FIXTURES / 'listing_two_documents.html').read_bytes()
    result = discover(html, SOURCE['discovery_url'], SOURCE, target_url=SECOND_URL)
    assert result == [{'source_url': SECOND_URL, 'parent_url': SOURCE['discovery_url']}]
    # A removed link for the OTHER document cannot prevent the selected document from running.
    second_path = SECOND_URL.removeprefix('https://www.hkma.gov.hk').encode()
    assert second_path in html
    html = html.replace(second_path, b'/removed.pdf')
    assert second_path not in html
    assert discover(html, SOURCE['discovery_url'], SOURCE, target_url=PDF_URL)[0]['source_url'] == PDF_URL


def test_missing_selected_link_never_falls_back_to_another_document():
    html = b'<html><h1>Regulatory Regime for Stablecoin Issuers</h1><a href="' + PDF_URL.encode() + b'">Guideline</a></html>'
    with pytest.raises(PipelineError, match='not found'):
        discover(html, SOURCE['discovery_url'], SOURCE, target_url=SECOND_URL)


def test_unknown_document_is_rejected_before_network(workspace):
    root, path = workspace
    factory = Mock()
    with pytest.raises(PipelineError, match='approved target'):
        ingest(root, path, SOURCES, fetcher_factory=factory, document_url='https://www.hkma.gov.hk/not-approved.pdf')
    factory.assert_not_called()


@pytest.mark.parametrize('targets,limit', [([PDF_URL, PDF_URL + '#page=1'], 2), ([PDF_URL, SECOND_URL], 1), ([PDF_URL, SECOND_URL], 4), ([], 2)])
def test_configuration_rejects_duplicate_or_unbounded_targets(targets, limit):
    source = copy.deepcopy(SOURCE)
    source['scope']['target_urls'] = targets
    source['scope']['max_documents'] = limit
    with pytest.raises(PipelineError):
        validate_enabled(source)


def test_two_documents_repeated_runs_keep_separate_evidence(workspace):
    root, path = workspace
    first = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    second = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher, document_url=SECOND_URL)
    first_again = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    second_again = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher, document_url=SECOND_URL)
    assert first_again['status'] == second_again['status'] == 'reused'
    assert second['counts'] == first_again['counts'] == second_again['counts']
    assert second['counts']['documents'] == second['counts']['document_versions'] == second['counts']['extractions'] == 2
    assert second['counts']['chunks'] == 164
    assert first['document_id'] != second['document_id']
    repository = Repository(path)
    try:
        rows = repository.db.execute('SELECT d.source_url, e.document_type, e.extraction_id FROM documents d JOIN document_versions v USING(document_id) JOIN extractions e USING(version_id)').fetchall()
        assert {r['source_url']:r['document_type'] for r in rows} == {PDF_URL:'guideline', SECOND_URL:'other'}
        first_chunk = repository.db.execute('SELECT chunk_id FROM chunks WHERE extraction_id=?', (first['extraction_id'],)).fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            repository.db.execute('INSERT INTO extraction_asset_classes VALUES (?,?,?,?)',
                                  (second['extraction_id'], 'rwa', 'test-only', first_chunk))
    finally:
        repository.close()


def test_second_document_failure_does_not_change_first_result(workspace):
    root, path = workspace
    first = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    class BadSecond(OfflineFetcher):
        def get(self, url, expected_type):
            download = super().get(url, expected_type)
            return replace(download, content=b'%PDF-1.7\nbroken') if url == SECOND_URL else download
    with pytest.raises(PipelineError):
        ingest(root, path, SOURCES, fetcher_factory=BadSecond, document_url=SECOND_URL)
    repeated = ingest(root, path, SOURCES, fetcher_factory=OfflineFetcher)
    assert repeated['extraction_id'] == first['extraction_id'] and repeated['status'] == 'reused'
    assert repeated['counts']['extractions'] == 1
    assert repeated['counts']['chunks'] == 113
