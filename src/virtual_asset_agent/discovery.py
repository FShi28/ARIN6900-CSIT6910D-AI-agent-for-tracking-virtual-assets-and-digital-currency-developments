"""Bounded topic discovery and serial ingestion, with auditable listing snapshots."""

import sqlite3

import requests

from .collectors.hkma import discover_candidates
from .common import PipelineError, json_bytes, local_path, sha256, write_immutable
from .fetching import Download, Fetcher, SourceAccessError
from .pipeline import RunLog, ingest
from .storage import Repository


def enabled_source(sources, source_id):
    source = sources.get(source_id)
    if source is None or not source['enabled'] or not source.get('discovery', {}).get('enabled'):
        raise PipelineError('Requested source or automatic discovery is disabled')
    return source


def scan(root, db_path, sources, source_id='hkma', fetcher_factory=Fetcher, shared_fetcher=None):
    source = enabled_source(sources, source_id)
    log = RunLog(root, source_id)
    fetcher = shared_fetcher or fetcher_factory(source, log)
    repository = None
    try:
        repository = Repository(db_path)
        listing = fetcher.get(source['discovery_url'], 'text/html')
        digest = sha256(listing.content)
        raw_path = f'data/raw/{digest}.html'
        write_immutable(local_path(root, raw_path), listing.content)
        candidates, skipped = discover_candidates(listing.content, listing.downloaded_url, source, listing.collected_at)
        for candidate in candidates:
            row = repository.db.execute('''SELECT d.document_id,
                EXISTS(SELECT 1 FROM document_versions v JOIN extractions e USING(version_id)
                       WHERE v.document_id=d.document_id) AS has_result
                FROM documents d WHERE d.source_id=? AND d.source_url=?''',
                (source_id, candidate['source_url'])).fetchone()
            candidate['state'] = 'new' if row is None else ('known' if row['has_result'] else 'retry')
        manifest_path = f'data/discovery/{log.run_id}.json'
        result = {'run_id': log.run_id, 'source_id': source_id, 'manifest_path': manifest_path,
                  'rule': source['discovery']['rule'], 'listing': {'source_url': source['discovery_url'],
                  'downloaded_url': listing.downloaded_url, 'raw_path': raw_path,
                  'content_sha256': digest, 'collected_at': listing.collected_at},
                  'candidates': candidates, 'skipped': skipped,
                  'selection_config': {'published_from': source['scope']['published_from'], **source['discovery']},
                  'counts': {state: sum(c['state'] == state for c in candidates) for state in ('new', 'known', 'retry')}}
        write_immutable(local_path(root, manifest_path), json_bytes(result))
        log('discovery', 'success', source['discovery_url'], manifest_path=manifest_path, counts=result['counts'])
        return result
    except (PipelineError, requests.RequestException, sqlite3.Error, OSError, ValueError) as exc:
        log('discovery', 'failure', source['discovery_url'], error_type=type(exc).__name__, message=str(exc))
        raise
    finally:
        if shared_fetcher is None:
            fetcher.close()
        if repository is not None:
            repository.close()


def ingest_discovered(root, db_path, sources, source_id='hkma', limit=3, new_only=False, fetcher_factory=Fetcher):
    source = enabled_source(sources, source_id)
    if type(limit) is not int or not 1 <= limit <= source['discovery']['max_batch']:
        raise PipelineError('Batch limit exceeds configured bound')
    log = RunLog(root, source_id)
    shared = fetcher_factory(source, log)
    class BorrowedFetcher:
        def __init__(self, source, logger):
            pass
        def get(self, url, expected_type):
            return shared.get(url, expected_type)
        def close(self):
            pass
    try:
        manifest = scan(root, db_path, sources, source_id, shared_fetcher=shared)
        candidates = [c for c in manifest['candidates'] if not new_only or c['state'] != 'known']
        selected = candidates[:limit]
        snapshot = manifest['listing']
        listing = Download(local_path(root, snapshot['raw_path']).read_bytes(), snapshot['downloaded_url'],
                           'text/html', snapshot['collected_at'])
        results, stopped = [], False
        for candidate in selected:
            url = candidate['source_url']
            try:
                results.append(ingest(root, db_path, sources, source_id, fetcher_factory=BorrowedFetcher,
                                      document_url=url, discovered=True, discovery_snapshot=listing))
            except (PipelineError, requests.RequestException, sqlite3.Error, OSError, ValueError) as exc:
                results.append({'source_url': url, 'status': 'failed', 'error_type': type(exc).__name__, 'message': str(exc)})
                if isinstance(exc, SourceAccessError):
                    stopped = True
                    break
        report = {'run_id': log.run_id, 'status': 'partial_failure' if any(r['status'] == 'failed' for r in results) else 'success',
                  'discovery_manifest': manifest['manifest_path'], 'limit': limit, 'new_only': new_only,
                  'selected': len(selected), 'attempted': len(results), 'remaining': len(candidates)-len(results),
                  'stopped_for_source_access': stopped, 'results': results}
        report['report_path'] = f'data/discovery/{log.run_id}-batch.json'
        write_immutable(local_path(root, report['report_path']), json_bytes(report))
        log('batch', report['status'], source['discovery_url'], report_path=report['report_path'])
        return report
    finally:
        shared.close()
