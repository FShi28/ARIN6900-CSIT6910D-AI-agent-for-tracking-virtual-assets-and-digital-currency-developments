"""Bounded discovery, failure isolation and persistent progress for Hong Kong CBDC."""
import json
from urllib.parse import urlsplit

from collection_service import file_lock, save_json
from research_publications import publication_fetcher, save_publication, sources, collect_research
from virtual_asset_agent.collectors.hk_cbdc import listing, html_metadata
from virtual_asset_agent.common import sha256, utc_now, write_immutable
from virtual_asset_agent.fetching import SourceAccessError
from hk_cbdc_data import selected_sources, export_corpus


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def discover(root, blocked_hosts=(), limit=12):
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('CBDC discovery batch must be 1..50')
    folder = root / 'data/ingestion/hk_cbdc'
    results, fetchers = [], {}
    blocked = set(blocked_hosts)
    channels = read(root / 'config/hk_cbdc_discovery.json', [])
    with file_lock(root / 'data/ingestion/research.lock'):
        catalog = read(folder / 'discovered_sources.json', [])
        queue = read(folder / 'candidates.json', {})
        known = {s['url'] for s in sources(root)}
        for url in queue.keys() & known:
            queue[url]['status'] = 'known'
        def fetch(url, publisher):
            host = urlsplit(url).hostname
            if host in blocked:
                raise SourceAccessError('Host stopped after access denial or throttling')
            if host not in fetchers:
                fetchers[host] = publication_fetcher(root, dict(url=url, publisher=publisher, trust_env=False))
            return fetchers[host].get(url, 'text/html')
        try:
            for channel in channels:
                try:
                    d = fetch(channel['url'], channel['publisher'])
                    raw = 'data/raw/' + sha256(d.content) + '.html'
                    write_immutable(root / raw, d.content)
                    candidates = listing(d.content, channel)
                    for c in candidates:
                        if c['url'] in known:
                            queue[c['url']] = dict(c, status='known', checked_at=d.collected_at)
                        elif c['url'] not in queue:
                            queue[c['url']] = dict(c, status='needs_pdf_review' if c['format'] == 'pdf' else 'pending',
                                                  listing_raw_path=raw, discovered_at=d.collected_at)
                    results.append(dict(source_url=channel['url'], status='reused', candidates=len(candidates)))
                    save_json(folder / 'candidates.json', queue)
                except Exception as exc:
                    if isinstance(exc, SourceAccessError):
                        blocked.add(urlsplit(channel['url']).hostname)
                    results.append(dict(source_url=channel['url'], status='failed', error_type=type(exc).__name__, message=str(exc)))
            pending = [c for c in queue.values() if c['status'] in ('pending', 'failed') and c['format'] == 'html']
            # Newest listing is scanned every run. Persistent queue prevents overflow from being lost.
            for c in pending[:limit]:
                url = c['url']
                try:
                    d = fetch(url, c['publisher'])
                    raw = 'data/raw/' + sha256(d.content) + '.html'
                    write_immutable(root / raw, d.content)
                    c['article_raw_path'] = raw
                    try:
                        metadata = html_metadata(d.content, c['publisher'])
                    except ValueError as exc:
                        c.update(status='needs_review', message=str(exc))
                        continue
                    source = dict(metadata, publisher=c['publisher'], url=url, topic='CBDC', authority='primary',
                        collection='hk_cbdc', trust_env=False, kind='Press release' if c['publisher'] == 'HKMA' and '/press-releases/' in url
                        or '/media-releases/' in url else 'Research / project update',
                        discovery_url=c['discovered_from'], automatic_discovery=True)
                    state = save_publication(root, source, d)
                    catalog.append(source)
                    save_json(folder / 'discovered_sources.json', catalog)
                    known.add(url)
                    c.update(status='collected', collected_at=d.collected_at)
                    results.append(dict(source_url=url, status=state))
                except Exception as exc:
                    if isinstance(exc, SourceAccessError):
                        blocked.add(urlsplit(url).hostname)
                    c.update(status='failed', message=str(exc))
                    results.append(dict(source_url=url, status='failed', error_type=type(exc).__name__, message=str(exc)))
                finally:
                    save_json(folder / 'candidates.json', queue)
        finally:
            for f in fetchers.values():
                f.close()
        save_json(folder / 'discovery_last_run.json', dict(checked_at=utc_now(), results=results,
            remaining=sum(c['status'] in ('pending', 'failed') for c in queue.values()),
            needs_review=sum(c['status'] in ('needs_review', 'needs_pdf_review') for c in queue.values())))
    return results


def cycle(root, refresh=True, blocked_hosts=(), limit=12):
    """Caller owns global run.lock. Each successful document persists immediately."""
    folder = root / 'data/ingestion/hk_cbdc'
    state = dict(status='running', started_at=utc_now(), phase='refresh' if refresh else 'discovery', results=[])
    save_json(folder / 'run_checkpoint.json', state)
    try:
        if refresh:
            state['results'].extend(collect_research(root, selected_sources(root)))
        blocked = set(blocked_hosts) | {urlsplit(r['source_url']).hostname for r in state['results']
                                       if r.get('error_type') == 'SourceAccessError'}
        state['phase'] = 'discovery'
        save_json(folder / 'run_checkpoint.json', state)
        state['results'].extend(discover(root, blocked, limit))
        state['phase'] = 'export'
        save_json(folder / 'run_checkpoint.json', state)
        state['corpus'] = export_corpus(root)
        state.update(status='partial_failure' if any(r['status'] == 'failed' for r in state['results']) else 'success', phase='complete')
    except Exception as exc:
        state.update(status='failed', error_type=type(exc).__name__, message=str(exc))
        raise
    finally:
        state['finished_at'] = utc_now()
        save_json(folder / 'run_checkpoint.json', state)
    return state
