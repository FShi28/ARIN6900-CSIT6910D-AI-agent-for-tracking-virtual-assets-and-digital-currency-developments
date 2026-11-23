"""UI smoke tests never start a network worker or touch production data."""

import hashlib
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import live_documents
from collection_service import CollectionService
from test_reader import dataset  # Reuse the synthetic schema-v2 fixture.

ROOT = Path(__file__).resolve().parents[1]


def test_original_download_checks_path_and_hash(tmp_path):
    raw = tmp_path / 'data/raw/test.pdf'
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b'%PDF-synthetic')
    document = {'raw_path': 'data/raw/test.pdf', 'content_sha256': hashlib.sha256(raw.read_bytes()).hexdigest()}
    assert live_documents.original_bytes(tmp_path, document) == raw.read_bytes()
    document['content_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='hash'):
        live_documents.original_bytes(tmp_path, document)
    document['raw_path'] = '../outside.pdf'
    with pytest.raises(ValueError, match='path'):
        live_documents.original_bytes(tmp_path, document)


def test_real_document_view_and_empty_filter(dataset, tmp_path):
    app = AppTest.from_string(f'''from pathlib import Path
from live_documents import document_panel
document_panel(Path({str(tmp_path)!r}), Path({str(dataset['path'])!r}))
''', default_timeout=20).run()
    assert not app.exception
    assert app.metric[0].value == '2'
    assert app.text_area[0].value == 'Stablecoin reserve assets changed.'
    assert any('Original download unavailable' in warning.value for warning in app.warning)
    app.text_input[0].set_value('no-matching-document').run()
    assert not app.exception
    assert any('No documents match' in info.value for info in app.info)


def test_missing_database_and_failed_collection_remain_visible(tmp_path):
    worker = CollectionService(tmp_path, runner=lambda root, db: (_ for _ in ()).throw(ValueError('Synthetic failure')))
    worker.configure(False, 24)
    worker.request_run()
    worker.tick()
    code = f'''from pathlib import Path
from collection_service import CollectionService
from live_documents import collection_panel, document_panel
root = Path({str(tmp_path)!r})
collection_panel(CollectionService(root))
document_panel(root, root / 'data/ingestion/hkma.sqlite')
'''
    app = AppTest.from_string(code, default_timeout=20).run()
    assert not app.exception
    assert any('Synthetic failure' in error.value for error in app.error)
    assert any('Waiting for the first collection' in info.value for info in app.info)
    app.button[-1].click().run()
    assert worker.settings()['request_id'] != worker.snapshot()['state']['handled_request_id']


def test_app_defaults_to_real_overview(tmp_path, monkeypatch):
    import app_data
    frames = app_data.regulatory_frames({'documents': [], 'chunks': []})
    monkeypatch.setattr(app_data, 'load_app_data', lambda root: (*frames, app_data.market_frame([]), []))
    app = AppTest.from_file(str(ROOT / 'src/app.py')).run(timeout=20)
    assert not app.exception
    assert app.sidebar.radio[0].value == 'Overview'
    app.sidebar.radio[0].set_value('Market Signals').run(timeout=20)
    assert not app.exception
    assert any('No market values' in i.value for i in app.info)
