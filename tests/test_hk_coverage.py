import json

import pytest

from hk_coverage import coverage_report
from research_publications import publication_pages
from virtual_asset_agent.common import sha256


@pytest.fixture
def evidence(tmp_path):
    raw = b'original reviewed publication'
    (tmp_path / 'config').mkdir()
    (tmp_path / 'data/raw').mkdir(parents=True)
    (tmp_path / 'data/raw/document.pdf').write_bytes(raw)
    config = dict(reviewed_on='2026-11-20', purpose='Evidence test', global_gaps=['Missing consolidated law'],
        sources={'guide': dict(url='https://example.test/guide.pdf', reviewed_sha256=sha256(raw),
                              new_document_discovery='not implemented')},
        checks=[dict(id='reserve-1', topic='reserve', check='Full backing', source='guide',
                     section='2.2', page_start=5, page_end=6, anchor='2.2. Full backing', applies_to='issuers')])
    (tmp_path / 'config/hk_stablecoin_coverage.json').write_text(json.dumps(config))
    doc = dict(document_id='d1', title='Guide', url='https://example.test/guide.pdf', authority='primary',
               raw_path='data/raw/document.pdf', content_sha256=sha256(raw), published='2025-08')
    chunks = [dict(document_id='d1', chunk_id='c1', page_start=5, page_end=5,
                   text='2.2. Full backing\nRequirements and explanations.')]
    return tmp_path, doc, chunks


def test_located_evidence_is_not_legal_completeness(evidence):
    root, doc, chunks = evidence
    result = coverage_report(root, [doc], chunks)
    assert result['by_status'] == {'evidence_located': 1}
    assert result['legal_completeness'] is False
    assert result['rows'][0]['citation_url'].endswith('#page=5')


def test_changed_source_requires_review_even_when_anchor_still_exists(evidence):
    root, doc, chunks = evidence
    new = b'updated source with original heading'
    (root / doc['raw_path']).write_bytes(new)
    doc['content_sha256'] = sha256(new)
    assert coverage_report(root, [doc], chunks)['rows'][0]['status'] == 'source_changed_requires_review'


def test_missing_corrupt_and_wrong_page_evidence_do_not_pass(evidence):
    root, doc, chunks = evidence
    assert coverage_report(root, [], [])['rows'][0]['status'] == 'missing_document'
    chunks[0]['page_start'] = chunks[0]['page_end'] = 2  # Table of contents is insufficient.
    assert coverage_report(root, [doc], chunks)['rows'][0]['status'] == 'anchor_not_found'
    (root / doc['raw_path']).write_bytes(b'corrupted')
    assert coverage_report(root, [doc], chunks)['rows'][0]['status'] == 'raw_evidence_invalid'


def test_sfc_publication_date_is_separate_from_page_updated_date():
    source = dict(title='Stablecoin circular', format='html', heading_selector='#content h1',
        body_selector='#content .newsc', date_evidence='27 May 2026',
        date_selector='#content small:not(:-soup-contains("Page last updated"))')
    content = b'''<html><div id="content"><h1>Stablecoin circular</h1>
    <small>27 May 2026</small><div class="newsc">Actual regulatory text.</div>
    <small>Page last updated: 20 November 2026</small></div></html>'''
    assert publication_pages(content, source) == ['Actual regulatory text.']
    with pytest.raises(ValueError, match='date evidence'):
        publication_pages(content.replace(b'27 May', b'28 May'), source)
