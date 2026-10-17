"""CLI: python -m virtual_asset_agent init-db|ingest."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import requests
import yaml

from .common import PipelineError, local_path
from .config import load_sources
from .pipeline import ingest
from .discovery import scan, ingest_discovered
from .storage import init_database, migrate_database


def main(argv=None):
    parser = argparse.ArgumentParser(description='HKMA single-document regulatory ingestion')
    parser.add_argument('command', choices=('init-db', 'migrate-db', 'ingest', 'discover', 'ingest-discovered'))
    parser.add_argument('--source', default='hkma')
    parser.add_argument('--url', help='Select an approved document URL; defaults to the first configured target')
    parser.add_argument('--db', default='data/ingestion/hkma.sqlite', help='Path under data/ingestion/')
    parser.add_argument('--limit', type=int, help='Discovered batch size, default 3, maximum 10')
    parser.add_argument('--new-only', action='store_true', help='Skip known successful documents; does not check their updates')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        if args.url is not None and args.command != 'ingest':
            raise PipelineError('--url is only supported with ingest')
        if (args.limit is not None or args.new_only) and args.command != 'ingest-discovered':
            raise PipelineError('--limit and --new-only require ingest-discovered')
        db_path = local_path(root, args.db)
        if not db_path.is_relative_to(local_path(root, 'data/ingestion')) or db_path.suffix != '.sqlite':
            raise PipelineError('Database must be a .sqlite file under data/ingestion/')
        if args.command == 'init-db':
            init_database(db_path, root / 'db/schema.sql')
            result = {'status': 'initialized', 'database': str(db_path), 'schema_version': 2}
        elif args.command == 'migrate-db':
            changed = migrate_database(db_path, root / 'db/migrations/002_html_observations.sql')
            result = {'status': 'migrated' if changed else 'current', 'schema_version': 2}
        else:
            sources = load_sources(root / 'config/sources.yaml')
            if args.command == 'discover':
                result = scan(root, db_path, sources, args.source)
            elif args.command == 'ingest-discovered':
                result = ingest_discovered(root, db_path, sources, args.source,
                                           3 if args.limit is None else args.limit, args.new_only)
            else:
                result = ingest(root, db_path, sources, args.source, document_url=args.url)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1 if result.get('status') == 'partial_failure' else 0
    except (PipelineError, requests.RequestException, sqlite3.Error, OSError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'message': str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
