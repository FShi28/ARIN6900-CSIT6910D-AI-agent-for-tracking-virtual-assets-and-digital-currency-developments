import json
from pathlib import Path
from types import SimpleNamespace

import research_publications as research


def test_failed_refresh_preserves_last_good_source_and_continues(tmp_path, monkeypatch):
    config = Path(__file__).resolve().parents[1] / 'config/research_sources.json'
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/research_sources.json').write_bytes(config.read_bytes())
    publications = research.sources(tmp_path)
    prior = dict(publications[0], collected_at='2026-04-24T00:00:00Z', chunks=[])
    path = research.snapshot_path(tmp_path, prior['url'])
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(prior), encoding='utf-8')

    attempts = []
    def invalid_download(self, url, media_type):
        attempts.append(url)
        return SimpleNamespace(content=b'%PDF-incomplete', collected_at='2026-11-13T00:00:00Z')

    monkeypatch.setattr(research.Fetcher, 'get', invalid_download)
    results = research.collect_research(tmp_path)
    assert attempts == [pub['url'] for pub in publications if pub.get('format') != 'source_note']
    assert all(r['status'] == 'failed' for r in results)
    loaded = research.load_publications(tmp_path)
    assert [pub for pub in loaded if pub.get('format') != 'source_note'] == [prior]
    for pub in loaded:
        if pub.get('format') == 'source_note':
            assert pub['chunks'][0]['page_start'] is None
            assert pub['chunks'][0]['text'] == pub['note']


def test_html_article_excludes_unrelated_page_sections():
    source = dict(title='Digital bonds', format='html', body_selector='main article')
    content = b'<html><h1>Digital bonds</h1><main><article>Issuance details</article></main><aside>Related</aside></html>'
    assert research.publication_pages(content, source) == ['Issuance details']
