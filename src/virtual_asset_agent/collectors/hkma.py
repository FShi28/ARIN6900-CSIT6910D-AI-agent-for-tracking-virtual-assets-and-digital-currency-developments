"""Discover approved documents from the HKMA stablecoin page without recursion."""

from urllib.parse import urljoin
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
import re

from bs4 import BeautifulSoup

from ..common import PipelineError, allowed_url, canonical_url

PRESS_PATH = re.compile(r'^/eng/news-and-media/press-releases/\d{4}/\d{2}/\d{8}-\d+/$')


def is_press_url(url, source):
    url = allowed_url(url, source['scope']['allowed_hosts'])
    parts = urlsplit(url)
    return bool(PRESS_PATH.fullmatch(parts.path)) and not parts.query


def discover_candidates(html, parent_url, source, collected_at):
    if not source.get('discovery', {}).get('enabled'):
        raise PipelineError('Automatic discovery is disabled')
    if canonical_url(parent_url) != canonical_url(source['discovery_url']):
        raise PipelineError('Discovery redirected away from the verified topic page')
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.find('h1')
    if heading is None or heading.get_text(' ', strip=True) != 'Regulatory Regime for Stablecoin Issuers':
        raise PipelineError('HKMA discovery page heading changed')
    items = soup.select('ul.template-related-information li.related-information-item')
    if not items:
        raise PipelineError('HKMA related-information layout is missing')
    local_day = datetime.strptime(collected_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).date()
    found, skipped = {}, []
    for item in items:
        links = item.select('.related-information-text a[href]')
        if len(links) != 1:
            skipped.append({'reason': 'ambiguous_or_missing_link'})
            continue
        link = links[0]
        try:
            url = canonical_url(urljoin(parent_url, link['href']))
            permitted = is_press_url(url, source)
        except PipelineError:
            skipped.append({'reason': 'unapproved_url', 'href': link['href']})
            continue
        label = link.get_text(' ', strip=True)
        if not permitted or not re.search(r'\bstablecoins?\b', label, re.I):
            skipped.append({'source_url': url, 'reason': 'outside_press_release_scope'})
            continue
        dates = item.select('.related-information-date')
        raw_date = dates[0].get_text(' ', strip=True) if len(dates) == 1 else None
        try:
            # Listing date is evidence for selection, never the publication field.
            day = datetime.strptime(raw_date or '', '%d %b %Y').date()
        except ValueError:
            skipped.append({'source_url': url, 'reason': 'missing_or_invalid_listing_date', 'raw_date': raw_date})
            continue
        if day.isoformat() < source['scope']['published_from'] or day > local_day:
            skipped.append({'source_url': url, 'reason': 'outside_date_scope', 'raw_date': raw_date})
            continue
        candidate = {'source_url': url, 'parent_url': parent_url, 'label': label,
                     'listing_date': day.isoformat(), 'listing_date_raw': raw_date,
                     'date_locator': 'li.related-information-item: matching href / .related-information-date',
                     'target_verified': False}
        if url in found and found[url] != candidate:
            raise PipelineError('Conflicting metadata for the same discovered URL')
        found[url] = candidate
    ordered = sorted(found.values(), key=lambda c: (c['listing_date'], c['source_url']), reverse=True)
    if len(ordered) > source['discovery']['max_candidates']:
        raise PipelineError('Discovery exceeds candidate bound; review scope before expanding')
    return ordered, skipped


def discover(html, parent_url, source, target_url=None):
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.find('h1')
    if heading is None or 'Regulatory Regime for Stablecoin Issuers' not in heading.get_text(' ', strip=True):
        raise PipelineError('HKMA discovery page heading changed or body is missing')
    ordered = [canonical_url(url) for url in source['scope']['target_urls']]
    if target_url is not None:
        selected = canonical_url(target_url)
        if selected not in ordered:
            raise PipelineError('Requested document is not in the approved target list')
        ordered = [selected]
    allowed = set(ordered)
    found = {}
    for link in soup.find_all('a', href=True):
        try:
            href = canonical_url(urljoin(parent_url, link['href']))
        except PipelineError:
            continue
        # Navigation and other hosts are not fetch candidates.
        if href not in allowed:
            continue
        url = allowed_url(href, source['scope']['allowed_hosts'])
        if not link.get_text(' ', strip=True):
            raise PipelineError('Target document link has no discoverable label')
        found[url] = {'source_url': url, 'parent_url': parent_url}
    if set(found) != allowed:
        raise PipelineError('Approved document was not found on the live discovery page')
    return [found[url] for url in ordered]
