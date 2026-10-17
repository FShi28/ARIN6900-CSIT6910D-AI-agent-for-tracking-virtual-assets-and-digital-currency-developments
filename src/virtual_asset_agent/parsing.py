"""Text-PDF parsing for the two verified cover layouts."""

import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .common import PipelineError


@dataclass(frozen=True)
class ParsedPDF:
    pages: list[str]
    title: str
    title_raw: str
    language_raw: str | None
    cover_date_raw: str | None
    cover_kind: str = 'guideline'


def parse_pdf(content):
    if not content.startswith(b'%PDF-'):
        raise PipelineError('Invalid PDF header')
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise PipelineError('Encrypted PDFs are unsupported')
        pages = [page.extract_text() or '' for page in reader.pages]
        language = reader.trailer['/Root'].get('/Lang')
    except (PyPdfError, KeyError, TypeError) as exc:
        raise PipelineError(f'PDF extraction failed: {type(exc).__name__}') from exc
    if not pages or any(len(page.strip()) < 20 for page in pages):
        raise PipelineError('PDF contains empty or non-text pages; OCR is not supported')
    if any('\x00' in page for page in pages):
        raise PipelineError('PDF extraction contains NUL characters')
    # Two verified layouts. A new layout must be reviewed and added with a fixture.
    title_match = re.search(r'(?im)^\s*(Guideline on[^\S\n]*\n[^\n]+)', pages[0])
    cover_kind = 'guideline'
    if not title_match:
        title_match = re.search(
            r'(?im)^[ \t]*(Legislative Proposal to Implement the[ \t]*\n'
            r'[ \t]*Regulatory Regime for Stablecoin Issuers in[ \t]*\n'
            r'[ \t]*Hong Kong\s+Consultation Conclusions)[ \t]*(?=\n|$)', pages[0])
        cover_kind = 'consultation_conclusions'
    if not title_match:
        raise PipelineError('Unsupported cover layout: cannot locate a reliable regulatory title')
    raw_title = title_match.group(1).strip()
    title = ' '.join(raw_title.split())
    if 'stablecoin' not in title.lower():
        raise PipelineError('PDF title is outside the stablecoin pilot')
    # Cover publication date only; never take unrelated body or PDF creation dates.
    months = 'January|February|March|April|May|June|July|August|September|October|November|December'
    date_match = re.search(rf'(?m)^\s*((?:\d{{1,2}} )?(?:{months}) \d{{4}})\s*$', pages[0])
    return ParsedPDF(pages, title, raw_title, str(language) if language else None,
                     date_match.group(1) if date_match else None, cover_kind)
