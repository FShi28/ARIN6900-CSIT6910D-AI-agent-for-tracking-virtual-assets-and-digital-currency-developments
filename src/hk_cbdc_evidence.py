"""Reviewed project claims and evidence availability, never a legal-completeness score."""
import json
import re

from collection_service import save_json
from virtual_asset_agent.common import utc_now


def evidence_report(root, documents, chunks):
    path = root / 'config/hk_cbdc_evidence.json'
    if not path.exists():
        return dict(status='not_configured', claims=[])
    config = json.loads(path.read_text(encoding='utf-8'))
    by_url = {d['url']: d for d in documents}
    result = []
    for claim in config:
        d = by_url.get(claim['source_url'])
        selected = [c for c in chunks if d and c['document_id'] == d['document_id']]
        joined = ' '.join(re.sub(r'\s+', ' ', c['text']) for c in selected)
        anchor = re.sub(r'\s+', ' ', claim['anchor'])
        status = ('source_missing' if d is None else 'source_changed_needs_review'
                  if d['content_sha256'] != claim['reviewed_sha256'] else
                  'anchor_missing' if anchor not in joined else 'evidence_validated')
        # A claim may cross chunk boundaries; preserve those nearby chunks too.
        matching = [c['chunk_id'] for c in selected if anchor in re.sub(r'\s+', ' ', c['text'])]
        if status == 'evidence_validated' and not matching:
            matching = [c['chunk_id'] for c in selected]
        result.append(dict(claim, status=status, evidence_chunk_ids=matching,
                           source_published=d['published'] if d else None,
                           source_collected_at=d['collected_at'] if d else None))
    report = dict(checked_at=utc_now(), claims=result,
        validated=sum(r['status'] == 'evidence_validated' for r in result), total=len(result),
        legal_completeness=False, note='Manually selected source-grounded historical claims. Hash changes require review; these are not automatically current project states.')
    save_json(root / 'data/exports/hk_cbdc/evidence.json', report)
    return report
