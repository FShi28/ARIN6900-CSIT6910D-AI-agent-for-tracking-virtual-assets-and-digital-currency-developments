"""Conservative CBDC discovery and classification from verified HKMA/BIS pages."""
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urldefrag

from bs4 import BeautifulSoup
from ..html_parsing import body_text

PROJECTS = {
    'e_hkd': r'\be[-\s]HKD\b',
    'mbridge': r'\bmBridge\b|\bInthanon[-–\s]LionRock\b|\bLionRock[-–\s]Inthanon\b',
    'ensemble': r'\b(?:Project\s+Ensemble|Ensemble\s*TX)\b',
    'aurum': r'\bAurum\b',
    'sela': r'\bSela\b',
    'e_cny_hk': r'\be[-\s]CNY\b|\bdigital (?:renminbi|yuan)\b',
}
CBDC = re.compile(r'\bCBDCs?\b|central bank digital currenc|tokeni[sz]ed central bank money', re.I)


def classification(text):
    """Text mentions, not an inference of issuance, membership or current law."""
    evidence = {key: match.group(0) for key, pattern in PROJECTS.items()
                if (match := re.search(pattern, text, re.I))}
    if not evidence or not (CBDC.search(text) or set(evidence) & {'e_hkd', 'e_cny_hk', 'mbridge', 'aurum', 'sela'}):
        raise ValueError('No supported Hong Kong CBDC project evidence')
    types = []
    if re.search(r'\bretail\b|\brCBDC\b', text, re.I):
        types.append('retail')
    if re.search(r'\bwholesale\b|\bwCBDC\b', text, re.I):
        types.append('wholesale')
    assets = ['CBDC']
    if re.search(r'tokeni[sz]ed deposits?', text, re.I):
        assets.append('Tokenised deposits')
    if re.search(r'\bstablecoins?\b', text, re.I):
        assets.append('Stablecoins')
    regions = ['Hong Kong']
    for label, pattern in [('Mainland China', r"People.s (?:Bank of China|Republic of China)|\bPBoC\b|Mainland China"),
                           ('Thailand', r'\bThailand\b'), ('United Arab Emirates', r'United Arab Emirates|\bUAE\b'),
                           ('Saudi Arabia', r'Saudi (?:Arabia|Central Bank)'), ('Israel', r'\bIsrael\b'),
                           ('Brazil', r'\bBra[sz]il\b'), ('France', r'Banque de France|\bFrance\b')]:
        if re.search(pattern, text, re.I):
            regions.append(label)
    return dict(projects=list(evidence), project_mention_evidence=evidence,
                cbdc_types_mentioned=types, asset_classes_mentioned=assets,
                jurisdictions_mentioned=regions, jurisdiction='Hong Kong',
                project_stage='not_assessed', legal_status='not_assessed',
                classification_note='Deterministic document mentions. Regions are not a participant list; type mentions are not a project-wide classification.')


def listing(content, channel):
    soup = BeautifulSoup(content, 'html.parser')
    headings = soup.select('h1')
    if len(headings) != 1 or headings[0].get_text(' ', strip=True) != channel['heading']:
        raise ValueError('CBDC listing identity changed')
    blocks = soup.select(channel['body_selector'])
    if len(blocks) != 1:
        raise ValueError('CBDC listing layout changed')
    found = {}
    for a in blocks[0].select('a[href]'):
        url = urldefrag(urljoin(channel['url'], a['href']))[0]
        p = urlsplit(url)
        if p.scheme != 'https' or p.hostname not in ('www.hkma.gov.hk', 'www.bis.org'):
            continue
        is_pdf = p.path.lower().endswith('.pdf')
        supported = (p.hostname == 'www.hkma.gov.hk' and '/eng/news-and-media/' in p.path
                     and bool(re.search(r'/\d{4}/\d{2}/\d+', p.path))
                     or p.hostname == 'www.bis.org' and p.path.startswith(('/publications/', '/media-releases/')))
        if not (is_pdf or supported) or url == channel['url']:
            continue
        found[url] = dict(url=url, title=a.get_text(' ', strip=True), format='pdf' if is_pdf else 'html',
                          discovered_from=channel['url'], publisher='HKMA' if p.hostname == 'www.hkma.gov.hk' else 'BIS')
    if not found or len(found) > 150:
        raise ValueError('Unexpected CBDC listing candidate count')
    return list(found.values())


def html_metadata(content, publisher):
    soup = BeautifulSoup(content, 'html.parser')
    body = '.template-content-area' if publisher == 'HKMA' else 'article'
    if len(soup.select('h1')) != 1 or len(soup.select(body)) != 1:
        raise ValueError('CBDC article layout changed')
    title = soup.select_one('h1').get_text(' ', strip=True)
    text = body_text(soup.select_one(body))
    result = dict(title=title, format='html', heading_selector='h1', body_selector=body,
                  published='', published_precision='unknown', **classification(title + '\n' + text))
    if publisher == 'HKMA':
        dates = soup.select('.content-area > .date')
        if len(dates) != 1:
            raise ValueError('HKMA article publication date missing or ambiguous')
        raw = dates[0].get_text(' ', strip=True)
        day = datetime.strptime(raw, '%d %b %Y').strftime('%Y-%m-%d')
        result.update(published=day, published_precision='day', date_selector='.content-area > .date', date_evidence=raw)
    else:
        dates = soup.select('meta[property="article:published_time"]')
        if len(dates) != 1:
            raise ValueError('BIS publication date missing or ambiguous')
        day = datetime.strptime(dates[0]['content'], '%Y-%m-%dT%H:%M:%S%z').date().isoformat()
        # Visible date, not a timestamp inferred from the URL or collection time.
        raw = datetime.strptime(day, '%Y-%m-%d').strftime('%d %B %Y').lstrip('0')
        if raw not in soup.get_text(' ', strip=True):
            raise ValueError('BIS visible publication date does not match metadata')
        result.update(published=day, published_precision='day', date_document_evidence=raw)
    return result
