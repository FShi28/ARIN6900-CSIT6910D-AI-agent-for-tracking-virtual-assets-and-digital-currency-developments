"""Incremental comparison, historical evidence, and additive migration tests."""

import copy
import sqlite3
from unittest.mock import patch

import pytest

from test_html_ingestion import CONTENT, URL, ROOT, SOURCES, OfflineHTML, workspace
from virtual_asset_agent.common import PipelineError
from virtual_asset_agent.fetching import Download
from virtual_asset_agent.incremental import fingerprints
from virtual_asset_agent.pipeline import ingest
from virtual_asset_agent.storage import Repository, init_database, migrate_database


def fetcher(content):
    class Changed(OfflineHTML):
        def get(self, url, expected_type):
            d = super().get(url, expected_type)
            return Download(content, url, d.media_type, d.collected_at) if url == URL else d
    return Changed


def run(workspace, content=CONTENT, sources=SOURCES):
    root, db = workspace
    return ingest(root, db, sources, fetcher_factory=fetcher(content), document_url=URL)


@pytest.mark.parametrize('before,after', [
    (b'108 submissions', b'109 submissions'),
    (b'17 Jul 2024', b'18 Jul 2024'),
    (b'20240717e3a1.pdf', b'20240717e3a2.pdf'),
    (b'issuers in Hong Kong released', b'issuers in Hong Kong announced'),
    (b'<html lang="en">', b'<html lang="en-GB">'),
])
def test_material_changes_and_reversion(workspace, before, after):
    assert before in CONTENT
    first = run(workspace)
    changed = run(workspace, CONTENT.replace(before, after))
    assert changed['change_type'] == 'content_changed'
    assert changed['version_id'] != first['version_id']
    reverted = run(workspace)
    assert reverted['change_type'] == 'content_changed'
    assert reverted['version_id'] == first['version_id']
    assert reverted['status'] == 'reused'
    assert run(workspace)['change_type'] == 'unchanged'


def test_sidebar_changes_are_not_mistaken_for_regulatory_update(workspace):
    first = run(workspace)
    assert b'Latest Press Releases' in CONTENT
    changed = run(workspace, CONTENT.replace(b'Latest Press Releases', b'Recent Press Releases'))
    assert changed['change_type'] == 'page_changed'
    # Unknown page changes remain conservative; only the verified token is ignored.
    assert changed['version_id'] != first['version_id']


def test_processing_change_preserves_raw_and_creates_result(workspace):
    first = run(workspace)
    sources = copy.deepcopy(SOURCES)
    sources['hkma']['processing']['chunk_max_chars'] = 900
    second = run(workspace, sources=sources)
    assert second['change_type'] == 'unchanged'
    assert second['version_id'] == first['version_id']
    assert second['extraction_id'] != first['extraction_id'] and second['status'] == 'created'


def test_corrupt_historical_original_cannot_be_reused(workspace):
    first = run(workspace)
    (workspace[0]/first['raw_path']).write_bytes(b'corrupted')
    # Different response hash prevents immutable-file publication from masking this check.
    with pytest.raises(PipelineError, match='SHA-256'):
        run(workspace, CONTENT.replace(b'108 submissions', b'109 submissions'))


def test_observation_failure_rolls_back_entire_success_bundle(workspace):
    original = Repository._insert
    def fail(self, table, record):
        if table == 'html_observations':
            record = dict(record, change_type='invalid')
        return original(self, table, record)
    with patch.object(Repository, '_insert', fail), pytest.raises(sqlite3.IntegrityError):
        run(workspace)
    repo = Repository(workspace[1])
    try:
        c = repo.counts()
        assert c['document_versions'] == 1
        assert c['extractions'] == c['chunks'] == c['extraction_asset_classes'] == c['html_observations'] == 0
    finally:
        repo.close()


def test_migration_preserves_v1_rows_and_matches_fresh_schema(workspace, tmp_path):
    first = run(workspace)
    db = sqlite3.connect(workspace[1])
    original_tables = ('sources','documents','document_versions','extractions','chunks','extraction_asset_classes')
    before = {t: db.execute(f'SELECT * FROM {t}').fetchall() for t in original_tables}
    db.execute('DROP TABLE html_observations')
    db.execute('PRAGMA user_version=1')
    db.commit(); db.close()
    migration = ROOT/'db/migrations/002_html_observations.sql'
    assert migrate_database(workspace[1], migration)
    assert not migrate_database(workspace[1], migration)
    repo = Repository(workspace[1])
    try:
        for table in original_tables:
            assert [tuple(r) for r in repo.db.execute(f'SELECT * FROM {table}')] == before[table]
        assert repo.db.execute('PRAGMA foreign_key_check').fetchall() == []
        migrated_schema = [tuple(r) for r in repo.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name')]
    finally:
        repo.close()
    fresh = tmp_path/'fresh.sqlite'
    init_database(fresh, ROOT/'db/schema.sql')
    db = sqlite3.connect(fresh)
    assert db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() == migrated_schema
    db.close()
    # Existing successful legacy HTML is reusable without fabricated historical observations.
    again = run(workspace)
    assert again['version_id'] == first['version_id'] and again['status'] == 'reused'
    assert again['counts']['html_observations'] == 1


def test_observation_constraints_and_immutability(workspace):
    run(workspace)
    repo = Repository(workspace[1])
    try:
        with pytest.raises(sqlite3.IntegrityError):
            repo.db.execute("UPDATE html_observations SET change_type='page_changed'")
        row = dict(repo.db.execute('SELECT * FROM html_observations').fetchone())
        row.pop('observation_id');row['run_id']='orphan';row['extraction_id']='f'*64
        with pytest.raises(sqlite3.IntegrityError):
            repo._insert('html_observations',row)
        repo.db.rollback()
    finally:
        repo.close()
