"""Conservative whitespace cleaning with physical-page character ranges."""

import re


def clean_pages(pages):
    parts, ranges = [], []
    offset = 0
    for number, raw in enumerate(pages, 1):
        # Preserve line order, clauses, amounts and page numbers; no summarization.
        lines = [re.sub(r'[^\S\n]+', ' ', line).strip() for line in raw.splitlines()]
        text = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
        if parts:
            offset += 2
        ranges.append({'page': number, 'start': offset, 'end': offset + len(text)})
        parts.append(text)
        offset += len(text)
    return '\n\n'.join(parts), ranges


def chunk_pages(text, ranges, extraction_id, max_chars):
    from .common import identity

    chunks = []
    for page in ranges:
        start = page['start']
        while start < page['end']:
            while start < page['end'] and text[start].isspace():
                start += 1
            if start == page['end']:
                break
            end = min(start + max_chars, page['end'])
            if end < page['end']:
                break_at = text.rfind('\n', start + max_chars // 2, end)
                if break_at < 0:
                    break_at = text.rfind(' ', start + max_chars // 2, end)
                if break_at > start:
                    end = break_at
            while end > start and text[end - 1].isspace():
                end -= 1
            ordinal = len(chunks)
            chunks.append({'chunk_id': identity('chunk', extraction_id, ordinal),
                           'extraction_id': extraction_id, 'ordinal': ordinal,
                           'text': text[start:end], 'char_start': start, 'char_end': end,
                           'page_start': page['page'], 'page_end': page['page'],
                           'section': None, 'is_table': None})
            start = end
    return chunks
