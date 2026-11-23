"""Bounded, persistent discovery of HK stablecoin publications on reviewed sites."""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from collection_service import file_lock, save_json
from research_publications import sources, publication_fetcher, save_publication, snapshot_path
from virtual_asset_agent.common import sha256, utc_now, write_immutable
from virtual_asset_agent.fetching import SourceAccessError
from virtual_asset_agent.reader import Reader
from virtual_asset_agent.collectors.hk_channels import (
    listing, html_metadata, pdf_metadata, charltons_pdf, OutsideScope)
from virtual_asset_agent.collectors.hk_official import official_listing, official_metadata
from virtual_asset_agent.collectors.hk_official import brdr_listing, brdr_pdf


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def known_urls(root):
    result = {s['url'] for s in sources(root)}
    db = root / 'data/ingestion/hkma.sqlite'
    if db.exists():
        with Reader(db) as reader:
            offset = 0
            while True:
                rows = reader.list_documents(limit=100, offset=offset)
                result.update(d['source_url'] for d in rows if d['state'] == 'ready')
                if len(rows) < 100:
                    break
                offset += len(rows)
    result.update(re.sub(r'p\.htm$', '.htm', url) for url in list(result)
                  if urlsplit(url).hostname == 'www.info.gov.hk')
    return result


def preserve(root, download, extension):
    path = 'data/raw/' + sha256(download.content) + '.' + extension
    write_immutable(root / path, download.content)
    return path


def discover_hk(root, blocked_hosts=(), channel_ids=None):
    config = root / 'config/hk_discovery.json'
    if not config.exists():
        return []
    folder = root / 'data/ingestion/hk_stablecoins'
    results = []
    with file_lock(root / 'data/ingestion/research.lock'):
        queue = read_json(folder / 'discovery_queue.json', {})
        dynamic = read_json(folder / 'discovered_sources.json', [])
        known = known_urls(root)
        report = dict(started_at=utc_now(), channels=[])
        for channel in read_json(config, []):
            if not channel.get('enabled', True) or (channel_ids is not None and channel['id'] not in channel_ids):
                continue
            stats = dict(publisher=channel['publisher'], pages=0, discovered=0, added=0,
                         known=0, needs_review=0, excluded=0, status='success', listing_snapshots=[])
            fetcher = publication_fetcher(root, channel)
            try:
                if urlsplit(channel['url']).hostname in blocked_hosts:
                    raise SourceAccessError('Earlier collection stopped this host')
                page_url, visited = channel['url'], set()
                while page_url and len(visited) < channel['max_pages']:
                    if page_url in visited:
                        raise ValueError('Pagination cycle')
                    visited.add(page_url)
                    if channel['id'] == 'hkma_brdr':
                        query = dict(langCode='EN', pageNumber=stats['pages'] + 1, pageSize=20,
                                     sortBy='ISSUE_DATE_DESCENDING',
                                     docSrchCriteriaDtoList=[dict(fieldCode='searchWordAll', valueList=['stablecoin'])])
                        downloaded = fetcher.post_json(channel['url'], query)
                        raw = preserve(root, downloaded, 'json')
                        candidates, total = brdr_listing(downloaded.content, channel['url'])
                        next_url = (channel['url'] + '#page=' + str(stats['pages'] + 2)
                                    if (stats['pages'] + 1) * 20 < total else None)
                        stats.setdefault('search_requests', []).append(dict(payload=query, raw_path=raw))
                    elif channel['id'] == 'sfc':
                        query = dict(lang='EN', year=datetime.now().year, cntCatKeySeq='all',
                                     pageNo=stats['pages'], pageSize=20)
                        downloaded = fetcher.post_json(channel['url'], query)
                        raw = preserve(root, downloaded, 'json')
                        candidates, total = official_listing(downloaded.content, channel, channel['url'])
                        next_url = (channel['url'] + '#page=' + str(stats['pages'] + 1)
                                    if (stats['pages'] + 1) * 20 < total else None)
                        stats.setdefault('search_requests', []).append(dict(payload=query, raw_path=raw))
                    elif channel['id'] == 'hksar':
                        downloaded = fetcher.get(page_url, 'application/xml')
                        raw = preserve(root, downloaded, 'xml')
                        candidates, next_url = official_listing(downloaded.content, channel, page_url)
                    else:
                        downloaded = fetcher.get(page_url, 'text/html')
                        raw = preserve(root, downloaded, 'html')
                        candidates, next_url = listing(downloaded.content, channel, page_url)
                    stats['pages'] += 1
                    stats['listing_snapshots'].append(raw)
                    for candidate in candidates:
                        url = candidate['url']
                        previous = queue.get(url, {})
                        queue[url] = dict(previous, **candidate, publisher=channel['publisher'],
                            channel_id=channel['id'], listing_raw_path=raw,
                            first_seen_at=previous.get('first_seen_at', downloaded.collected_at),
                            last_seen_at=downloaded.collected_at)
                        stats['discovered'] += 1
                    page_url = next_url
                stats['next_page_not_scanned'] = page_url
                pending = []
                for url, item in queue.items():
                    if item['channel_id'] != channel['id']:
                        continue
                    if url in known or item.get('resolved_url') in known:
                        item['status'] = 'known'
                        stats['known'] += 1
                    else:
                        pending.append(item)
                pending.sort(key=lambda c: (c.get('last_attempt_at', ''), c['first_seen_at'], c['url']))
                stats['pending_beyond_batch'] = max(0, len(pending) - channel['batch_size'])
                for item in pending[:channel['batch_size']]:
                    item['last_attempt_at'] = utc_now()
                    try:
                        url = item['url']
                        pdf = urlsplit(url).path.lower().endswith('.pdf')
                        downloaded = fetcher.get(url, 'application/pdf' if pdf else 'text/html')
                        parent_raw = preserve(root, downloaded, 'pdf' if pdf else 'html')
                        candidate = dict(item)
                        if channel['id'] == 'hkma_brdr':
                            url = brdr_pdf(downloaded.content, url)
                            item['resolved_url'] = url
                            if url in known:
                                item['status'] = 'known'
                                stats['known'] += 1
                                continue
                            downloaded = fetcher.get(url, 'application/pdf')
                            preserve(root, downloaded, 'pdf')
                            pdf = True
                        if channel['id'] == 'charltons' and not pdf:
                            candidate['title'], url = charltons_pdf(downloaded.content, url)
                            item['resolved_url'] = url
                            if url in known:
                                item['status'] = 'known'
                                stats['known'] += 1
                                continue
                            downloaded = fetcher.get(url, 'application/pdf')
                            preserve(root, downloaded, 'pdf')
                            # Only merge a query-string variant after byte equality,
                            # never assume that a version parameter is irrelevant.
                            plain_url = urlsplit(url)._replace(query='').geturl()
                            prior = read_json(snapshot_path(root, plain_url), {})
                            if plain_url in known and prior.get('content_sha256') == sha256(downloaded.content):
                                item.update(status='known', resolved_url=plain_url)
                                stats['known'] += 1
                                continue
                            pdf = True
                        metadata = (official_metadata(downloaded.content, channel) if channel['id'] in ('sfc', 'hksar') else
                                    pdf_metadata(downloaded.content, candidate, channel) if pdf
                                    else html_metadata(downloaded.content, channel))
                        source = dict(metadata, url=url, publisher=channel['publisher'],
                            kind='Circular' if channel['id'] == 'sfc' else
                                 'Government announcement' if channel['id'] == 'hksar' else
                                 'Regulatory publication' if channel['id'] in ('hkma', 'hkma_brdr') else
                                 'Industry consultation response' if channel['id'] == 'asifma' else 'Legal commentary',
                            jurisdiction='Hong Kong', topic='Stablecoins', collection='hk_stablecoins',
                            authority='primary' if channel['id'] in ('hkma', 'hkma_brdr', 'sfc', 'hksar') else 'secondary',
                            legal_status='not_assessed', effective_at=None,
                            trust_env=channel.get('trust_env', True),
                            publication_page=item['url'], discovery_url=item['listing_url'],
                            listing_raw_path=item['listing_raw_path'], parent_raw_path=parent_raw,
                            repository_issue_date=item.get('repository_issue_date'),
                            repository_version_label=item.get('repository_version_label'),
                            coverage_scope=metadata.get('coverage_scope', 'mixed-jurisdiction context' if channel['id'] == 'linklaters' else 'Hong Kong-focused'),
                            scope_note='Automatically selected by deterministic HK stablecoin rules; not a current-law determination.')
                        status = save_publication(root, source, downloaded)
                        dynamic = [s for s in dynamic if s['url'] != url] + [source]
                        save_json(folder / 'discovered_sources.json', dynamic)
                        known.add(url)
                        item.update(status='collected', resolved_url=url)
                        item.pop('error', None)
                        stats['added'] += 1
                        results.append(dict(source_url=url, status=status))
                    except SourceAccessError:
                        raise
                    except OutsideScope as exc:
                        item.update(status='excluded', reason=str(exc))
                        item.pop('error', None)
                        stats['excluded'] += 1
                    except Exception as exc:
                        item.update(status='needs_review', error=str(exc))
                        stats['needs_review'] += 1
                        results.append(dict(source_url=item['url'], status='failed',
                                            error_type=type(exc).__name__, message=str(exc)))
                    finally:
                        save_json(folder / 'discovery_queue.json', queue)
            except Exception as exc:
                stats.update(status='failed', error=str(exc))
                results.append(dict(source_url=channel['url'], status='failed',
                                    error_type=type(exc).__name__, message=str(exc)))
            finally:
                fetcher.close()
                save_json(folder / 'discovery_queue.json', queue)
                report['channels'].append(stats)
                report['finished_at'] = utc_now()
                save_json(folder / 'discovery_report.json', report)
    return results


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    results = discover_hk(root)
    from hk_stablecoin_data import export_corpus
    summary = export_corpus(root)
    print(json.dumps(dict(results=results, documents=summary['documents'], chunks=summary['chunks']), indent=2))
    raise SystemExit(int(any(r['status'] == 'failed' for r in results)))
