import json
from types import SimpleNamespace

import pytest

import hk_stablecoin_data as hk
import research_publications as research
from virtual_asset_agent.fetching import SourceAccessError


def test_topic_audit_includes_attachments_but_excludes_navigation_and_external_links():
    content = b'''<html><h1>Regulatory Regime for Stablecoin Issuers</h1>
    <nav><a href="/navigation.pdf">Navigation</a></nav>
    <div class="template-top-background full-content-printer">
    <a href="/media/aml.pdf">AML guideline</a><a href="/media/aml.pdf#page=2">Duplicate</a>
    <a href="https://www.elegislation.gov.hk/hk/cap656">Ordinance</a>
    <a href="https://unrelated.test/report.pdf">Unrelated</a></div></html>'''
    assert {l['url'] for l in hk.topic_links(content)} == {
        'https://www.hkma.gov.hk/media/aml.pdf', 'https://www.elegislation.gov.hk/hk/cap656'}
    with pytest.raises(ValueError, match='heading'):
        hk.topic_links(content.replace(b'Regulatory Regime', b'Unexpected heading'))


def test_government_html_requires_headline_and_date_and_excludes_sidebar():
    source = dict(title='Stablecoins update', format='html', heading_selector='#PRHeadlineSpan',
                  body_selector='#pressrelease', date_document_evidence='Ends/Friday, June 6, 2025')
    content = b'''<html><span id="PRHeadlineSpan">Stablecoins update</span>
    <span id="pressrelease">A <a>stablecoin</a> update.<script>junk()</script></span>
    <div>Ends/Friday, June 6, 2025</div><aside>Unrelated news</aside></html>'''
    assert research.publication_pages(content, source) == ['A stablecoin update.']
    with pytest.raises(ValueError, match='date evidence'):
        research.publication_pages(content.replace(b'June 6', b'June 7'), source)


def test_pdf_cover_date_must_match_even_when_title_matches(monkeypatch):
    pdf = SimpleNamespace(is_encrypted=False, metadata=None,
        pages=[SimpleNamespace(extract_text=lambda: 'Stablecoin guideline August 2025')])
    monkeypatch.setattr(research, 'PdfReader', lambda _: pdf)
    source = dict(title='Stablecoin guideline', date_evidence='August 2025')
    assert research.publication_pages(b'fake', source) == ['Stablecoin guideline August 2025']
    with pytest.raises(ValueError, match='date evidence'):
        research.publication_pages(b'fake', dict(source, date_evidence='August 2026'))


def test_denial_stops_same_host_but_other_publisher_continues(tmp_path, monkeypatch):
    selected = [dict(url='https://blocked.test/one.pdf', publisher='Blocked'),
                dict(url='https://blocked.test/two.pdf', publisher='Blocked'),
                dict(url='https://open.test/one.pdf', publisher='Open')]
    attempts = []
    def collect(root, source, fetcher):
        attempts.append(source['url'])
        if source['publisher'] == 'Blocked':
            raise SourceAccessError('HTTP 429')
        return 'reused'
    monkeypatch.setattr(research, 'collect_publication', collect)
    results = research.collect_research(tmp_path, selected)
    assert attempts == [selected[0]['url'], selected[2]['url']]
    assert [r['status'] for r in results] == ['failed', 'failed', 'reused']


def test_snapshot_repeat_is_idempotent_and_bad_refresh_preserves_evidence(tmp_path):
    source = dict(url='https://example.test/article', publisher='Example', title='Stablecoins',
                  format='html', body_selector='article')
    text = 'Stablecoin reserve assets must be maintained. ' * 15
    download = SimpleNamespace(content=f'<html><h1>Stablecoins</h1><article>{text}</article></html>'.encode(),
                               collected_at='2026-11-19T00:00:00Z', downloaded_url=source['url'])
    assert research.save_publication(tmp_path, source, download) == 'created'
    initial = json.loads(research.snapshot_path(tmp_path, source['url']).read_text())
    download.collected_at = '2026-11-19T01:00:00Z'
    assert research.save_publication(tmp_path, source, download) == 'reused'
    assert len(list((tmp_path / 'data/ingestion/research_versions').glob('*.json'))) == 1
    download.content = b'<html><h1>Login required</h1></html>'
    with pytest.raises(ValueError):
        research.save_publication(tmp_path, source, download)
    retained = json.loads(research.snapshot_path(tmp_path, source['url']).read_text())
    assert retained['chunks'] == initial['chunks']
    assert retained['content_sha256'] == initial['content_sha256']


def test_export_labels_secondary_sources_and_unknown_dates(tmp_path, monkeypatch):
    pub = dict(url='https://example.test/report', publisher='Example', kind='Legal commentary',
        title='HK stablecoins', topic='Stablecoins', collection='hk_stablecoins', published='',
        format='html', chunks=[dict(chunk_id='c1', page_start=None, text='An industry interpretation.')])
    monkeypatch.setattr(hk, 'sources', lambda _: [pub])
    monkeypatch.setattr(hk, 'load_publications', lambda _: [pub])
    summary = hk.export_corpus(tmp_path)
    exported = json.loads((tmp_path / 'data/exports/hk_stablecoins/chunks.jsonl').read_text())
    assert summary['documents'] == 1
    assert summary['primary_database_present'] is False
    assert exported['authority'] == 'secondary'
    assert exported['published'] == ''
    assert exported['published_precision'] == 'unknown'
    assert exported['citation']['url'] == pub['url']
