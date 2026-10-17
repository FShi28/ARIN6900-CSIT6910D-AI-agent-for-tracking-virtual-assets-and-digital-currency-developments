"""Conservative HKMA HTML comparison. Fingerprints never replace raw hashes."""

from bs4 import BeautifulSoup

from .common import PipelineError, json_bytes, local_path, sha256
from .html_parsing import ARTICLE, parse_html, unique_node

RULE = 'hkma-html-csrf-v1'


def fingerprints(raw):
    parse_html(raw)  # Never classify a login/error/layout-change response as unchanged.
    soup = BeautifulSoup(raw, 'html.parser')
    article = {'dom': str(unique_node(soup, ARTICLE)),
               'language': unique_node(soup, 'html').get('lang'),
               'dates': [str(n) for n in soup.select('meta[name="date"],meta[name="last-modified"],.pr-revision')]}
    for token in soup.select('head meta[name="csrf_token"]'):
        if 'content' in token.attrs:
            token['content'] = ''
    return {'response_fingerprint': sha256(str(soup).encode('utf-8')),
            'article_fingerprint': sha256(json_bytes(article)), 'rule_id': RULE}


def inspect_html(root, repository, source_id, url, download):
    current = fingerprints(download.content)
    history = repository.html_history(source_id, url)
    matched = None
    previous = None
    for record in history:
        raw = local_path(root, record['raw_path']).read_bytes()
        if sha256(raw) != record['content_sha256']:
            raise PipelineError('Historical HTML original failed SHA-256 verification')
        prior = fingerprints(raw)
        if previous is None:
            previous = prior
        if matched is None and prior['response_fingerprint'] == current['response_fingerprint']:
            matched = repository.version(record['version_id'])
    if previous is None:
        change = 'new'
    elif previous['article_fingerprint'] != current['article_fingerprint']:
        change = 'content_changed'
    elif previous['response_fingerprint'] != current['response_fingerprint']:
        change = 'page_changed'
    else:
        change = 'unchanged'
    if matched is not None:
        evidence = local_path(root, matched['raw_path']).read_bytes()
        if (sha256(evidence) != matched['content_sha256']
                or fingerprints(evidence)['response_fingerprint'] != current['response_fingerprint']):
            raise PipelineError('HTML observation is inconsistent with its evidence version')
    return matched, dict(current, change_type=change)
