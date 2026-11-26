"""Review-only downloads from the verified HKMA CBDC page; no corpus admission."""
import io
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.constants import UserAccessPermissions
from collection_service import save_json
from research_publications import publication_fetcher
from virtual_asset_agent.common import sha256, write_immutable
from virtual_asset_agent.fetching import SourceAccessError

ROOT = Path(__file__).resolve().parents[1]
TOPIC = 'https://www.hkma.gov.hk/eng/key-functions/international-financial-centre/fintech/central-bank-digital-currency/'


def main():
    folder = ROOT / 'data/discovery/hk_cbdc'
    report = folder / 'pdf_review.json'
    records = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {}
    fetchers, blocked = {}, set()
    try:
        hk = publication_fetcher(ROOT, dict(url=TOPIC, publisher='HKMA CBDC review', trust_env=False, max_bytes=50*1024*1024))
        fetchers['HKMA'] = hk
        listing = hk.get(TOPIC, 'text/html')
        soup = BeautifulSoup(listing.content, 'html.parser')
        candidates = [(a.get_text(' ', strip=True), urljoin(TOPIC, a['href']))
                      for a in soup.select('.template-top-background a[href]')
                      if a['href'].split('?')[0].lower().endswith('.pdf')
                      and (a['href'].startswith('/media/eng/') or a['href'].startswith('https://www.bis.org/'))]
        candidates.append(('Project Aurum Phase 2: exploring privacy-enhancing technologies for digital cash',
            'https://www.bis.org/publications/project-aurum-phase-2-exploring-privacy-enhancing-technologies-digital-cash.pdf'))
        candidates.extend([
            ('Project Aurum: A Prototype for Two-tier Central Bank Digital Currency (CBDC)',
             'https://www.bis.org/publications/project-aurum-prototype-two-tier-central-bank-digital-currency-cbdc.pdf'),
            ('Project Sela: an accessible and secure retail CBDC ecosystem',
             'https://www.bis.org/publications/project-sela-accessible-and-secure-retail-cbdc-ecosystem.pdf')])
        for title, url in candidates:
            prior = records.get(url, {})
            if prior and prior.get('message') not in ('Response exceeds configured size limit', 'Encrypted PDF requires extraction permission review'):
                continue
            publisher = 'BIS' if 'www.bis.org' in url else 'HKMA'
            if publisher in blocked:
                continue
            try:
                if publisher not in fetchers:
                    fetchers[publisher] = publication_fetcher(ROOT, dict(url=url, publisher=publisher, trust_env=False, max_bytes=50*1024*1024))
                d = fetchers[publisher].get(url, 'application/pdf')
                path = 'data/raw/' + sha256(d.content) + '.pdf'
                write_immutable(ROOT / path, d.content)
                pdf = PdfReader(io.BytesIO(d.content))
                if pdf.is_encrypted and (not pdf.decrypt('') or not pdf.user_access_permissions & UserAccessPermissions.EXTRACT):
                    raise ValueError('Report requires password or restricts text extraction')
                records[url] = dict(title=title, url=url, publisher=publisher, raw_path=path,
                    downloaded_url=d.downloaded_url, collected_at=d.collected_at,
                    pages=len(pdf.pages), cover=pdf.pages[0].extract_text(),
                    first_pages='\n'.join(p.extract_text() or '' for p in pdf.pages[:3]),
                    embedded_title=pdf.metadata.title if pdf.metadata else None)
                print('reviewed', title, len(pdf.pages), flush=True)
            except Exception as exc:
                records[url] = dict(title=title, url=url, status='failed', error_type=type(exc).__name__, message=str(exc))
                if isinstance(exc, SourceAccessError):
                    blocked.add(publisher)
                print('failed', title, str(exc), flush=True)
            save_json(report, records)
    finally:
        for fetcher in fetchers.values():
            fetcher.close()


if __name__ == '__main__':
    main()
