"""Reviewed source statements, never inferred current-law classifications."""
import json
from collections import Counter

from collection_service import save_json
from hk_coverage import normalized
from virtual_asset_agent.common import sha256, utc_now


def relationship_report(root, documents, chunks):
    path = root / 'config/hk_stablecoin_relationships.json'
    if not path.exists():
        return []
    by_url = {d['url']: d for d in documents}
    rows = []
    for review in json.loads(path.read_text(encoding='utf-8')):
        row = dict(review, status='source_missing', evidence_chunk_ids=[])
        source, target = by_url.get(review['source_url']), by_url.get(review['target_url'])
        if source:
            raw = root / source['raw_path']
            if source['authority'] != 'primary':
                row['status'] = 'not_primary_evidence'
            elif not raw.exists() or sha256(raw.read_bytes()) != source['content_sha256']:
                row['status'] = 'raw_evidence_invalid'
            elif source['content_sha256'] != review['source_sha256']:
                row['status'] = 'source_changed_requires_review'
            else:
                matches = [c for c in chunks if c['document_id'] == source['document_id']
                           and normalized(review['anchor']) in normalized(c['text'])]
                row['evidence_chunk_ids'] = [c['chunk_id'] for c in matches]
                row['status'] = 'anchor_not_found' if not matches else 'target_not_collected'
                if matches and target:
                    target_raw = root / target['raw_path']
                    if not target_raw.exists() or sha256(target_raw.read_bytes()) != target['content_sha256']:
                        row['status'] = 'target_raw_invalid'
                    elif target['content_sha256'] != review.get('target_sha256'):
                        row['status'] = 'target_changed_requires_review'
                    else:
                        row['status'] = 'evidence_validated'
        rows.append(row)
    folder = root / 'data/exports/hk_stablecoins'
    save_json(folder / 'relationships.json', dict(generated_at=utc_now(), legal_completeness=False,
        purpose='Reviewed explicit document relationships; no automatic current-law determination',
        by_status=dict(Counter(r['status'] for r in rows)), rows=rows))
    for doc in documents:
        doc['relationship_evidence'] = [dict(id=r['id'], relation=r['relation'], status=r['status'],
            source_url=r['source_url'], target_url=r['target_url'], applies_to=r['applies_to'])
            for r in rows if doc['url'] in (r['source_url'], r['target_url'])]
    for chunk in chunks:
        chunk['relationship_evidence_ids'] = [r['id'] for r in rows if chunk['chunk_id'] in r['evidence_chunk_ids']]
    return rows
