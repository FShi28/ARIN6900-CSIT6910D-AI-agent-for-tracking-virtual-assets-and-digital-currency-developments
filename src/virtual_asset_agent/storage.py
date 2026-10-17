"""SQLite persistence with explicit identity reuse and atomic result bundles."""

import sqlite3
from pathlib import Path

from .common import PipelineError, identity

SOURCE_FIELDS = ('source_id', 'source_name', 'jurisdiction', 'regulator', 'source_type',
                 'discovery_url', 'verified_at', 'enabled')
TABLES = ('sources', 'documents', 'document_versions', 'extractions', 'chunks', 'extraction_asset_classes', 'html_observations')


def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        connection.close()
        raise PipelineError('SQLite foreign keys are not enabled')
    return connection


def init_database(path, schema_path):
    path = Path(path)
    if path.exists():
        raise PipelineError('Database already exists; initialization never overwrites it')
    if sqlite3.sqlite_version_info < (3, 38, 0):
        raise PipelineError('SQLite 3.38+ is required')
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(path)
    try:
        connection.executescript(Path(schema_path).read_text(encoding='utf-8'))
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def migrate_database(path, migration_path):
    if not Path(path).is_file():
        raise PipelineError('Database does not exist')
    db = connect(path)
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 2:
            return False
        if version != 1:
            raise PipelineError('Only schema v1 can migrate to v2')
        db.executescript(Path(migration_path).read_text(encoding='utf-8'))
        return True
    except sqlite3.Error:
        db.rollback()
        raise
    finally:
        db.close()


class Repository:
    def __init__(self, path):
        if not Path(path).is_file():
            raise PipelineError('Database does not exist; run init-db first')
        self.db = connect(path)
        if self.db.execute('PRAGMA user_version').fetchone()[0] != 2:
            self.db.close()
            raise PipelineError('Schema v2 required; run migrate-db for an existing v1 database')

    def close(self):
        self.db.close()

    def _insert(self, table, values):
        if table not in TABLES:
            raise PipelineError('Unknown storage entity')
        columns = ','.join(values)
        placeholders = ','.join('?' for _ in values)
        self.db.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(values.values()))

    def sync_sources(self, sources):
        with self.db:
            for source in sources.values():
                record = {key: source.get(key) for key in SOURCE_FIELDS}
                record['enabled'] = int(record['enabled'])
                existing = self.db.execute('SELECT * FROM sources WHERE source_id=?', (record['source_id'],)).fetchone()
                if existing is None:
                    self._insert('sources', record)
                else:
                    if any(existing[key] != record[key] for key in SOURCE_FIELDS[:5]):
                        raise PipelineError('Existing source identity/attribution cannot change')
                    self.db.execute('UPDATE sources SET discovery_url=?,verified_at=?,enabled=? WHERE source_id=?',
                                    (record['discovery_url'], record['verified_at'], record['enabled'], record['source_id']))

    def register_raw(self, source_id, source_url, download, content_hash, raw_path, parent_url):
        document_id = identity('document', source_id, source_url)
        version_id = identity('version', document_id, content_hash)
        with self.db:
            # Serialize identity checks with writes; no replace/ignore semantics.
            self.db.execute('BEGIN IMMEDIATE')
            if not self.db.execute('SELECT 1 FROM documents WHERE document_id=?', (document_id,)).fetchone():
                self._insert('documents', {'document_id': document_id, 'source_id': source_id, 'source_url': source_url})
            existing = self.db.execute('SELECT * FROM document_versions WHERE version_id=?', (version_id,)).fetchone()
            if existing is None:
                self._insert('document_versions', {
                    'version_id': version_id, 'document_id': document_id, 'content_sha256': content_hash,
                    'downloaded_url': download.downloaded_url, 'parent_url': parent_url, 'raw_path': raw_path,
                    'media_type': download.media_type, 'collected_at': download.collected_at,
                    'last_collected_at': download.collected_at})
            else:
                self.db.execute('UPDATE document_versions SET last_collected_at=? WHERE version_id=?',
                                (max(existing['last_collected_at'], download.collected_at), version_id))
        return dict(self.db.execute('SELECT * FROM document_versions WHERE version_id=?', (version_id,)).fetchone())

    def version(self, version_id):
        return dict(self.db.execute('SELECT * FROM document_versions WHERE version_id=?', (version_id,)).fetchone())

    def html_history(self, source_id, url):
        # Newest successful observation first, including reversions to older evidence.
        observed = self.db.execute('''SELECT o.raw_path,o.content_sha256,e.version_id
            FROM html_observations o JOIN extractions e USING(extraction_id)
            JOIN document_versions v USING(version_id) JOIN documents d USING(document_id)
            WHERE d.source_id=? AND d.source_url=? ORDER BY o.observation_id DESC''', (source_id, url)).fetchall()
        legacy = self.db.execute('''SELECT v.raw_path,v.content_sha256,v.version_id
            FROM document_versions v JOIN documents d USING(document_id)
            WHERE d.source_id=? AND d.source_url=? AND v.media_type='text/html'
            AND EXISTS (SELECT 1 FROM extractions e WHERE e.version_id=v.version_id)
            ORDER BY v.last_collected_at DESC,v.version_id''', (source_id, url)).fetchall()
        return [dict(r) for r in [*observed, *legacy]]

    def save_result(self, extraction, chunks, assets, observation=None):
        if not chunks:
            raise PipelineError('Successful extraction must contain evidence')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            existing = self.db.execute('SELECT * FROM extractions WHERE extraction_id=?', (extraction['extraction_id'],)).fetchone()
            if existing is not None:
                # Same pipeline must reproduce the same result, apart from execution time.
                if any(existing[key] != value for key, value in extraction.items() if key != 'processed_at'):
                    raise PipelineError('Same pipeline produced different content; create a new pipeline version')
                saved_chunks = [dict(r) for r in self.db.execute('SELECT * FROM chunks WHERE extraction_id=? ORDER BY ordinal', (extraction['extraction_id'],))]
                saved_assets = [dict(r) for r in self.db.execute('SELECT * FROM extraction_asset_classes WHERE extraction_id=? ORDER BY asset_class', (extraction['extraction_id'],))]
                if saved_chunks != chunks or saved_assets != sorted(assets, key=lambda a: a['asset_class']):
                    raise PipelineError('Existing extraction has different or incomplete evidence')
            else:
                self._insert('extractions', extraction)
                for chunk in chunks:
                    self._insert('chunks', chunk)
                for asset in assets:
                    self._insert('extraction_asset_classes', asset)
            if observation is not None:
                if observation['extraction_id'] != extraction['extraction_id']:
                    raise PipelineError('Observation points to a different extraction')
                self._insert('html_observations', observation)
        return existing is None

    def counts(self):
        return {table: self.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}
