"""Offline official-response fixtures and isolated regional SQLite checks."""
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from regional_ingestion import ingest_one, parse
from virtual_asset_agent.fetching import Download
from virtual_asset_agent.storage import init_database
from virtual_asset_agent.reader import Reader
from virtual_asset_agent.common import PipelineError

ROOT = Path(__file__).resolve().parents[1]
SOURCES = json.loads((ROOT / 'config/regional_sources.json').read_text())['sources']


class FixtureFetcher:
    def __init__(self, source, log): self.source = source
    def close(self): pass
    def get(self, url, media_type):
        suffix = 'pdf' if media_type == 'application/pdf' else 'html'
        data = (ROOT / f"tests/fixtures/regional/{self.source['source_id']}.{suffix}").read_bytes()
        return Download(data, url, media_type, '2026-10-28T08:30:00Z')


@pytest.mark.parametrize('source', SOURCES, ids=lambda s:s['source_id'])
def test_ingest_repeat_and_exact_evidence(tmp_path, source):
    (tmp_path/'db').mkdir()
    shutil.copy(ROOT/'db/regional_schema.sql',tmp_path/'db/regional_schema.sql')
    path=tmp_path/'data/ingestion/regional.sqlite'
    init_database(path,tmp_path/'db/regional_schema.sql')
    first=ingest_one(tmp_path,source,FixtureFetcher)
    second=ingest_one(tmp_path,source,FixtureFetcher)
    assert first['status']=='created' and second['status']=='reused'
    with Reader(path) as reader:
        d=reader.list_documents()[0]
        assert d['jurisdiction']==source['jurisdiction']
        e=reader.get_extraction(d['extraction_id'],include_text=True)
        for c in reader.list_chunks(d['extraction_id'],limit=100):
            assert e['clean_text'][c['char_start']:c['char_end']]==c['text']
        if source['source_id']=='mas': assert 'tokenized_deposit' in d['asset_classes']
        if source['source_id']=='esma': assert 'More on the same topic' not in e['clean_text']
        if source['source_id']=='fca': assert 'Was this page useful' not in e['clean_text']
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


@pytest.mark.parametrize('source', SOURCES, ids=lambda s:s['source_id'])
def test_error_pages_not_ingested(source):
    with pytest.raises(PipelineError):
        parse(b'<html><h1>Service unavailable</h1></html>',source)


def test_disabled_source_never_downloads(tmp_path):
    def unexpected_fetch(*args):
        pytest.fail('Disabled source must not create a fetcher')
    with pytest.raises(PipelineError, match='disabled'):
        ingest_one(tmp_path, dict(SOURCES[0], enabled=False), unexpected_fetch)
