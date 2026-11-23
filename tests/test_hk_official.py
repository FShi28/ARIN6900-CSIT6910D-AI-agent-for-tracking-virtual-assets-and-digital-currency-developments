import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hk_discovery import discover_hk, known_urls
from research_publications import load_publications, publication_pages
from virtual_asset_agent.collectors.hk_official import official_listing, official_metadata
from virtual_asset_agent.collectors.hk_official import brdr_listing, brdr_pdf

FIX = Path(__file__).parent / 'fixtures/hk_discovery'
CONFIG = json.loads((FIX.parents[2] / 'config/hk_discovery.json').read_text())
CHANNELS = [next(c for c in CONFIG if c['id'] == key) for key in ('hksar', 'sfc')]


def test_live_rss_valid_empty_scope_and_schema_errors():
    assert official_listing((FIX / 'gov-rss.xml').read_bytes(), CHANNELS[0], CHANNELS[0]['url']) == ([], None)
    for bad in (b'<html>error</html>', b'<!DOCTYPE rss><rss/>'):
        with pytest.raises(ValueError):
            official_listing(bad, CHANNELS[0], CHANNELS[0]['url'])


def test_live_sfc_pagination_and_subject_filter():
    results = []
    for i in range(3):
        rows, total = official_listing((FIX / f'sfc-page-{i}.json').read_bytes(), CHANNELS[1], CHANNELS[1]['url'])
        assert total == 46
        results.extend(rows)
    assert len(results) == 1
    assert results[0]['url'].endswith('lang=EN&refNo=26EC26')


@pytest.mark.parametrize('idx,name,date', [(0, 'gov', '2026-06-10'), (1, 'sfc', '2026-05-27')])
def test_official_body_date_and_normalization(idx, name, date):
    content = (FIX / f'{name}-article.html').read_bytes()
    metadata = official_metadata(content, CHANNELS[idx])
    assert metadata['published'] == date
    assert 'stablecoin' in publication_pages(content, metadata)[0].lower()


def test_government_discovery_real_body_persistence_and_dedup(tmp_path, monkeypatch):
    import hk_discovery
    channel = CHANNELS[0]
    url = 'https://www.info.gov.hk/gia/general/202606/10/P2026061000429.htm'
    # Synthetic feed wrapper around a saved real article, not a live-feed success claim.
    feed = f'<rss><channel><title>HKSAR Government Press Releases</title><item><title>Stablecoins</title><link>{url}</link></item></channel></rss>'.encode()
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/hk_discovery.json').write_text(json.dumps([channel]))
    calls = []
    class Fetcher:
        def get(self, target, mime):
            calls.append(target)
            return SimpleNamespace(content=feed if target == channel['url'] else (FIX / 'gov-article.html').read_bytes(),
                                   collected_at='2026-11-20T00:00:00Z', downloaded_url=target)
        def close(self):
            pass
    monkeypatch.setattr(hk_discovery, 'publication_fetcher', lambda *a: Fetcher())
    assert discover_hk(tmp_path)[0]['status'] == 'created'
    assert discover_hk(tmp_path) == []
    pubs = load_publications(tmp_path)
    assert len(pubs) == 1 and pubs[0]['authority'] == 'primary'
    assert pubs[0]['published'] == '2026-06-10' and pubs[0]['chunks']
    assert calls.count(url) == 1
    assert (tmp_path / pubs[0]['raw_path']).exists()


def test_government_print_url_alias(tmp_path):
    (tmp_path / 'config').mkdir()
    url = 'https://www.info.gov.hk/gia/general/202506/06/P2025060600275p.htm'
    (tmp_path / 'config/hk_stablecoin_sources.json').write_text(json.dumps([{'url':url}]))
    assert url.replace('p.htm', '.htm') in known_urls(tmp_path)


def test_rss_rejects_untrusted_candidate_url():
    feed = b'<rss><channel><title>HKSAR Government Press Releases</title><item><title>Stablecoin</title><link>https://evil.test/a</link></item></channel></rss>'
    with pytest.raises(ValueError, match='URL'):
        official_listing(feed, CHANNELS[0], CHANNELS[0]['url'])


def test_brdr_real_search_preserves_subject_and_english_scope():
    candidates, total = brdr_listing((FIX / 'brdr-results.json').read_bytes(), 'https://brdr.hkma.gov.hk/restapi/doc-search')
    assert total == 65 and len(candidates) == 4
    assert all(c['url'].endswith('-EN') for c in candidates)
    assert candidates[0]['repository_issue_date'] == '27 May 2026'
    assert not any('Capital' in c['title'] for c in candidates)


def test_brdr_download_uses_actual_primary_link_not_related_appendix():
    url = 'https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260527-2-EN'
    assert brdr_pdf((FIX / 'brdr-article.html').read_bytes(), url).endswith('/20260527-2-EN/20260527-2-EN.pdf')
    with pytest.raises(ValueError):
        brdr_pdf(b'<a href="https://evil.test/a.pdf">Download</a>', url)


def test_brdr_schema_errors_are_not_empty_success():
    for payload in ({'error':'unavailable'}, {'resultList':[], 'totalRecordNumber':5}):
        with pytest.raises(ValueError):
            brdr_listing(json.dumps(payload).encode(), 'https://brdr.hkma.gov.hk/restapi/doc-search')
