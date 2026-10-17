"""HTML text utilities and the verified HKMA press-release layout."""

from dataclasses import dataclass

from bs4 import BeautifulSoup

from .common import PipelineError

ARTICLE = '.layout-press-release-detail .content-area'
BODY = ARTICLE + ' .template-content-area'
TITLE = ARTICLE + ' .press-release-title'
DATE = ARTICLE + ' > .date'
KIND = ARTICLE + ' .press-release-tag'


def unique_node(soup, selector, required=True):
    nodes = soup.select(selector)
    if len(nodes) > 1 or (required and not nodes):
        raise PipelineError(f'Missing or ambiguous HTML element: {selector}')
    return nodes[0] if nodes else None


def body_text(node):
    """Keep DOM order and inline punctuation; add boundaries at block elements."""
    fragment = BeautifulSoup(str(node), 'html.parser')
    for unwanted in fragment.select('script,style,noscript,template,nav,footer,[hidden],[aria-hidden="true"]'):
        unwanted.decompose()
    for br in fragment.find_all('br'):
        br.replace_with('\n')
    for block in fragment.find_all(['p', 'div', 'section', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'blockquote']):
        block.insert_before('\n')
        block.insert_after('\n')
    for cell in fragment.find_all(['td', 'th']):
        cell.insert_after('\t')
    return fragment.get_text().strip()


@dataclass(frozen=True)
class ParsedHTML:
    # One unpaginated body block; never interpreted as a physical page.
    pages: list[str]
    title: str
    title_raw: str
    language_raw: str | None
    published_raw: str | None
    body_selector: str = BODY


def parse_html(content):
    if b'\x00' in content:
        raise PipelineError('HTML contains NUL bytes')
    soup = BeautifulSoup(content, 'html.parser')
    if soup.contains_replacement_characters:
        raise PipelineError('HTML decoding lost characters')
    unique_node(soup, ARTICLE)
    kind = unique_node(soup, KIND).get_text(' ', strip=True)
    if kind != 'Press Releases':
        raise PipelineError('Unsupported HKMA HTML publication type')
    title_raw = unique_node(soup, TITLE).get_text(' ', strip=True)
    title = ' '.join(title_raw.split())
    if not title or 'stablecoin' not in title.lower():
        raise PipelineError('HTML title is outside the stablecoin pilot')
    body = body_text(unique_node(soup, BODY))
    if len(body.strip()) < 200 or 'stablecoin' not in body.lower():
        raise PipelineError('Missing substantive stablecoin HTML body')
    published = unique_node(soup, DATE, required=False)
    language = unique_node(soup, 'html').get('lang')
    return ParsedHTML([body], title, title_raw, language,
                      published.get_text(' ', strip=True) if published else None)
