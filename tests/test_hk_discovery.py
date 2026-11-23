import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import hk_discovery as discovery
from research_publications import sources
from virtual_asset_agent.collectors.hk_channels import (
    listing, html_metadata, pdf_metadata, same_host_link, charltons_pdf, OutsideScope)

FIXTURES = Path(__file__).parent / 'fixtures/hk_discovery'
CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'config/hk_discovery.json').read_text())


@pytest.mark.parametrize('channel,fixture', list(zip(CONFIG, ['hkma', 'charltons', 'asifma-search', 'll-hk-search'])))
def test_live_listing_fixtures_preserve_host_and_relevant_candidates(channel, fixture):
    found, _ = listing((FIXTURES / (fixture + '.html')).read_bytes(), channel, channel['url'])
    assert found
    assert len({c['url'] for c in found}) == len(found)
    assert all(same_host_link(channel['url'], c['url']) == c['url'] for c in found)
    if channel['id'] == 'hkma':
        assert not any('/press-releases/' in c['url'] for c in found)
    if channel['id'] == 'asifma':
        assert len(found) == 4
        assert all('HKMA' in c['title'] for c in found)
        assert not any('MAS' in c['title'] for c in found)


def test_regional_bulletin_does_not_confuse_singapore_with_hong_kong():
    content = (FIXTURES / 'll-article.html').read_bytes()
    with pytest.raises(OutsideScope):
        html_metadata(content, CONFIG[3])
    # A future HK section containing stablecoin developments is admissible.
    changed = content.replace(b'various tokenisation initiatives', b'various stablecoin initiatives')
    metadata = html_metadata(changed, CONFIG[3])
    assert metadata['published'] == '2026-10-27'
    assert metadata['body_selector'] == 'article.post-view .post-view__body'


def test_layout_failure_and_pagination_host_are_not_silent():
    with pytest.raises(ValueError, match='layout'):
        listing(b'<html>Login</html>', CONFIG[1], CONFIG[1]['url'])
    assert same_host_link(CONFIG[1]['url'], 'https://evil.test/report.pdf') is None
    assert same_host_link(CONFIG[1]['url'], 'javascript:alert(1)') is None


def test_charltons_download_query_is_preserved_and_references_are_excluded():
    html = b'''<html><h1 class="entry-title">HKMA stablecoin licences</h1>
    <a href="/legal/newsletters/725/licences.pdf?v=1.0">Download the PDF</a>
    <a href="/legal/newsletters/695/guideline.pdf">Related guideline</a></html>'''
    title, url = charltons_pdf(html, CONFIG[1]['url'])
    assert title == 'HKMA stablecoin licences'
    assert url == 'https://www.charltonslaw.com/legal/newsletters/725/licences.pdf?v=1.0'


def test_pdf_does_not_infer_date_from_multiple_body_dates(monkeypatch):
    from virtual_asset_agent.collectors import hk_channels
    fake = SimpleNamespace(is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda:
        'HKMA stablecoin consultation response\n30 June 2025\n26 May 2025')])
    monkeypatch.setattr(hk_channels, 'PdfReader', lambda _: fake)
    metadata = pdf_metadata(b'pdf', dict(title='ASIFMA HKMA stablecoin response'), CONFIG[2])
    assert metadata['published'] == ''
    assert metadata['published_precision'] == 'unknown'


def test_new_document_is_registered_visible_and_not_downloaded_twice(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    channel = CONFIG[2]
    (tmp_path / 'config/hk_discovery.json').write_text(json.dumps([channel]))
    link = 'https://www.asifma.org/new-response.pdf'
    html = f'<html><section class="mk-search-loop"><article class="research"><h3 class="the-title"><a href="{link}">HKMA stablecoin response</a></h3></article></section></html>'.encode()
    requests, saves = [], []
    class Fetcher:
        def get(self, url, mime):
            requests.append(url)
            return SimpleNamespace(content=html if url == channel['url'] else b'%PDF-test',
                                   collected_at='2026-11-20T00:00:00Z', downloaded_url=url)
        def close(self):
            pass
    monkeypatch.setattr(discovery, 'publication_fetcher', lambda *args: Fetcher())
    monkeypatch.setattr(discovery, 'pdf_metadata', lambda *args: dict(title='HKMA stablecoin response',
        format='pdf', published='', published_precision='unknown'))
    def save(root, source, downloaded):
        saves.append(source)
        return 'created'
    monkeypatch.setattr(discovery, 'save_publication', save)
    assert discovery.discover_hk(tmp_path) == [dict(source_url=link, status='created')]
    assert sources(tmp_path)[0]['url'] == link
    assert discovery.discover_hk(tmp_path) == []
    assert requests.count(link) == 1
    assert saves[0]['authority'] == 'secondary'
    assert (tmp_path / saves[0]['listing_raw_path']).exists()


def test_blocked_host_is_not_requested_and_other_channels_continue(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/hk_discovery.json').write_text(json.dumps(CONFIG[:2]))
    calls = []
    class Fetcher:
        def get(self, url, mime):
            calls.append(url)
            raise ValueError('Fixture layout error')
        def close(self):
            pass
    monkeypatch.setattr(discovery, 'publication_fetcher', lambda *args: Fetcher())
    result = discovery.discover_hk(tmp_path, {'www.hkma.gov.hk'})
    assert calls == [CONFIG[1]['url']]
    assert result[0]['error_type'] == 'SourceAccessError'
    assert len(result) == 2
