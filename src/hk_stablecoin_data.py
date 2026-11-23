"""Bounded HK stablecoin corpus, topic-page gap audit and portable RAG export.

Known publications refresh through the existing collection worker. Reviewed
channel adapters now discover and ingest new publications automatically; the
topic audit remains a separate coverage diagnostic. This module never interprets
a document as current law.
"""
import json
from datetime import datetime
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag

from bs4 import BeautifulSoup

from collection_service import save_json
from dashboard_data import load_corpus
from research_publications import sources, load_publications, publication_fetcher
from virtual_asset_agent.common import identity, sha256, utc_now, write_immutable

TOPIC_URL = 'https://www.hkma.gov.hk/eng/key-functions/international-financial-centre/stablecoin-issuers/'


def selected_sources(root):
    return [s for s in sources(root) if s.get('collection') == 'hk_stablecoins'
            or (s['publisher'] == 'Charltons' and s['topic'] == 'Stablecoins')]


def topic_links(content):
    soup = BeautifulSoup(content, 'html.parser')
    heading = soup.find('h1')
    if not heading or heading.get_text(' ', strip=True) != 'Regulatory Regime for Stablecoin Issuers':
        raise ValueError('HKMA topic heading changed')
    blocks = soup.select('.template-top-background.full-content-printer')
    if len(blocks) != 1:
        raise ValueError('HKMA topic body missing or ambiguous')
    found = {}
    for a in blocks[0].select('a[href]'):
        url = urldefrag(urljoin(TOPIC_URL, a['href']))[0]
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname not in ('www.hkma.gov.hk', 'www.elegislation.gov.hk'):
            continue
        if url == TOPIC_URL or not a.get_text(' ', strip=True):
            continue
        found[url] = {'url': url, 'label': a.get_text(' ', strip=True)}
    if not found or len(found) > 100:
        raise ValueError('Unexpected topic-link count; review discovery scope')
    return sorted(found.values(), key=lambda item: item['url'])


def audit_topic(root, known_urls):
    source = {'url': TOPIC_URL, 'publisher': 'HKMA', 'trust_env': False}
    fetcher = publication_fetcher(root, source)
    try:
        downloaded = fetcher.get(TOPIC_URL, 'text/html')
    finally:
        fetcher.close()
    links = topic_links(downloaded.content)
    raw_path = 'data/raw/' + sha256(downloaded.content) + '.html'
    write_immutable(root / raw_path, downloaded.content)
    for link in links:
        link['status'] = 'collected' if link['url'] in known_urls else 'needs_review'
    audit = dict(checked_at=downloaded.collected_at, entry_url=TOPIC_URL,
                 raw_path=raw_path, links=links, scope='Direct English topic-page links only; not a whole-site completeness claim.')
    save_json(root / 'data/ingestion/hk_stablecoins/topic_audit.json', audit)
    return audit


def corpus(root):
    documents, chunks = [], []
    db = root / 'data/ingestion/hkma.sqlite'
    if db.exists():
        original = load_corpus(db)
        for d in original['documents']:
            if d['state'] != 'ready':
                continue
            date = d['published_at'] or ''
            evidence = d['metadata_evidence']['published_at']
            # Preserve the legacy extraction's month-only evidence without
            # inventing a day or using a URL/announcement date for a PDF.
            precision = 'day' if date else 'unknown'
            if not date and evidence.get('reason') == 'partial_date':
                try:
                    date = datetime.strptime(evidence['raw_value'], '%B %Y').strftime('%Y-%m')
                    precision = 'month'
                except ValueError:
                    pass
            documents.append(dict(document_id=d['document_id'], url=d['source_url'],
                title=d['title'], publisher='HKMA', jurisdiction='Hong Kong', topic='Stablecoins',
                authority='primary', kind=d['document_type'], published=date,
                published_precision=precision, date_evidence=evidence,
                format='pdf' if d['media_type'] == 'application/pdf' else 'html',
                content_sha256=d['content_sha256'], raw_path=d['raw_path'],
                collected_at=d['evidence_last_collected_at'], effective_at=d['effective_at'],
                legal_status='not_assessed', chunk_count=d['chunk_count'], storage='hkma.sqlite'))
        for c in original['chunks']:
            chunks.append(dict(c, document_id=c['citation']['document_id']))
    selected = {s['url'] for s in selected_sources(root)}
    for pub in load_publications(root):
        if pub['url'] not in selected or pub.get('format') == 'source_note':
            continue
        d = {k: v for k, v in pub.items() if k != 'chunks'}
        d.update(document_id=identity(pub['url']), chunk_count=len(pub['chunks']), storage='research JSON')
        d.setdefault('format', 'pdf')
        d.setdefault('jurisdiction', 'Hong Kong')
        d.setdefault('authority', 'secondary')
        d.setdefault('published_precision', 'day' if len(d.get('published', '')) == 10 else 'unknown')
        d.setdefault('legal_status', 'not_assessed')
        documents.append(d)
        for c in pub['chunks']:
            page = c['page_start']
            chunks.append(dict(c, document_id=d['document_id'], citation=dict(
                title=d['title'], source_name=d['publisher'], source_url=d['url'],
                url=d['url'] + (f'#page={page}' if page else ''), page=page)))
    if len({d['url'] for d in documents}) != len(documents):
        raise ValueError('Duplicate source URL across primary and research corpus')
    by_id = {d['document_id']: d for d in documents}
    for chunk in chunks:
        d = by_id[chunk['document_id']]
        chunk.update(jurisdiction='Hong Kong', topic='Stablecoins', authority=d['authority'],
                     document_type=d['kind'], published=d['published'],
                     published_precision=d['published_precision'], legal_status=d['legal_status'])
    return documents, chunks


def export_corpus(root):
    documents, chunks = corpus(root)
    folder = root / 'data/exports/hk_stablecoins'
    folder.mkdir(parents=True, exist_ok=True)
    from hk_relationships import relationship_report
    relationship_report(root, documents, chunks)
    for name, records in [('documents', documents), ('chunks', chunks)]:
        # Replace atomically, so an interrupted export cannot truncate a live file.
        path = folder / (name + '.jsonl')
        temporary = path.with_suffix('.jsonl.tmp')
        temporary.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
        temporary.replace(path)
    summary = dict(exported_at=utc_now(), documents=len(documents), chunks=len(chunks),
        by_authority=dict(Counter(d['authority'] for d in documents)),
        by_publisher=dict(Counter(d['publisher'] for d in documents)),
        by_format=dict(Counter(d['format'] for d in documents)),
        available_dates=sorted({d['published'] for d in documents if d['published']}),
        primary_database_present=(root / 'data/ingestion/hkma.sqlite').exists(),
        missing_configured_urls=sorted({s['url'] for s in selected_sources(root)} - {d['url'] for d in documents}),
        limitations=['Curated corpus, not all Hong Kong stablecoin publications.',
                     'PDF tables are text, not validated structured tables.',
                     'No automated current-law or supersession determination.',
                     'Comparative reports and annexes may also discuss other assets or jurisdictions.'])
    save_json(folder / 'summary.json', summary)
    lines = ['# Hong Kong stablecoin data inventory', '',
             f"Exported: {summary['exported_at']}. {len(documents)} publications; {len(chunks)} passages.", '',
             'Primary regulator commentary and speeches are not themselves binding rules. Unknown dates remain blank.', '',
             '| Publisher | Authority | Format | Title / source | Published | Region | Type |',
             '|---|---|---|---|---|---|---|']
    for d in sorted(documents, key=lambda d: (d['publisher'], d['published'], d['title'])):
        title = d['title'].replace('|', '/')
        lines.append(f"| {d['publisher']} | {d['authority']} | {d['format']} | [{title}]({d['url']}) | {d['published'] or 'unverified'} | Hong Kong | {d['kind']} |")
    (folder / 'inventory.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    from hk_coverage import coverage_report
    coverage_report(root, documents, chunks)
    return summary
