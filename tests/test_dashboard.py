"""All workspace pages use temporary real-schema records, never canonical demo files."""

from pathlib import Path
import shutil

from streamlit.testing.v1 import AppTest

import dashboard_ui
from collection_service import CollectionService
from dashboard_data import load_corpus, search_evidence
from test_reader import dataset

ROOT = Path(__file__).resolve().parents[1]


def test_corpus_uses_current_versions_and_exact_citations(dataset):
    data = load_corpus(dataset['path'])
    assert len(data['documents']) == 2 and len(data['chunks']) == 2
    matches = search_evidence(data, 'What are the reserve assets?')
    assert len(matches) == 1
    assert matches[0]['extraction_id'] == dataset['e2']
    assert matches[0]['citation']['reference'] == 'chunk:' + dataset['c2']
    assert matches[0]['text'] == 'Stablecoin reserve assets changed.'
    assert matches[0]['matched_terms'] == ['assets', 'reserve']
    assert search_evidence(data, 'What is the?') == []
    assert search_evidence(data, 'reserve', jurisdiction='Singapore') == []


def test_original_four_pages_with_real_schema_data(dataset, tmp_path, monkeypatch):
    data = load_corpus(dataset['path'])
    service = CollectionService(tmp_path)
    service.configure(False, 24)
    monkeypatch.setattr(dashboard_ui, 'collection_service', lambda root: service)
    monkeypatch.setattr(dashboard_ui, 'corpus', lambda *args: data)
    monkeypatch.setattr(dashboard_ui, 'market_snapshot', lambda root: [
        {'source_id': 'synthetic', 'provider': 'Synthetic test provider', 'status': 'available',
         'collected_at': '2026-10-01T00:00:00Z', 'rows': [
             dict(instrument='BTC', asset_id='bitcoin', asset_class='cryptocurrency', metric='market_cap',
                  value=100, unit='USD', provider='Synthetic test provider', observed_at=None,
                  collected_at='2026-10-01T00:00:00Z', source_url='https://example.invalid/market')]}])
    database = tmp_path / 'data/ingestion/hkma.sqlite'
    database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(dataset['path'], database)
    observed = []
    monkeypatch.setattr(dashboard_ui, 'document_panel', lambda root, path, documents_override=None:
                        observed.append(documents_override))
    app = AppTest.from_string(f'from pathlib import Path\nfrom dashboard_ui import render_dashboard\n'
                             f'render_dashboard(Path({str(tmp_path)!r}))', default_timeout=20).run()
    assert not app.exception
    assert any(m.label == 'Tracked publications' and m.value == '2' for m in app.metric)
    app.sidebar.radio[0].set_value('Regulatory Monitor').run()
    assert not app.exception and len(observed[-1]) == 2
    app.multiselect[0].set_value([]).run()
    assert observed[-1] == []
    app.sidebar.radio[0].set_value('Market Signals').run()
    assert not app.exception
    assert any(m.label == 'BTC market cap (USD)' and m.value == '$100.00' for m in app.metric)
    app.sidebar.radio[0].set_value('Ask the Analyst').run()
    app.text_input[0].set_value('reserve assets').run()
    assert not app.exception
    assert any(t.value == 'Stablecoin reserve assets changed.' for t in app.text)
    assert any('Matched terms: assets, reserve' in c.value for c in app.caption)
    assert 'canonical' not in (ROOT / 'src/app.py').read_text(encoding='utf-8')
