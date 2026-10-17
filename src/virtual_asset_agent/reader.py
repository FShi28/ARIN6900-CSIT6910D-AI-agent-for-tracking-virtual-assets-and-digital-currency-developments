"""Read-only SQLite queries and fixed evidence references; no network or model calls."""

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from .common import PipelineError, local_path

# Observation order handles HTML reversions without rewriting immutable evidence.
CURRENT = '''WITH events AS (
    SELECT document_id,version_id,last_collected_at AS observed_at,0 AS kind,rowid AS seq
    FROM document_versions
    UNION ALL
    SELECT v.document_id,e.version_id,o.collected_at,1,o.observation_id
    FROM html_observations o JOIN extractions e USING(extraction_id)
    JOIN document_versions v USING(version_id)
), ranked AS (
    SELECT *,ROW_NUMBER() OVER(PARTITION BY document_id
        ORDER BY observed_at DESC,kind DESC,seq DESC) AS position FROM events
), current_versions AS (
    SELECT * FROM ranked WHERE position=1
)
'''

FIELDS = '''d.document_id,d.source_url,s.source_id,s.source_name,s.jurisdiction,s.regulator,
    v.version_id,v.media_type,v.downloaded_url,v.parent_url,v.raw_path,v.content_sha256,
    v.collected_at AS evidence_collected_at,v.last_collected_at AS evidence_last_collected_at,
    e.extraction_id,e.pipeline_version,e.processed_at,e.title,e.language,e.published_at,
    e.updated_at,e.effective_at,e.document_type,e.lifecycle_stage,e.metadata_evidence,
    (SELECT COUNT(*) FROM chunks c WHERE c.extraction_id=e.extraction_id) AS chunk_count'''

CURRENT_FROM = '''FROM documents d JOIN sources s USING(source_id)
    JOIN current_versions cv USING(document_id)
    JOIN document_versions v ON v.version_id=cv.version_id
    LEFT JOIN extractions e ON e.extraction_id=(SELECT e2.extraction_id FROM extractions e2
        WHERE e2.version_id=v.version_id ORDER BY e2.processed_at DESC,e2.rowid DESC LIMIT 1)'''


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise PipelineError('Expected a 64-character lowercase hexadecimal identifier')
    return value


def page_bounds(limit, offset):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise PipelineError('limit must be 1..100 and offset must be a non-negative integer')


def filters(source=None, published_from=None, published_to=None):
    clauses, values = [], []
    if source is not None:
        if not isinstance(source, str) or not source.strip():
            raise PipelineError('source must be non-empty')
        clauses.append('s.source_id=?'); values.append(source)
    for value in (published_from, published_to):
        if value is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise PipelineError('Dates must be YYYY-MM-DD')
            date.fromisoformat(value)
    if published_from and published_to and published_from > published_to:
        raise PipelineError('published_from must not exceed published_to')
    if published_from:
        clauses.append('e.published_at>=?'); values.append(published_from)
    if published_to:
        clauses.append('e.published_at<=?'); values.append(published_to)
    return clauses, values


class Reader:
    def __init__(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            raise PipelineError('Database does not exist; read queries never create it')
        self.db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        if self.db.execute('PRAGMA user_version').fetchone()[0] != 2:
            self.close()
            raise PipelineError('Reader requires schema v2; it never migrates databases')
        self.db.execute('BEGIN')  # One consistent read snapshot for this Reader lifetime.

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _record(self, row):
        if row is None:
            raise PipelineError('Record not found')
        result = dict(row)
        result['state'] = 'ready' if result['extraction_id'] else 'unprocessed'
        result['metadata_evidence'] = json.loads(result['metadata_evidence']) if result['metadata_evidence'] else None
        result['asset_classes'] = [r[0] for r in self.db.execute(
            'SELECT asset_class FROM extraction_asset_classes WHERE extraction_id=? ORDER BY asset_class',
            (result['extraction_id'],))]
        return result

    def list_documents(self, limit=20, offset=0, source=None, published_from=None, published_to=None):
        page_bounds(limit, offset)
        clauses, values = filters(source, published_from, published_to)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        rows = self.db.execute(CURRENT + 'SELECT ' + FIELDS + ',cv.observed_at AS last_observed_at ' +
            CURRENT_FROM + where + ' ORDER BY e.published_at DESC,d.document_id LIMIT ? OFFSET ?',
            [*values, limit, offset]).fetchall()
        return [self._record(r) for r in rows]

    def get_document(self, document_id):
        row = self.db.execute(CURRENT + 'SELECT ' + FIELDS + ',cv.observed_at AS last_observed_at ' +
            CURRENT_FROM + ' WHERE d.document_id=?', (identifier(document_id),)).fetchone()
        return self._record(row)

    def get_extraction(self, extraction_id, include_text=False):
        extra = ',e.raw_text,e.clean_text' if include_text else ''
        row = self.db.execute('SELECT ' + FIELDS + extra + ''' FROM extractions e
            JOIN document_versions v USING(version_id) JOIN documents d USING(document_id)
            JOIN sources s USING(source_id) WHERE e.extraction_id=?''', (identifier(extraction_id),)).fetchone()
        return self._record(row)

    def _chunk(self, row):
        chunk = dict(row)
        metadata = self.get_extraction(chunk['extraction_id'])
        evidence = metadata['metadata_evidence']
        chunk['citation'] = {key: metadata[key] for key in ('document_id','version_id','extraction_id',
            'source_id','source_name','source_url','title','published_at','downloaded_url','raw_path','content_sha256')}
        chunk['citation'].update({'reference': 'chunk:' + chunk['chunk_id'], 'chunk_id': chunk['chunk_id'],
            'page_start': chunk['page_start'], 'page_end': chunk['page_end'],
            'char_start': chunk['char_start'], 'char_end': chunk['char_end'],
            'offset_basis': 'clean_text_unicode_codepoints_half_open',
            'html_body_locator': evidence.get('body', {}).get('locator') if metadata['media_type']=='text/html' else None})
        return chunk

    def get_chunk(self, chunk_id):
        row = self.db.execute('SELECT * FROM chunks WHERE chunk_id=?', (identifier(chunk_id),)).fetchone()
        if row is None:
            raise PipelineError('Chunk not found')
        return self._chunk(row)

    def list_chunks(self, extraction_id, limit=20, offset=0):
        page_bounds(limit, offset)
        self.get_extraction(extraction_id)
        return [self._chunk(r) for r in self.db.execute(
            'SELECT * FROM chunks WHERE extraction_id=? ORDER BY ordinal LIMIT ? OFFSET ?',
            (extraction_id, limit, offset)).fetchall()]

    def search(self, query, limit=10, offset=0, source=None, published_from=None, published_to=None):
        page_bounds(limit, offset)
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200 or '\x00' in query:
            raise PipelineError('Query must contain 1..200 non-empty characters without NUL')
        clauses, values = filters(source, published_from, published_to)
        # Literal phrase search; %, _, and SQL punctuation are ordinary characters.
        clauses.append('instr(lower(c.text),lower(?))>0'); values.append(query.strip())
        rows = self.db.execute(CURRENT + 'SELECT c.* ' + CURRENT_FROM +
            ' JOIN chunks c ON c.extraction_id=e.extraction_id WHERE ' + ' AND '.join(clauses) +
            ' ORDER BY e.published_at DESC,d.document_id,c.ordinal LIMIT ? OFFSET ?',
            [*values, limit, offset]).fetchall()
        return [self._chunk(r) for r in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only regulatory document and evidence queries')
    parser.add_argument('command', choices=('documents','document','extraction','chunks','chunk','search'))
    parser.add_argument('--db', default='data/ingestion/hkma.sqlite')
    parser.add_argument('--source')
    parser.add_argument('--published-from')
    parser.add_argument('--published-to')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--document-id')
    parser.add_argument('--extraction-id')
    parser.add_argument('--chunk-id')
    parser.add_argument('--query')
    parser.add_argument('--include-text', action='store_true')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        required = {'document':'document_id','extraction':'extraction_id','chunks':'extraction_id',
                    'chunk':'chunk_id','search':'query'}
        for option in ('document_id','extraction_id','chunk_id','query'):
            value = getattr(args, option)
            if option == required.get(args.command):
                if value is None:raise PipelineError(f'{args.command} requires --{option.replace("_","-")}')
            elif value is not None:raise PipelineError(f'Unexpected --{option.replace("_","-")} for {args.command}')
        if args.include_text and args.command != 'extraction':
            raise PipelineError('--include-text requires extraction')
        selected_filters = dict(source=args.source, published_from=args.published_from, published_to=args.published_to)
        if args.command not in ('documents','search') and any(v is not None for v in selected_filters.values()):
            raise PipelineError('Source/date filters only apply to documents and search')
        path = local_path(root, args.db)
        if not path.is_relative_to(local_path(root, 'data/ingestion')) or path.suffix != '.sqlite':
            raise PipelineError('Database must be a .sqlite file under data/ingestion/')
        with Reader(path) as reader:
            if args.command == 'documents':result=reader.list_documents(args.limit,args.offset,**selected_filters)
            elif args.command == 'document':result=reader.get_document(args.document_id)
            elif args.command == 'extraction':result=reader.get_extraction(args.extraction_id,args.include_text)
            elif args.command == 'chunks':result=reader.list_chunks(args.extraction_id,args.limit,args.offset)
            elif args.command == 'chunk':result=reader.get_chunk(args.chunk_id)
            else:result=reader.search(args.query,args.limit,args.offset,**selected_filters)
        print(json.dumps({'mode':'read_only','result':result},ensure_ascii=True,indent=2))
        return 0
    except (PipelineError,sqlite3.Error,OSError,ValueError) as exc:
        print(json.dumps({'status':'failed','error_type':type(exc).__name__,'message':str(exc)}),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
