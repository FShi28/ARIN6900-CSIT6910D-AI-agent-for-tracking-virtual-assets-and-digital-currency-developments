"""Original UI contract with real-schema evidence and unassessed analysis fields."""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

import app_data
from dashboard_data import load_corpus
from test_reader import dataset

ROOT = Path(__file__).resolve().parents[1]


def test_original_contract_without_invented_assessments(dataset):
    documents, developments, chunks = app_data.regulatory_frames(load_corpus(dataset['path']))
    assert len(documents) == len(developments) == len(chunks) == 2
    assert developments.risk_rating.tolist() == ['unknown', 'unknown']
    assert developments.confidence.isna().all()
    assert set(developments.review_status) == {'not_reviewed'}
    assert all(x.startswith('Publication: ') for x in developments.obligation_summary)
    assert all(set(ids) <= set(chunks.chunk_id) for ids in developments.evidence_chunk_ids)
    assert all(c.url.startswith('https://example.invalid/') for c in chunks.citation)
    assert app_data.assessment(None) == app_data.assessment(float('nan')) == 'Not assessed'


def test_original_pages_filter_unknown_and_display_citations(dataset, monkeypatch):
    frames = app_data.regulatory_frames(load_corpus(dataset['path']))
    monkeypatch.setattr(app_data, 'load_app_data', lambda root: (*frames, app_data.market_frame([]), []))
    app = AppTest.from_file(str(ROOT / 'src/app.py'), default_timeout=20).run()
    assert not app.exception
    assert any('Not assessed' in m.value for m in app.markdown)
    app.sidebar.radio[0].set_value('Regulatory Monitor').run()
    assert not app.exception
    assert 'unknown' in app.multiselect[2].value
    assert len(app.dataframe[0].value) == 2
    assert set(app.dataframe[0].value.confidence) == {'Not assessed'}
    assert any('Open source' in m.value for m in app.markdown)
    app.multiselect[2].set_value(['low']).run()
    assert not app.exception and app.dataframe[0].value.empty
    app.sidebar.radio[0].set_value('Ask the Analyst').run()
    app.text_input[0].set_value('reserve').run()
    assert not app.exception
    assert any('Stablecoin reserve assets changed.' in m.value for m in app.markdown)
    app.sidebar.radio[0].set_value('Market Signals').run()
    assert not app.exception


def test_market_contract_preserves_missing_values_and_real_protocol_names():
    frame = app_data.market_frame([{'source_id': 'defillama_rwa', 'status': 'stale', 'rows': [
        {'instrument': 'Synthetic Protocol', 'metric': 'protocol_tvl', 'value': 10,
         'provider': 'Synthetic provider', 'observed_at': None, 'collected_at': '2026-10-01T00:00:00Z'}]}])
    assert len(frame) == 3
    assert pd.isna(frame.iloc[0].value) and pd.isna(frame.iloc[1].value)
    assert frame.iloc[2].instrument == 'Synthetic Protocol'
    assert frame.iloc[2].data_quality == 'stale'
    assert frame.iloc[2].observed_at is None


def test_original_styles_and_layout_constructs_are_preserved():
    original = (ROOT / 'src/app_original.py').read_text(encoding='utf-8')
    current = (ROOT / 'src/app.py').read_text(encoding='utf-8')
    assert original.split('<style>')[1].split('</style>')[0] == current.split('<style>')[1].split('</style>')[0]
    for token in ['st.columns(4)', 'st.columns([1.35, 1])', 'st.columns(3)', 'st.columns(len(markets))',
                  'px.treemap(', 'px.bar(', '"Overview", "Regulatory Monitor", "Market Signals", "Ask the Analyst"']:
        assert token in current and token in original
    assert 'render_dashboard' not in current and 'load_jsonl' not in current


def test_individual_asset_filter_matches_multi_class_publication(dataset, monkeypatch):
    corpus = load_corpus(dataset['path'])
    corpus['documents'][0]['asset_classes'] = ['tokenized_security', 'tokenized_deposit']
    frames = app_data.regulatory_frames(corpus)
    monkeypatch.setattr(app_data, 'load_app_data', lambda root: (*frames, app_data.market_frame([]), []))
    app = AppTest.from_file(str(ROOT / 'src/app.py'), default_timeout=20).run()
    app.sidebar.radio[0].set_value('Regulatory Monitor').run()
    assert not app.exception
    assert 'tokenized_deposit' in app.multiselect[1].options
    assert 'tokenized_security, tokenized_deposit' not in app.multiselect[1].options
    app.multiselect[1].set_value(['tokenized_deposit']).run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 1
    app.multiselect[1].set_value(['tokenized_deposit', 'tokenized_security']).run()
    assert len(app.dataframe[0].value) == 1
