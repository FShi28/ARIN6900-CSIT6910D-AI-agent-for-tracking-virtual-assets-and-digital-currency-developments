"""Conservative source facts and deterministic, evidenced topic classification."""

import re
from datetime import date

from .common import json_bytes
from .html_parsing import ParsedHTML, TITLE, DATE, KIND

MONTHS = {name: number for number, name in enumerate(
    'January February March April May June July August September October November December'.split(), 1)}


def normalize(parsed):
    if isinstance(parsed, ParsedHTML):
        return normalize_html(parsed)
    evidence = {key: {'raw_value': None, 'reason': 'not_extracted'} for key in (
        'title', 'language', 'published_at', 'updated_at', 'effective_at', 'document_type', 'lifecycle_stage')}
    title_rule = 'cover-title-v1' if parsed.cover_kind == 'guideline' else 'consultation-cover-title-v1'
    evidence['title'] = {'raw_value': parsed.title_raw, 'locator': {'page': 1}, 'rule_id': title_rule}
    if parsed.cover_kind == 'guideline':
        document_type = 'guideline'
        evidence['document_type'] = {'raw_value': parsed.title_raw, 'locator': {'page': 1}, 'rule_id': 'guideline-title-v1'}
    else:
        document_type = 'other'
        evidence['document_type'] = {'raw_value': 'Consultation Conclusions', 'locator': {'page': 1},
                                     'reason': 'unmapped_source_type', 'rule_id': 'consultation-type-v1'}
    language = None
    evidence['language'] = {'raw_value': None, 'reason': 'metadata_missing_or_unsupported'}
    if parsed.language_raw and parsed.language_raw.lower().split('-')[0] == 'en':
        language = 'en'
        evidence['language'] = {'raw_value': parsed.language_raw, 'locator': {'metadata': 'PDF.Root.Lang'}, 'rule_id': 'language-v1'}
    published = None
    evidence['published_at'] = {'raw_value': None, 'reason': 'not_located_on_cover'}
    if parsed.cover_date_raw:
        exact = re.fullmatch(r'(\d{1,2}) (\w+) (\d{4})', parsed.cover_date_raw)
        if exact:
            day, month, year = exact.groups()
            published = date(int(year), MONTHS[month], int(day)).isoformat()
            evidence['published_at'] = {'raw_value': parsed.cover_date_raw, 'locator': {'page': 1}, 'rule_id': 'cover-date-v1'}
        else:
            evidence['published_at'] = {'raw_value': parsed.cover_date_raw, 'locator': {'page': 1}, 'reason': 'partial_date'}
    return {'title': parsed.title, 'language': language, 'published_at': published,
            'updated_at': None, 'effective_at': None, 'document_type': document_type,
            'lifecycle_stage': 'unknown', 'metadata_evidence': json_bytes(evidence).decode('utf-8')}


def normalize_html(parsed):
    evidence = {key: {'raw_value': None, 'reason': 'not_extracted'}
                for key in ('updated_at', 'effective_at', 'lifecycle_stage')}
    evidence['title'] = {'raw_value': parsed.title_raw, 'locator': {'selector': TITLE},
                         'rule_id': 'hkma-html-title-v1'}
    evidence['document_type'] = {'raw_value': 'Press Releases', 'locator': {'selector': KIND},
                                 'rule_id': 'hkma-html-type-v1'}
    evidence['body'] = {'locator': {'selector': parsed.body_selector}, 'rule_id': 'html-dom-text-v1'}
    language = None
    evidence['language'] = {'raw_value': None, 'reason': 'metadata_missing_or_unsupported'}
    if parsed.language_raw and parsed.language_raw.lower().split('-')[0] == 'en':
        language = 'en'
        evidence['language'] = {'raw_value': parsed.language_raw,
                               'locator': {'selector': 'html', 'attribute': 'lang'}, 'rule_id': 'language-v1'}
    published = None
    evidence['published_at'] = {'raw_value': None, 'reason': 'not_located_in_article_header'}
    if parsed.published_raw:
        evidence['published_at'] = {'raw_value': parsed.published_raw,
                                   'locator': {'selector': DATE}, 'reason': 'unsupported_date_format'}
        match = re.fullmatch(r'(\d{1,2}) ([A-Za-z]+) (\d{4})', parsed.published_raw)
        if match:
            day, month, year = match.groups()
            months = {**MONTHS, **{k[:3]: v for k, v in MONTHS.items()}}
            if month in months:
                # Invalid calendar dates fail; missing/unsupported precision remains unknown.
                published = date(int(year), months[month], int(day)).isoformat()
                evidence['published_at'] = {'raw_value': parsed.published_raw,
                                           'locator': {'selector': DATE}, 'rule_id': 'hkma-html-date-v1'}
    return {'title': parsed.title, 'language': language, 'published_at': published,
            'updated_at': None, 'effective_at': None, 'document_type': 'press_release',
            'lifecycle_stage': 'unknown', 'metadata_evidence': json_bytes(evidence).decode('utf-8')}


def classify(chunks):
    # Textual subject relevance only; this is not a legal applicability decision.
    for chunk in chunks:
        if re.search(r'\bstablecoins?\b', chunk['text'], re.I):
            return [{'extraction_id': chunk['extraction_id'], 'asset_class': 'stablecoin',
                     'rule_id': 'stablecoin_word_v1', 'evidence_chunk_id': chunk['chunk_id']}]
    return []
