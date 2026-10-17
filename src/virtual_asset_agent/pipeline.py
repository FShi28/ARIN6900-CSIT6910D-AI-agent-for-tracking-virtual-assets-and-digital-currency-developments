"""Single-document orchestration; no model calls, scheduler or UI coupling."""

import importlib.metadata
import json
import logging
import platform
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .cleaning import chunk_pages, clean_pages
from .collectors.hkma import discover, discover_candidates, is_press_url
from .common import PipelineError, canonical_url, identity, json_bytes, local_path, sha256, utc_now, write_immutable
from .fetching import Fetcher
from .normalization import classify, normalize
from .parsing import parse_pdf
from .html_parsing import ParsedHTML, parse_html
from .incremental import inspect_html
from .storage import Repository
from .validation import validate_result


class RunLog:
    def __init__(self, root, source_id):
        self.path = local_path(root, 'logs/ingestion.jsonl')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = uuid.uuid4().hex
        self.source_id = source_id

    def __call__(self, stage, status, url=None, **details):
        record = {'run_id': self.run_id, 'source_id': self.source_id, 'url': url,
                  'stage': stage, 'status': status, 'error_type': None, 'message': '',
                  'occurred_at': utc_now(), **details}
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')


def processing_manifest(root, source):
    package = Path(__file__).parent
    code = {path.relative_to(package).as_posix(): sha256(path.read_bytes()) for path in sorted(package.rglob('*.py'))}
    manifest = {'format_version': 1, 'code_sha256': code, 'python': platform.python_version(),
                'dependencies': {name: importlib.metadata.version(name) for name in ('requests', 'beautifulsoup4', 'PyYAML', 'pypdf')},
                'processing': source['processing'], 'published_from': source['scope']['published_from'],
                'source_id': source['source_id'], 'schema_sha256': sha256((Path(root) / 'db/schema.sql').read_bytes())}
    payload = json_bytes(manifest)
    pipeline_version = sha256(payload)
    write_immutable(local_path(root, f'data/processed/{pipeline_version}/manifest.json'), payload)
    return pipeline_version


def ingest(root, db_path, sources, source_id='hkma', fetcher_factory=Fetcher, document_url=None,
           discovered=False, discovery_snapshot=None):
    root = Path(root)
    log = RunLog(root, source_id)
    stage, current_url = 'configuration', None
    fetcher = repository = None
    try:
        source = sources.get(source_id)
        if source is None or not source['enabled']:
            raise PipelineError('Requested source is missing or disabled')
        targets = [canonical_url(url) for url in source['scope']['target_urls']]
        selected = canonical_url(document_url) if document_url is not None else targets[0]
        if discovered:
            if not source.get('discovery', {}).get('enabled') or not is_press_url(selected, source):
                raise PipelineError('Requested URL is outside the automatic discovery scope')
        elif selected not in targets:
            raise PipelineError('Requested document is not in the approved target list')
        repository = Repository(db_path)
        repository.sync_sources(sources)
        fetcher = fetcher_factory(source, log)
        stage, current_url = 'discovery', source['discovery_url']
        listing = discovery_snapshot if discovery_snapshot is not None else fetcher.get(current_url, 'text/html')
        listing_hash = sha256(listing.content)
        listing_path = f'data/raw/{listing_hash}.html'
        write_immutable(local_path(root, listing_path), listing.content)
        if discovered:
            candidates, _ = discover_candidates(listing.content, listing.downloaded_url, source, listing.collected_at)
            candidates = [c for c in candidates if c['source_url'] == selected]
            if not candidates:
                raise PipelineError('Selected URL was not found within the live discovery scope')
        else:
            candidates = discover(listing.content, listing.downloaded_url, source, target_url=selected)
        log(stage, 'success', current_url, downloaded_url=listing.downloaded_url,
            raw_path=listing_path, content_sha256=listing_hash, count=len(candidates))
        # Each run handles one selected approved target, keeping failures isolated.
        candidate = candidates[0]
        stage, current_url = 'download', candidate['source_url']
        expected_type = 'application/pdf' if urlsplit(current_url).path.lower().endswith('.pdf') else 'text/html'
        download = fetcher.get(current_url, expected_type)
        content_hash = sha256(download.content)
        extension = 'pdf' if download.media_type == 'application/pdf' else 'html'
        raw_path = f'data/raw/{content_hash}.{extension}'
        write_immutable(local_path(root, raw_path), download.content)
        version, comparison = None, None
        if download.media_type == 'text/html':
            stage = 'incremental'
            version, comparison = inspect_html(root, repository, source_id, current_url, download)
        stage = 'raw_storage'
        if version is None or version['content_sha256'] == content_hash:
            version = repository.register_raw(source_id, current_url, download, content_hash, raw_path, candidate['parent_url'])
        log(stage, 'success', current_url, version_id=version['version_id'], raw_path=raw_path,
            downloaded_url=download.downloaded_url, content_sha256=content_hash, collected_at=download.collected_at,
            evidence_raw_path=version['raw_path'], evidence_content_sha256=version['content_sha256'])
        stage = 'parsing'
        parsed = parse_pdf(download.content) if download.media_type == 'application/pdf' else parse_html(download.content)
        stage = 'cleaning'
        clean_text, page_ranges = clean_pages(parsed.pages)
        if isinstance(parsed, ParsedHTML):
            page_ranges[0]['page'] = None
        stage = 'normalization'
        pipeline_version = processing_manifest(root, source)
        extraction_id = identity('extraction', version['version_id'], pipeline_version)
        extraction = {'extraction_id': extraction_id, 'version_id': version['version_id'],
                      'pipeline_version': pipeline_version, 'processed_at': utc_now(),
                      'raw_text': '\n\n'.join(parsed.pages), 'clean_text': clean_text, **normalize(parsed)}
        chunks = chunk_pages(clean_text, page_ranges, extraction_id, source['processing']['chunk_max_chars'])
        assets = classify(chunks)
        stage = 'validation'
        if discovered and (extraction['published_at'] is None or extraction['published_at'] != candidate['listing_date']):
            raise PipelineError('Article publication date missing or inconsistent with listing date')
        validate_result(root, source, version, extraction, chunks, assets, parsed, page_ranges)
        log(stage, 'warning', current_url, message='Table structure has not been verified; is_table remains null.',
            unknown_dates=[key for key in ('published_at', 'updated_at', 'effective_at') if extraction[key] is None])
        stage = 'persistence'
        observation = None
        if comparison is not None:
            observation = {'run_id': log.run_id, 'extraction_id': extraction_id,
                           'collected_at': download.collected_at, 'downloaded_url': download.downloaded_url,
                           'parent_url': candidate['parent_url'], 'raw_path': raw_path,
                           'content_sha256': content_hash, **comparison}
        created = repository.save_result(extraction, chunks, assets, observation)
        summary = {'run_id': log.run_id, 'status': 'created' if created else 'reused',
                   'document_id': version['document_id'], 'version_id': version['version_id'],
                   'extraction_id': extraction_id, 'source_url': current_url,
                   'downloaded_url': download.downloaded_url, 'raw_path': raw_path,
                   'content_sha256': content_hash, 'title': extraction['title'],
                   'evidence_raw_path': version['raw_path'], 'evidence_content_sha256': version['content_sha256'],
                   'change_type': comparison['change_type'] if comparison else None,
                   'response_differs_from_evidence': content_hash != version['content_sha256'],
                   'media_type': download.media_type, 'published_at': extraction['published_at'],
                   'pages': None if isinstance(parsed, ParsedHTML) else len(parsed.pages),
                   'chunks': len(chunks), 'counts': repository.counts()}
        if discovered:
            summary['discovery_evidence'] = {'raw_path': listing_path, 'content_sha256': listing_hash,
                                             'collected_at': listing.collected_at, 'candidate': candidate}
        log(stage, 'success', current_url, result=summary)
        return summary
    except (PipelineError, requests.RequestException, sqlite3.Error, OSError, ValueError) as exc:
        log(stage, 'failure', current_url, error_type=type(exc).__name__, message=str(exc))
        raise
    except Exception as exc:
        # Boundary-only logging for unexpected defects; preserve traceback and failure.
        log(stage, 'failure', current_url, error_type=type(exc).__name__, message=str(exc))
        logging.getLogger(__name__).exception('Unexpected ingestion failure')
        raise
    finally:
        if fetcher is not None:
            fetcher.close()
        if repository is not None:
            repository.close()
