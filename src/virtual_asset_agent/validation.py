"""Application checks that supplement the SQLite constraints."""

import json
from datetime import date, datetime, timedelta, timezone

from .common import PipelineError, allowed_url, identity, local_path, sha256
from .normalization import normalize
from .html_parsing import ParsedHTML, parse_html, unique_node
from bs4 import BeautifulSoup


def validate_result(root, source, version, extraction, chunks, assets, parsed, page_ranges):
    hosts = source['scope']['allowed_hosts']
    allowed_url(version['downloaded_url'], hosts)
    if version['parent_url']:
        allowed_url(version['parent_url'], hosts)
    is_html = isinstance(parsed, ParsedHTML)
    media_type = 'text/html' if is_html else 'application/pdf'
    if version.get('media_type', media_type) != media_type:
        raise PipelineError('Parsed format differs from stored media type')
    extension = 'html' if is_html else 'pdf'
    expected_path = f"data/raw/{version['content_sha256']}.{extension}"
    if version['raw_path'] != expected_path:
        raise PipelineError('Raw path does not match the content hash')
    raw_bytes = local_path(root, expected_path).read_bytes()
    if sha256(raw_bytes) != version['content_sha256']:
        raise PipelineError('Raw file does not match its stored SHA-256')
    if is_html and parse_html(raw_bytes) != parsed:
        raise PipelineError('HTML extraction differs from the saved original')
    soup = BeautifulSoup(raw_bytes, 'html.parser') if is_html else None
    if extraction['version_id'] != version['version_id']:
        raise PipelineError('Extraction points to a different raw version')
    eid = identity('extraction', version['version_id'], extraction['pipeline_version'])
    if extraction['extraction_id'] != eid:
        raise PipelineError('Extraction identity does not match its inputs')
    collected = datetime.strptime(version['collected_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    processed = datetime.strptime(extraction['processed_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    if processed < collected:
        raise PipelineError('Processing time precedes collection time')
    # Both pilot jurisdictions use UTC+08 throughout the configured 2022+ scope.
    local_day = collected.astimezone(timezone(timedelta(hours=8))).date()
    for field in ('published_at', 'updated_at', 'effective_at'):
        value = extraction[field]
        if value is not None:
            day = date.fromisoformat(value)
            if field != 'effective_at' and day > local_day:
                raise PipelineError(f'{field} is later than collection')
    published = extraction['published_at']
    if published and published < source['scope']['published_from']:
        raise PipelineError('Publication date is outside the configured pilot period')
    evidence = json.loads(extraction['metadata_evidence'])
    raw = '\n\n'.join(parsed.pages)
    expected_metadata = normalize(parsed)
    if any(extraction[key] != value for key, value in expected_metadata.items()):
        raise PipelineError('Normalized metadata differs from the cited raw source')
    for field in ('title', 'language', 'published_at', 'updated_at', 'effective_at', 'document_type', 'lifecycle_stage'):
        record = evidence.get(field)
        if not isinstance(record, dict) or 'raw_value' not in record:
            raise PipelineError(f'Missing metadata evidence: {field}')
        value = extraction[field]
        if value is not None and value not in ('unknown', 'other'):
            if not record.get('raw_value') or not record.get('locator'):
                raise PipelineError(f'Unlocated metadata: {field}')
            if field in ('language', 'document_type', 'lifecycle_stage') and not record.get('rule_id'):
                raise PipelineError(f'Missing mapping rule: {field}')
        elif not record.get('reason'):
            raise PipelineError(f'Missing explanation for unknown metadata: {field}')
        if record.get('raw_value'):
            locator = record.get('locator', {})
            if is_html and 'selector' in locator:
                node = unique_node(soup, locator['selector'])
                actual = node.get(locator['attribute']) if 'attribute' in locator else node.get_text(' ', strip=True)
                if actual != record['raw_value']:
                    raise PipelineError(f'HTML metadata differs from cited element: {field}')
            elif 'page' in locator:
                page = locator['page']
                if type(page) is not int or not 1 <= page <= len(parsed.pages) or record['raw_value'] not in parsed.pages[page - 1]:
                    raise PipelineError(f'Metadata is not present on the cited page: {field}')
            elif locator.get('metadata') == 'PDF.Root.Lang':
                if record['raw_value'] != parsed.language_raw:
                    raise PipelineError('Language evidence differs from PDF metadata')
            else:
                raise PipelineError(f'Unsupported metadata locator: {field}')
    text = extraction['clean_text']
    if extraction['raw_text'] != raw or len(text.strip()) < 200 or '\x00' in text:
        raise PipelineError('Empty, truncated, or invalid regulatory body')
    if not chunks or len(page_ranges) != len(parsed.pages):
        raise PipelineError('Missing chunks or physical page mapping')
    previous_end = 0
    for ordinal, chunk in enumerate(chunks):
        start, end = chunk['char_start'], chunk['char_end']
        if chunk['ordinal'] != ordinal or chunk['extraction_id'] != eid or chunk['chunk_id'] != identity('chunk', eid, ordinal):
            raise PipelineError('Invalid chunk identity or sequence')
        page = chunk['page_start']
        if is_html:
            if page is not None or chunk['page_end'] is not None or chunk['section'] is not None:
                raise PipelineError('HTML requires null pages and no invented section title')
            bounds = page_ranges[0]
        else:
            if type(page) is not int or not 1 <= page <= len(page_ranges) or chunk['page_end'] != page:
                raise PipelineError('Invalid physical PDF page')
            bounds = page_ranges[page - 1]
        if not bounds['start'] <= start < end <= bounds['end'] or text[start:end] != chunk['text']:
            raise PipelineError('Chunk text or page mapping is inconsistent')
        if start < previous_end or text[previous_end:start].strip():
            raise PipelineError('Overlapping chunks or lost body text')
        previous_end = end
    if text[previous_end:].strip():
        raise PipelineError('Trailing body text was lost')
    chunk_map = {chunk['chunk_id']: chunk for chunk in chunks}
    for asset in assets:
        chunk = chunk_map.get(asset['evidence_chunk_id'])
        if asset['extraction_id'] != eid or not chunk or 'stablecoin' not in chunk['text'].lower():
            raise PipelineError('Asset classification has no supporting local evidence')
    if not assets:
        raise PipelineError('Document has no stablecoin relevance evidence')
