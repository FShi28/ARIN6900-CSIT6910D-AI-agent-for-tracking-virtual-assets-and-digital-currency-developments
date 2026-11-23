"""Official government RSS and SFC e-Distribution search adapters."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlsplit
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .hk_channels import STABLE, OutsideScope
from ..html_parsing import body_text


def brdr_listing(content, page_url):
    data = json.loads(content)
    if not isinstance(data.get('resultList'), list) or not isinstance(data.get('totalRecordNumber'), int):
        raise ValueError('HKMA repository search schema changed')
    if data['totalRecordNumber'] > 0 and not data['resultList']:
        raise ValueError('HKMA repository returned an unexpected empty page')
    found = []
    for item in data['resultList']:
        ref = item['docId']
        title = BeautifulSoup(item['docLongTitle'], 'html.parser').get_text(' ', strip=True)
        # The search also returns broader banking rules and Chinese variants.
        if not ref.endswith('-EN') or not STABLE.search(title):
            continue
        if not re.fullmatch(r'\d{8}-\d+-EN', ref):
            raise ValueError('Unexpected HKMA repository document identifier')
        found.append(dict(url='https://brdr.hkma.gov.hk/eng/doc-ldg/docId/' + ref,
                          title=title, listing_url=page_url,
                          repository_issue_date=item.get('issueDateStr'),
                          repository_version_label=item.get('versionCode')))
    return found, data['totalRecordNumber']


def brdr_pdf(content, page_url):
    soup = BeautifulSoup(content, 'html.parser')
    ref = urlsplit(page_url).path.rsplit('/', 1)[-1]
    targets = {urljoin(page_url, a['href']) for a in soup.select('a[href]')
               if a['href'] == f'/eng/doc-ldg/docId/getPdf/{ref}/{ref}.pdf'}
    if len(targets) != 1:
        raise ValueError('HKMA repository PDF link missing or ambiguous')
    return targets.pop()


def sfc_scope(text):
    return bool(STABLE.search(text) or
                ('custody' in text.lower() and 'virtual asset' in text.lower()))


def official_listing(content, channel, page_url):
    found = {}
    if channel['id'] == 'sfc':
        data = json.loads(content)
        if not isinstance(data.get('items'), list) or not isinstance(data.get('total'), int):
            raise ValueError('SFC search schema changed')
        for item in data['items']:
            ref, title = item['refNo'], item['title']
            if not re.fullmatch(r'\d{2}EC\d+', ref) or item['lang'] != 'EN':
                raise ValueError('Unexpected SFC reference or language')
            if not sfc_scope(title):
                continue
            # Verified document endpoint used by existing official records.
            url = ('https://apps.sfc.hk/edistributionWeb/api/circular/list-content/'
                   'circular/doc?lang=EN&refNo=' + ref)
            found[url] = dict(url=url, title=title, listing_url=page_url)
        return list(found.values()), data['total']
    if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('DTD/entities not allowed in RSS')
    root = ET.fromstring(content)
    if root.tag != 'rss' or root.findtext('./channel/title') != 'HKSAR Government Press Releases':
        raise ValueError('Government RSS identity/layout changed')
    items = root.findall('./channel/item')
    if not items or len(items) > 500:
        raise ValueError('Unexpected government RSS item count')
    for item in items:
        title, url = item.findtext('title', ''), item.findtext('link', '')
        description = BeautifulSoup(item.findtext('description', ''), 'html.parser').get_text(' ', strip=True)
        if not STABLE.search(title + ' ' + description):
            continue
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'www.info.gov.hk'
                or not re.fullmatch(r'/gia/general/\d{6}/\d{2}/P\d+(?:p)?\.htm', parsed.path)):
            raise ValueError('Unexpected government article URL')
        # Print and ordinary releases are the same publication identifier.
        url = re.sub(r'p\.htm$', '.htm', url)
        found[url] = dict(url=url, title=title, listing_url=page_url)
    return list(found.values()), None


def official_metadata(content, channel):
    soup = BeautifulSoup(content, 'html.parser')
    sfc = channel['id'] == 'sfc'
    heading, body = ('#content h1', '#content .newsc') if sfc else ('#PRHeadlineSpan', '#pressrelease')
    if len(soup.select(heading)) != 1 or len(soup.select(body)) != 1:
        raise ValueError('Official article layout changed')
    title = soup.select_one(heading).get_text(' ', strip=True)
    text = body_text(soup.select_one(body))
    if not (sfc_scope(title + ' ' + text) if sfc else STABLE.search(title + ' ' + text)):
        raise OutsideScope('No stablecoin or configured custody relevance')
    result = dict(title=title, format='html', heading_selector=heading, body_selector=body,
                  published='', published_precision='unknown')
    if sfc:
        selector = '#content small:not(:-soup-contains("Page last updated"))'
        dates = soup.select(selector)
        if len(dates) != 1:
            raise ValueError('SFC publication date missing or ambiguous')
        raw = dates[0].get_text(' ', strip=True)
        result.update(published=datetime.strptime(raw, '%d %b %Y').strftime('%Y-%m-%d'),
                      published_precision='day', date_selector=selector, date_evidence=raw,
                      coverage_scope='Stablecoin services or broader virtual-asset custody; entity-specific applicability')
    else:
        dates = re.findall(r'Ends/\s*([A-Za-z]+, [A-Za-z]+ \d{1,2}, \d{4})', soup.get_text(' ', strip=True))
        if len(set(dates)) != 1:
            raise ValueError('Government publication date missing or ambiguous')
        raw = dates[0]
        result.update(published=datetime.strptime(raw, '%A, %B %d, %Y').strftime('%Y-%m-%d'),
                      published_precision='day', date_evidence=raw, date_document_evidence='Ends/' + raw)
    return result
