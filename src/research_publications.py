"""Collect citable PDFs and articles alongside explicitly labelled editorial notes."""
import io
import json
import logging
import re
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from pypdf import PdfReader
from pypdf.constants import UserAccessPermissions
from bs4 import BeautifulSoup

from collection_service import file_lock, save_json
from virtual_asset_agent.cleaning import clean_pages, chunk_pages
from virtual_asset_agent.common import identity, sha256, write_immutable
from virtual_asset_agent.fetching import Fetcher
from virtual_asset_agent.fetching import SourceAccessError
from virtual_asset_agent.html_parsing import body_text
from virtual_asset_agent.pipeline import RunLog


def sources(root):
    result = []
    for name in ('research_sources.json', 'hk_stablecoin_sources.json'):
        path = root / 'config' / name
        if path.exists():
            result.extend(json.loads(path.read_text(encoding='utf-8')))
    if len({source['url'] for source in result}) != len(result):
        raise ValueError('Duplicate publication URL in source catalogues')
    for collection in ('hk_stablecoins',):
        dynamic = root / f'data/ingestion/{collection}/discovered_sources.json'
        if not dynamic.exists():
            continue
        known = {source['url'] for source in result}
        for source in json.loads(dynamic.read_text(encoding='utf-8')):
            if source['url'] not in known:
                result.append(source)
                known.add(source['url'])
    return result


def snapshot_path(root, url):
    return root / 'data/ingestion/research' / (identity(url) + '.json')


def title_key(text):
    # PDF text layers sometimes split a single word into separate glyph runs.
    return ''.join(re.findall(r'\w+', text.casefold()))


def publication_pages(content, source):
    title = title_key(source.get('title_evidence', source['title']))
    if source.get('format') == 'html':
        soup = BeautifulSoup(content, 'html.parser')
        headings = soup.select(source.get('heading_selector', 'h1'))
        blocks = soup.select(source['body_selector'])
        if len(headings) != 1 or title_key(headings[0].get_text(' ', strip=True)) != title or len(blocks) != 1:
            raise ValueError('Article heading or body selector changed')
        if source.get('date_selector'):
            dates = soup.select(source['date_selector'])
            if len(dates) != 1 or dates[0].get_text(' ', strip=True) != source['date_evidence']:
                raise ValueError('Publication date evidence changed')
        if source.get('date_document_evidence') and title_key(source['date_document_evidence']) not in title_key(soup.get_text(' ', strip=True)):
            raise ValueError('Publication date evidence missing from document')
        if source.get('date_attribute_selector'):
            dates = soup.select(source['date_attribute_selector'])
            if len(dates) != 1 or dates[0].get('datetime') != source['date_attribute_value']:
                raise ValueError('Publication date attribute changed')
        pages = [body_text(blocks[0])]
        if source.get('date_evidence_in_body') and title_key(source['date_evidence']) not in title_key(pages[0]):
            raise ValueError('Publication date evidence missing from article')
        return pages
    pdf = PdfReader(io.BytesIO(content))
    if pdf.is_encrypted and (not pdf.decrypt('') or
            not pdf.user_access_permissions & UserAccessPermissions.EXTRACT):
        raise ValueError('Report requires a password or restricts text extraction')
    if not 1 <= len(pdf.pages) <= 300:
        raise ValueError('Unsupported report format or page count')
    pages = [page.extract_text() or '' for page in pdf.pages]
    embedded_title = pdf.metadata.title if pdf.metadata else None
    if title not in title_key(pages[0]) and title != title_key(embedded_title or ''):
        raise ValueError('Report title missing from cover or PDF metadata')
    if source.get('date_evidence') and title_key(source['date_evidence']) not in title_key(pages[0]):
        raise ValueError('Publication date evidence missing from cover')
    return pages


def publication_size_limit(source):
    max_bytes = source.get('max_bytes', 12 * 1024 * 1024)
    if type(max_bytes) is not int or not 1 <= max_bytes <= 50 * 1024 * 1024:
        raise ValueError('Publication size limit must be within 1..50 MiB')
    return max_bytes


def publication_fetcher(root, source):
    url = source['url']
    log = RunLog(root, source['publisher'])
    max_bytes = publication_size_limit(source)
    options = dict(scope={'allowed_hosts': [urlsplit(url).hostname]}, http={
        'user_agent': 'VirtualAssetResearch/0.3 (academic publication pilot)',
        'timeout_seconds': 30, 'max_retries': 1, 'min_interval_seconds': 1,
        'max_redirects': 2, 'max_bytes': max_bytes, 'trust_env': source.get('trust_env', True)})
    return Fetcher(options, log)


def collect_publication(root, source, fetcher=None):
    url = source['url']
    is_html = source.get('format') == 'html'
    if fetcher is None:
        with closing(publication_fetcher(root, source)) as owned_fetcher:
            download = owned_fetcher.get(url, 'text/html' if is_html else 'application/pdf')
    else:
        # A pooled session may serve both small articles and reviewed large PDFs.
        fetcher.options['max_bytes'] = publication_size_limit(source)
        download = fetcher.get(url, 'text/html' if is_html else 'application/pdf')
    return save_publication(root, source, download)


def save_publication(root, source, download):
    url = source['url']
    is_html = source.get('format') == 'html'
    digest = sha256(download.content)
    path = snapshot_path(root, url)
    prior = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    pages = publication_pages(download.content, source)
    text, ranges = clean_pages(pages)
    if is_html:
        ranges[0]['page'] = None
    chunks = chunk_pages(text, ranges, identity(url, digest), 1800)
    if len(text.strip()) < 300 or not chunks:
        raise ValueError('Insufficient report text')
    raw = f"data/raw/{digest}.{'html' if is_html else 'pdf'}"
    write_immutable(root / raw, download.content)
    record = dict(source, content_sha256=digest, raw_path=raw, chunks=chunks)
    record['downloaded_url'] = getattr(download, 'downloaded_url', url)
    changed = any(prior.get(key) != value for key, value in record.items())
    version = identity(url, json.dumps(record, sort_keys=True, ensure_ascii=False))
    version_path = root / 'data/ingestion/research_versions' / (version + '.json')
    if not version_path.exists():
        save_json(version_path, dict(record, collected_at=download.collected_at))
    save_json(path, dict(record, collected_at=download.collected_at))
    return 'created' if changed else 'reused'


def collect_research(root, selected=None):
    results = []
    fetchers, blocked_hosts = {}, set()
    with file_lock(root / 'data/ingestion/research.lock'):
        try:
            for source in sources(root) if selected is None else selected:
                if source.get('format') == 'source_note':
                    continue
                result = {'source_url': source['url']}
                host = urlsplit(source['url']).hostname
                try:
                    if host in blocked_hosts:
                        raise SourceAccessError('Host stopped after earlier access denial/throttling')
                    if host not in fetchers:
                        fetchers[host] = publication_fetcher(root, source)
                    result['status'] = collect_publication(root, source, fetchers[host])
                except Exception as exc:
                    if isinstance(exc, SourceAccessError):
                        blocked_hosts.add(host)
                    logging.getLogger(__name__).exception('Failed to collect %s', source['url'])
                    result.update(status='failed', message=str(exc), error_type=type(exc).__name__)
                results.append(result)
        finally:
            for fetcher in fetchers.values():
                fetcher.close()
    return results


def load_publications(root):
    publications = []
    for source in sources(root):
        if source.get('format') == 'source_note':
            publications.append(dict(source, chunks=[dict(chunk_id=identity(source['url'], source['note']),
                text=source['note'], page_start=None)]))
            continue
        path = snapshot_path(root, source['url'])
        if path.exists():
            publications.append(json.loads(path.read_text(encoding='utf-8')))
    return publications


if __name__ == '__main__':
    results = collect_research(Path(__file__).resolve().parents[1])
    print(json.dumps(results, indent=2))
    raise SystemExit(int(any(item['status'] == 'failed' for item in results)))
