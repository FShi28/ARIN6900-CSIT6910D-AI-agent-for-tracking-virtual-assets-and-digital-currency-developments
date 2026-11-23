"""Validate the local focused corpus without network calls or model generation."""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from pypdf import PdfReader
from collection_service import save_json
from hk_stablecoin_data import corpus, selected_sources
from research_publications import publication_pages, snapshot_path
from virtual_asset_agent.cleaning import clean_pages, chunk_pages
from virtual_asset_agent.common import identity, sha256, utc_now


def main():
    docs, chunks = corpus(ROOT)
    failures = []
    by_id = {d['document_id']: d for d in docs}
    by_url = {d['url']: d for d in docs}
    if len({c['chunk_id'] for c in chunks}) != len(chunks):
        failures.append('Duplicate chunk identifiers')
    page_counts = {}
    for doc in docs:
        raw = (ROOT / doc['raw_path']).read_bytes()
        if sha256(raw) != doc['content_sha256']:
            failures.append('Raw hash mismatch: ' + doc['url'])
        if doc['format'] == 'pdf':
            page_counts[doc['document_id']] = len(PdfReader(io.BytesIO(raw)).pages)
    for chunk in chunks:
        doc = by_id[chunk['document_id']]
        if not chunk['text'].strip() or chunk['citation']['source_url'] != doc['url']:
            failures.append('Invalid text/citation: ' + chunk['chunk_id'])
        if doc['format'] == 'pdf':
            if not 1 <= chunk['page_start'] <= chunk['page_end'] <= page_counts[doc['document_id']]:
                failures.append('Invalid PDF page range: ' + chunk['chunk_id'])
        elif chunk['page_start'] is not None:
            failures.append('Invented HTML page: ' + chunk['chunk_id'])
    for source in selected_sources(ROOT):
        path = snapshot_path(ROOT, source['url'])
        if not path.exists():
            failures.append('Missing configured snapshot: ' + source['url'])
            continue
        record = json.loads(path.read_text(encoding='utf-8'))
        raw = (ROOT / record['raw_path']).read_bytes()
        pages = publication_pages(raw, source)
        text, ranges = clean_pages(pages)
        if source.get('format') == 'html':
            ranges[0]['page'] = None
        expected = chunk_pages(text, ranges, identity(source['url'], sha256(raw)), 1800)
        if record['chunks'] != expected:
            failures.append('Re-extraction differs: ' + source['url'])
    # Evidence-availability checks, not a claim about an LLM's answer quality.
    cases = [
        ('licensing', 'Explanatory_Notes_on_Licensing', ['application', 'licence']),
        ('reserve requirements', 'Guideline_on_supervision_of_licensed', ['reserve', 'redemption']),
        ('AML requirements', 'Guideline_on_Anti-Money_Laundering', ['customer', 'due diligence']),
        ('consultation response', 'asifma-response-to-hkma-supervision', ['consultation', 'members']),
        ('2026 circular', '20260527-2-EN.pdf', ['relevant stablecoin', 'registered institutions']),
        ('licence register', '/register-of-licensed-stablecoin-issuers/', ['FRS01', 'FRS02'])]
    evidence_checks = []
    for name, url_fragment, terms in cases:
        matching = [d for url, d in by_url.items() if url_fragment in url]
        text = '\n'.join(c['text'] for c in chunks if c['document_id'] in {d['document_id'] for d in matching}).casefold()
        passed = bool(matching) and all(term.casefold() in text for term in terms)
        evidence_checks.append(dict(case=name, passed=passed, urls=[d['url'] for d in matching]))
        if not passed:
            failures.append('Evidence availability failed: ' + name)
    report = dict(checked_at=utc_now(), documents=len(docs), chunks=len(chunks),
                  evidence_checks=evidence_checks, failures=failures,
                  status='passed' if not failures else 'failed')
    save_json(ROOT / 'data/exports/hk_stablecoins/validation.json', report)
    print(json.dumps(report, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
