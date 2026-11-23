"""Verified listing adapters. No network, persistence, or inferred legal effect."""
import io
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urldefrag

from bs4 import BeautifulSoup
from pypdf import PdfReader

from ..html_parsing import body_text

STABLE = re.compile(r'\bstablecoins?\b', re.I)
HONG_KONG = re.compile(r'\b(?:Hong\s+Kong|HKMA|HK)\b', re.I)


class OutsideScope(ValueError):
    """Valid publication that does not satisfy the configured subject scope."""


def same_host_link(base, href):
    url = urldefrag(urljoin(base, href))[0]
    if urlsplit(url).scheme == 'https' and urlsplit(url).hostname == urlsplit(base).hostname:
        return url
    return None


def listing(content, channel, page_url):
    soup = BeautifulSoup(content, 'html.parser')
    key = channel['id']
    if key == 'hkma':
        heading = soup.find('h1')
        if not heading or heading.get_text(' ', strip=True) != 'Regulatory Regime for Stablecoin Issuers':
            raise ValueError('HKMA topic heading changed')
        containers = soup.select('.template-top-background.full-content-printer')
        selector = 'a[href]'
    elif key == 'charltons':
        containers = soup.select('.newsletter_card_ui')
        selector = 'a[href]'
    elif key == 'asifma':
        containers = soup.select('section.mk-search-loop article.research')
        selector = 'h3.the-title a[href]'
    else:
        containers = soup.select('article.block-post')
        selector = 'a[href*="/post/"]'
    if not containers:
        raise ValueError('Listing layout missing or no results; review source, not a successful empty scan')
    found = {}
    for container in containers:
        for a in container.select(selector):
            title = a.get_text(' ', strip=True)
            url = same_host_link(page_url, a['href'])
            if not title or not url:
                continue
            relevant = key == 'linklaters' or bool(STABLE.search(title))
            if key == 'asifma':
                relevant = relevant and bool(HONG_KONG.search(title))
            if key == 'hkma':
                relevant = (relevant or '/insight/' in url or '/speeches/' in url
                            or urlsplit(url).path.endswith('.pdf'))
                # Press releases already have an automatic SQLite collector.
                # Do not create a second copy in the research JSON store.
                if '/press-releases/' in url:
                    relevant = False
            if relevant and url != channel['url']:
                found[url] = dict(url=url, title=title, listing_url=page_url)
    if len(found) > 150:
        raise ValueError('Listing exceeds candidate bound')
    next_url = None
    for a in soup.select('a[href]'):
        if a.get_text(' ', strip=True).lower().startswith('next') or 'next' in a.get('rel', []):
            target = same_host_link(page_url, a['href'])
            if target and urlsplit(target).path == urlsplit(page_url).path:
                next_url = target
                break
    return list(found.values()), next_url


def hk_relevant_text(title, text, channel):
    if channel['id'] in ('hkma', 'charltons'):
        return bool(STABLE.search(title + ' ' + text))
    if STABLE.search(title) and HONG_KONG.search(title):
        return True
    # Regional bulletins often mention HK and Singapore in different sections.
    # Do not label Singapore stablecoin news as Hong Kong merely from co-occurrence.
    if 'Hong Kong SAR:' in text and 'Singapore:' in text:
        section = text.split('Hong Kong SAR:', 1)[1].split('Singapore:', 1)[0]
        return bool(STABLE.search(section))
    return any(STABLE.search(p) and HONG_KONG.search(p) for p in text.split('\n') if len(p) < 600)


def html_metadata(content, channel):
    soup = BeautifulSoup(content, 'html.parser')
    heading = 'h1'
    body = '.template-content-area' if channel['id'] == 'hkma' else 'article.post-view .post-view__body'
    if len(soup.select(heading)) != 1 or len(soup.select(body)) != 1:
        raise ValueError('Unsupported article layout')
    title = soup.select_one(heading).get_text(' ', strip=True)
    text = body_text(soup.select_one(body))
    if not hk_relevant_text(title, text, channel):
        raise OutsideScope('No verified Hong Kong stablecoin relevance in article body')
    result = dict(title=title, format='html', heading_selector=heading, body_selector=body,
                  published='', published_precision='unknown')
    if channel['id'] == 'hkma':
        dates = soup.select('.content-area > .date')
        if len(dates) == 1:
            raw = dates[0].get_text(' ', strip=True)
            result.update(published=datetime.strptime(raw, '%d %b %Y').strftime('%Y-%m-%d'),
                          published_precision='day', date_selector='.content-area > .date', date_evidence=raw)
    else:
        dates = soup.select('article.post-view > .post-view__header time[datetime]')
        if len(dates) == 1:
            raw = dates[0]['datetime']
            day = datetime.strptime(raw[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
            result.update(published=day, published_precision='day',
                          date_attribute_selector='article.post-view > .post-view__header time[datetime]',
                          date_attribute_value=raw)
    return result


def charltons_pdf(content, url):
    soup = BeautifulSoup(content, 'html.parser')
    headings = soup.select('h1.entry-title')
    if len(headings) != 1:
        raise ValueError('Charltons article title missing or ambiguous')
    links = set()
    for a in soup.select('a[href]'):
        target = same_host_link(url, a['href'])
        if (target and '/legal/newsletters/' in urlsplit(target).path
                and urlsplit(target).path.lower().endswith('.pdf')
                and 'download' in a.get_text(' ', strip=True).lower()):
            links.add(target)
    if len(links) != 1:
        raise ValueError('Charltons full-text PDF missing or ambiguous')
    return headings[0].get_text(' ', strip=True), links.pop()


def pdf_metadata(content, candidate, channel):
    pdf = PdfReader(io.BytesIO(content))
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 300:
        raise ValueError('Unsupported PDF')
    cover = pdf.pages[0].extract_text() or ''
    if not STABLE.search(cover):
        raise ValueError('Stablecoin scope not verified on PDF cover')
    if channel['id'] == 'asifma' and not HONG_KONG.search(candidate['title']):
        raise ValueError('Not a Hong Kong consultation response')
    # The title is the publisher's own listing label, not an invented PDF title.
    # A cover anchor and preserved listing snapshot are separate evidence.
    anchor = next(line.strip() for line in cover.splitlines() if STABLE.search(line))
    result = dict(title=candidate['title'], title_evidence=anchor, title_origin='publisher listing',
                  format='pdf', published='', published_precision='unknown')
    # Only standalone dates near the beginning, never dates mentioned inside
    # a paragraph about another document or a consultation deadline.
    pattern = r'(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}'
    leading = [line.strip() for line in cover.splitlines() if line.strip()][:12]
    dates = [line for line in leading if re.fullmatch(pattern, line)]
    unique = list(dict.fromkeys(dates))
    if len(unique) == 1:
        raw = unique[0]
        day_precision = raw[0].isdigit()
        date = datetime.strptime(raw, '%d %B %Y' if day_precision else '%B %Y')
        result.update(published=date.strftime('%Y-%m-%d' if day_precision else '%Y-%m'),
                      published_precision='day' if day_precision else 'month', date_evidence=raw)
    return result
