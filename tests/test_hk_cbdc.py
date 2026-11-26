import json
from pathlib import Path

import pytest

import hk_cbdc_collection as collection
from hk_cbdc_data import corpus, export_corpus
from research_publications import sources, save_publication, publication_fetcher
from virtual_asset_agent.collectors.hk_cbdc import classification, listing, html_metadata
from virtual_asset_agent.fetching import Download, SourceAccessError
from collection_service import save_json

URL = 'https://www.hkma.gov.hk/eng/news-and-media/press-releases/2025/10/20251028-4/'
CHANNEL = dict(url='https://www.hkma.gov.hk/topic/', heading='CBDC', body_selector='#listing', publisher='HKMA')
ARTICLE = ('<html><h1>e-HKD pilot report</h1><div class="content-area"><div class="date">28 Oct 2025</div></div>'
           '<div class="template-content-area">' + 'Hong Kong e-HKD retail CBDC research and tokenised deposits. ' * 15 + '</div></html>').encode()


def source():
    return dict(html_metadata(ARTICLE, 'HKMA'), url=URL, publisher='HKMA', collection='hk_cbdc',
                topic='CBDC', authority='primary', kind='Press release')


def test_scope_does_not_label_tokenised_deposits_as_cbdc_or_pilot_as_issuance():
    with pytest.raises(ValueError, match='evidence'):
        classification('Hong Kong tokenised deposits settlement')
    got = classification('Project Ensemble tests wholesale CBDC settlement of tokenised deposits in Hong Kong.')
    assert got['projects'] == ['ensemble']
    assert got['asset_classes_mentioned'] == ['CBDC', 'Tokenised deposits']
    assert got['project_stage'] == 'not_assessed'
    assert got['cbdc_types_mentioned'] == ['wholesale']
    assert classification('Project LionRock-Inthanon cross-border payments')['projects'] == ['mbridge']


def test_listing_rejects_other_hosts_chinese_and_duplicates():
    data = ('<html><h1>CBDC</h1><div id="listing">' +
            f'<a href="{URL}">e-HKD</a><a href="{URL}#a">duplicate</a>' +
            '<a href="https://evil.example/fake.pdf">foreign</a>' +
            '<a href="/chi/news-and-media/press-releases/2025/10/20251028-4/">Chinese</a></div></html>').encode()
    found = listing(data, CHANNEL)
    assert len(found) == 1 and found[0]['url'] == URL
    with pytest.raises(ValueError, match='identity'):
        listing(data.replace(b'CBDC', b'wrong'), CHANNEL)


def test_html_date_evidence_and_bis_visible_date_gate():
    assert html_metadata(ARTICLE, 'HKMA')['published'] == '2025-10-28'
    with pytest.raises(ValueError, match='date'):
        html_metadata(ARTICLE.replace(b'class="date"', b'class="missing"'), 'HKMA')
    bis = b'<html><meta property="article:published_time" content="2023-09-12T14:00:00+0200"><article><h1>Project Sela</h1>retail CBDC 12 September 2023</article></html>'
    assert html_metadata(bis, 'BIS')['published'] == '2023-09-12'
    with pytest.raises(ValueError, match='visible'):
        html_metadata(bis.replace(b'12 September 2023', b''), 'BIS')


def test_url_dedup_roundtrip_export_and_tampered_raw(tmp_path):
    src = source()
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [src])
    d = Download(ARTICLE, URL, 'text/html', '2026-11-23T00:00:00Z')
    assert save_publication(tmp_path, src, d) == 'created'
    assert save_publication(tmp_path, src, d) == 'reused'
    summary = export_corpus(tmp_path)
    assert summary['documents'] == 1 and summary['missing_configured_urls'] == []
    docs, chunks = corpus(tmp_path)
    assert all(c['citation']['source_url'] == URL and c['citation']['page'] is None for c in chunks)
    assert len(list((tmp_path / 'data/ingestion/research_versions').glob('*.json'))) == 1
    (tmp_path / docs[0]['raw_path']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='validation failed'):
        export_corpus(tmp_path)


def test_catalogue_keeps_collections_separate_and_rejects_duplicate_static_url(tmp_path):
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [source()])
    save_json(tmp_path / 'data/ingestion/hk_cbdc/discovered_sources.json', [source()])
    assert len(sources(tmp_path)) == 1
    save_json(tmp_path / 'config/research_sources.json', [source()])
    with pytest.raises(ValueError, match='Duplicate'):
        sources(tmp_path)


def test_persistent_queue_and_denial_stop_host(tmp_path, monkeypatch):
    save_json(tmp_path / 'config/hk_cbdc_discovery.json', [CHANNEL])
    index = f'<html><h1>CBDC</h1><div id="listing"><a href="{URL}">e-HKD</a><a href="/new.pdf">report</a></div></html>'.encode()
    calls = []
    class FakeFetcher:
        def get(self, url, expected):
            calls.append(url)
            return Download(index if url == CHANNEL['url'] else ARTICLE, url, 'text/html', '2026-11-23T00:00:00Z')
        def close(self):
            pass
    monkeypatch.setattr(collection, 'publication_fetcher', lambda *args: FakeFetcher())
    collection.discover(tmp_path)
    assert len(sources(tmp_path)) == 1
    collection.discover(tmp_path)
    assert calls.count(URL) == 1
    queue = json.loads((tmp_path / 'data/ingestion/hk_cbdc/candidates.json').read_text())
    assert queue['https://www.hkma.gov.hk/new.pdf']['status'] == 'needs_pdf_review'
    results = collection.discover(tmp_path, blocked_hosts=['www.hkma.gov.hk'])
    assert results[0]['error_type'] == 'SourceAccessError'
    assert len(sources(tmp_path)) == 1


def test_size_override_has_hard_upper_bound(tmp_path):
    with pytest.raises(ValueError, match='size limit'):
        publication_fetcher(tmp_path, dict(url=URL, publisher='HKMA', max_bytes=100*1024*1024))


def test_scheduled_cycle_wires_discovery_without_second_refresh(tmp_path, monkeypatch):
    import collection_service as service
    class Reader:
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
    db = tmp_path / 'test.sqlite'; db.touch()
    save_json(tmp_path / 'config/hk_cbdc_discovery.json', [])
    calls = []
    monkeypatch.setattr(service, 'load_sources', lambda *args: {})
    monkeypatch.setattr(service, 'Reader', Reader)
    monkeypatch.setattr(collection, 'cycle', lambda root, **kwargs: calls.append(kwargs) or {'results': []})
    service.collect_once(tmp_path, db)
    assert calls == [dict(refresh=False, blocked_hosts=set())]


def test_reviewed_claim_is_flagged_after_source_changes(tmp_path):
    from hk_cbdc_evidence import evidence_report
    src = source()
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [src])
    save_publication(tmp_path, src, Download(ARTICLE, URL, 'text/html', '2026-11-23T00:00:00Z'))
    docs, chunks = corpus(tmp_path)
    claim = dict(id='pilot', source_url=URL, anchor='e-HKD retail CBDC research', reviewed_sha256=docs[0]['content_sha256'])
    save_json(tmp_path / 'config/hk_cbdc_evidence.json', [claim])
    assert evidence_report(tmp_path, docs, chunks)['validated'] == 1
    docs[0]['content_sha256'] = 'changed'
    result = evidence_report(tmp_path, docs, chunks)
    assert result['validated'] == 0
    assert result['claims'][0]['status'] == 'source_changed_needs_review'


def test_pooled_fetcher_uses_each_publication_size_limit(tmp_path):
    from research_publications import collect_publication
    class Fetcher:
        options = {}
        observed = []
        def get(self, url, expected):
            self.observed.append(self.options['max_bytes'])
            return Download(ARTICLE, url, expected, '2026-11-23T00:00:00Z')
    f = Fetcher()
    collect_publication(tmp_path, dict(source(), max_bytes=50*1024*1024), f)
    collect_publication(tmp_path, source(), f)
    assert f.observed == [50*1024*1024, 12*1024*1024]


def test_date_review_preserves_collection_time_and_rejects_missing_anchor(tmp_path):
    from hk_cbdc_data import apply_date_reviews, validate
    src = source()
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [src])
    stamp = '2026-11-23T00:00:00Z'
    save_publication(tmp_path, src, Download(ARTICLE, URL, 'text/html', stamp))
    review = dict(url=URL, source_url=URL, published='2025-10', precision='month', anchor='e-HKD retail CBDC research')
    assert apply_date_reviews(tmp_path, [review]) == 1
    docs, chunks = corpus(tmp_path)
    assert docs[0]['collected_at'] == stamp and docs[0]['published'] == '2025-10'
    assert validate(tmp_path, docs, chunks)['status'] == 'passed'
    # Cosmetic HTML changes are allowed if the reviewed original remains and
    # the date statement is still present; a changed target remains a failure.
    docs[0]['publication_date_provenance']['document_sha256'] = 'changed'
    assert validate(tmp_path, docs, chunks)['status'] == 'failed'
    with pytest.raises(ValueError, match='anchor'):
        apply_date_reviews(tmp_path, [dict(review, anchor='Missing evidence')])
    with pytest.raises(ValueError, match='Duplicate'):
        apply_date_reviews(tmp_path, [review, review])
    assert corpus(tmp_path)[0][0]['published'] == '2025-10'


def test_download_budget_closes_slow_response_without_retry(tmp_path, monkeypatch):
    from unittest.mock import Mock
    import virtual_asset_agent.fetching as fetching
    from virtual_asset_agent.common import PipelineError
    now = [0.0]
    monkeypatch.setattr(fetching.time, 'monotonic', lambda: now[0])
    response = Mock(status_code=200, headers={'Content-Type': 'text/html'})
    def slow_body(**kwargs):
        yield b'<html>'
        now[0] = 91
        yield b'late body</html>'
    response.iter_content.side_effect = slow_body
    fetcher = publication_fetcher(tmp_path, source())
    fetcher.session.close()
    session = Mock()
    session.get.return_value = response
    fetcher.session = session
    with pytest.raises(PipelineError, match='time budget'):
        fetcher.get(URL, 'text/html')
    assert session.get.call_count == 1
    response.close.assert_called_once()


def test_question_acceptance_detects_missing_evidence_and_keeps_gaps_explicit(tmp_path):
    from hk_cbdc_questions import check_questions
    src = source()
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [src])
    save_publication(tmp_path, src, Download(ARTICLE, URL, 'text/html', '2026-11-24T00:00:00Z'))
    docs, _ = corpus(tmp_path)
    claim = dict(id='pilot', source_url=URL, anchor='e-HKD retail CBDC research',
                 reviewed_sha256=docs[0]['content_sha256'], statement='Research only', as_of='2025-10-28')
    save_json(tmp_path / 'config/hk_cbdc_evidence.json', [claim])
    cases = [dict(id='positive', question='What was studied?', expected='supported', evidence_ids=['pilot'], limits='Historical'),
             dict(id='negative', question='Full launch date?', expected='insufficient', evidence_ids=[], limits='Not established')]
    save_json(tmp_path / 'config/hk_cbdc_questions.json', cases)
    result = check_questions(tmp_path)
    assert result['supported_questions'] == 1 and result['documented_gaps'] == 1
    assert result['cases'][0]['citations'][0]['citation']['source_url'] == URL
    claim['anchor'] = 'not present'
    save_json(tmp_path / 'config/hk_cbdc_evidence.json', [claim])
    assert check_questions(tmp_path)['unresolved'] == 1


def test_unnamed_historical_context_requires_review_and_surviving_evidence(tmp_path):
    from hk_cbdc_data import validate
    src = dict(source(), projects=[], kind='Speech')
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [src])
    save_publication(tmp_path, src, Download(ARTICLE, URL, 'text/html', '2026-11-24T00:00:00Z'))
    docs, chunks = corpus(tmp_path)
    assert validate(tmp_path, docs, chunks)['status'] == 'failed'
    docs[0]['context_scope_review'] = dict(scope='hong_kong_cbdc_history', reason='Reviewed historical context',
        anchors=['e-HKD retail CBDC research', 'CBDC'])
    assert validate(tmp_path, docs, chunks)['status'] == 'passed'
    docs[0]['context_scope_review']['anchors'][0] = 'Removed policy context'
    assert validate(tmp_path, docs, chunks)['status'] == 'failed'


def test_handoff_rejects_partial_refresh_and_unshared_source_catalogue(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('handoff_check', Path(__file__).resolve().parents[1] / 'scripts/validate_hk_cbdc.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    src = source()
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [src])
    save_publication(tmp_path, src, Download(ARTICLE, URL, 'text/html', '2026-11-26T00:00:00Z'))
    docs, _ = corpus(tmp_path)
    save_json(tmp_path / 'config/hk_cbdc_evidence.json', [dict(id='pilot', source_url=URL,
        anchor='e-HKD retail CBDC research', reviewed_sha256=docs[0]['content_sha256'], statement='Research only', as_of='2025-10-28')])
    save_json(tmp_path / 'config/hk_cbdc_projects.json', [dict(id='e_hkd', evidence_ids=['pilot'])])
    save_json(tmp_path / 'config/hk_cbdc_questions.json', [dict(id='q', question='What research?', expected='supported', evidence_ids=['pilot'], limits='Historical')])
    checkpoint = tmp_path / 'data/ingestion/hk_cbdc/run_checkpoint.json'
    save_json(checkpoint, dict(status='success', phase='complete'))
    assert module.validate_handoff(tmp_path)['status'] == 'passed'
    save_json(checkpoint, dict(status='partial_failure', phase='complete'))
    assert not module.validate_handoff(tmp_path)['checks']['latest_complete_cycle']
    save_json(tmp_path / 'config/hk_cbdc_sources.json', [])
    save_json(tmp_path / 'data/ingestion/hk_cbdc/discovered_sources.json', [src])
    assert not module.validate_handoff(tmp_path)['checks']['source_catalogue_portable']
