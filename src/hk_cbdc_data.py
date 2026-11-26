"""Independent, citable Hong Kong CBDC corpus; shared immutable publication store."""
import json
import re
from collections import Counter
from urllib.parse import urlsplit

from collection_service import save_json
from research_publications import load_publications, sources, snapshot_path
from virtual_asset_agent.common import identity, sha256, utc_now


def apply_date_reviews(root, reviews):
    """Persist reviewed dates without re-extracting or redating a downloaded PDF."""
    from datetime import datetime
    if len({r['url'] for r in reviews}) != len(reviews):
        raise ValueError('Duplicate document URL in date reviews')
    documents, chunks = corpus(root)
    by_url = {d['url']: d for d in documents}
    prepared = []
    for review in reviews:
        doc = by_url[review['url']]
        reference = by_url[review['source_url']]
        datetime.strptime(review['published'], '%Y-%m-%d' if review['precision'] == 'day' else '%Y-%m')
        text = ' '.join(re.sub(r'\s+', ' ', c['text']) for c in chunks if c['document_id'] == reference['document_id'])
        if re.sub(r'\s+', ' ', review['anchor']) not in text:
            raise ValueError('Date review anchor missing')
        for item in (doc, reference):
            if sha256((root / item['raw_path']).read_bytes()) != item['content_sha256']:
                raise ValueError('Date review raw hash mismatch')
        proof = dict(source_url=reference['url'], reviewed_sha256=reference['content_sha256'],
                     reviewed_raw_path=reference['raw_path'],
                     document_sha256=doc['content_sha256'], anchor=review['anchor'])
        prepared.append((doc['url'], dict(published=review['published'], published_precision=review['precision'],
                                         publication_date_provenance=proof)))
    # All evidence is checked before any catalogue/snapshot mutation.
    for filename in ('config/hk_cbdc_sources.json', 'data/ingestion/hk_cbdc/discovered_sources.json'):
        path = root / filename
        if not path.exists():
            continue
        catalog = json.loads(path.read_text(encoding='utf-8'))
        for source in catalog:
            for url, metadata in prepared:
                if source['url'] == url:
                    source.update(metadata)
        save_json(path, catalog)
    for url, metadata in prepared:
        path = snapshot_path(root, url)
        record = json.loads(path.read_text(encoding='utf-8'))
        collected_at = record.pop('collected_at')
        record.update(metadata)
        version = identity(url, json.dumps(record, sort_keys=True, ensure_ascii=False))
        version_path = root / 'data/ingestion/research_versions' / (version + '.json')
        if not version_path.exists():
            save_json(version_path, dict(record, collected_at=collected_at))
        save_json(path, dict(record, collected_at=collected_at))
    return len(prepared)


def selected_sources(root):
    return [s for s in sources(root) if s.get('collection') == 'hk_cbdc']


def corpus(root):
    documents, chunks = [], []
    selected = {s['url'] for s in selected_sources(root)}
    for pub in load_publications(root):
        if pub['url'] not in selected or pub.get('format') == 'source_note':
            continue
        doc = {k: v for k, v in pub.items() if k != 'chunks'}
        doc.update(document_id=identity(pub['url']), chunk_count=len(pub['chunks']))
        doc.setdefault('format', 'pdf')
        documents.append(doc)
        for c in pub['chunks']:
            page = c['page_start']
            chunks.append(dict(c, document_id=doc['document_id'], topic='CBDC', jurisdiction='Hong Kong',
                projects=doc['projects'], authority=doc['authority'], published=doc['published'],
                project_stage=doc.get('project_stage', 'not_assessed'), legal_status='not_assessed',
                citation=dict(title=doc['title'], source_name=doc['publisher'], source_url=doc['url'],
                    url=doc['url'] + (f'#page={page}' if page else ''), page=page)))
    if len({d['url'] for d in documents}) != len(documents):
        raise ValueError('Duplicate CBDC URL')
    return documents, chunks


def validate(root, documents, chunks):
    errors = []
    by_id = {d['document_id']: d for d in documents}
    for d in documents:
        path = root / d['raw_path']
        if not path.exists() or sha256(path.read_bytes()) != d['content_sha256']:
            errors.append(dict(url=d['url'], reason='Raw source missing or hash mismatch'))
        # Manually reviewed historical HKMA speeches may discuss CBDCs without
        # naming a configured project. Keep projects empty rather than inventing
        # a project mention; automatic discovery retains its stricter rule.
        context = d.get('context_scope_review', {})
        text = ' '.join(re.sub(r'\s+', ' ', c['text']) for c in chunks if c['document_id'] == d['document_id'])
        anchors = context.get('anchors', [])
        reviewed_context = (d.get('publisher') == 'HKMA' and d.get('authority') == 'primary'
            and urlsplit(d['url']).hostname == 'www.hkma.gov.hk'
            and d.get('kind') == 'Speech' and d.get('format') == 'html'
            and context.get('scope') == 'hong_kong_cbdc_history'
            and bool(context.get('reason')) and len(anchors) >= 2
            and all(isinstance(a, str) and a.strip() and re.sub(r'\s+', ' ', a) in text for a in anchors)
            and bool(re.search(r'\bCBDCs?\b|central bank digital currenc', text, re.I)))
        if (not d.get('projects') and not reviewed_context) or not d.get('title') or not d.get('authority'):
            errors.append(dict(url=d['url'], reason='Required provenance/classification missing'))
        if d['chunk_count'] != sum(c['document_id'] == d['document_id'] for c in chunks):
            errors.append(dict(url=d['url'], reason='Chunk count mismatch'))
        proof = d.get('publication_date_provenance')
        if proof:
            reference = next((p for p in documents if p['url'] == proof['source_url']), None)
            text = ' '.join(re.sub(r'\s+', ' ', c['text']) for c in chunks
                            if reference and c['document_id'] == reference['document_id'])
            archive = root / proof.get('reviewed_raw_path',
                f"data/raw/{proof['reviewed_sha256']}.{reference['format'] if reference else 'html'}")
            # Dynamic navigation/nonce changes must not invalidate an unchanged
            # date statement. Preserve the reviewed original and recheck the
            # statement in the latest source text as well as the target PDF hash.
            if (d['content_sha256'] != proof.get('document_sha256')
                    or not reference or not archive.exists()
                    or sha256(archive.read_bytes()) != proof['reviewed_sha256']
                    or re.sub(r'\s+', ' ', proof['anchor']) not in text):
                errors.append(dict(url=d['url'], reason='Publication-date provenance changed; review required'))
    for c in chunks:
        d = by_id.get(c['document_id'])
        if not d or not c['text'].strip() or c['citation']['source_url'] != d['url']:
            errors.append(dict(chunk_id=c['chunk_id'], reason='Broken citation or empty text'))
        if d and d['format'] == 'html' and c['citation']['page'] is not None:
            errors.append(dict(chunk_id=c['chunk_id'], reason='Fabricated HTML page number'))
    if len({c['chunk_id'] for c in chunks}) != len(chunks):
        errors.append(dict(reason='Duplicate chunk ID'))
    return dict(checked_at=utc_now(), status='failed' if errors or not documents else 'passed',
                documents=len(documents), chunks=len(chunks), errors=errors,
                scope='Raw hashes, required metadata, counts and citations; not legal completeness.')


def export_corpus(root):
    docs, chunks = corpus(root)
    folder = root / 'data/exports/hk_cbdc'
    folder.mkdir(parents=True, exist_ok=True)
    validation = validate(root, docs, chunks)
    save_json(folder / 'validation.json', validation)
    if validation['status'] == 'failed':
        raise ValueError('CBDC export validation failed; see validation.json')
    from hk_cbdc_evidence import evidence_report
    evidence = evidence_report(root, docs, chunks)
    projects_path = root / 'config/hk_cbdc_projects.json'
    if projects_path.exists():
        projects = json.loads(projects_path.read_text(encoding='utf-8'))
        for project in projects:
            project['stage_evidence'] = [claim for claim in evidence['claims'] if claim['id'] in project['evidence_ids']]
        save_json(folder / 'projects.json', projects)
    for d in docs:
        d['reviewed_evidence_ids'] = [c['id'] for c in evidence['claims']
            if c['source_url'] == d['url'] and c['status'] == 'evidence_validated']
    for name, records in [('documents', docs), ('chunks', chunks)]:
        path = folder / (name + '.jsonl')
        temp = path.with_suffix('.jsonl.tmp')
        temp.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
        temp.replace(path)
    summary = dict(exported_at=utc_now(), documents=len(docs), chunks=len(chunks),
        by_publisher=dict(Counter(d['publisher'] for d in docs)),
        by_format=dict(Counter(d['format'] for d in docs)),
        by_authority=dict(Counter(d['authority'] for d in docs)),
        by_project_mentions=dict(Counter(p for d in docs for p in d['projects'])),
        reviewed_context_documents=sum(bool(d.get('context_scope_review')) for d in docs),
        missing_configured_urls=sorted({s['url'] for s in selected_sources(root)} - {d['url'] for d in docs}),
        date_range=sorted({d['published'] for d in docs if d['published']}),
        fixed_url_refresh_documents=len(docs),
        evidence_validated=evidence.get('validated', 0), evidence_total=evidence.get('total', 0),
        limitations=['Selected Hong Kong CBDC and cross-border project corpus, not exhaustive.',
                    'Project and region counts are overlapping mentions, not unique project membership.',
                    'Historical project stage claims require dated evidence; pilot is not issuance.',
                    'New PDF links queue for review; only supported in-scope HTML articles auto-ingest.',
                    'The 24-hour app worker must remain running; configuration does not prove liveness.'])
    save_json(folder / 'summary.json', summary)
    lines = ['# 香港 CBDC 与香港参与的跨境项目：资料清单', '',
             f"{len(docs)} 份文件，{len(chunks)} 个引用片段。地区是正文提及，不代表项目参与方。", '',
             '| 发布方 | 类型 | 标题／原文 | 发布日期 | 项目提及 |', '|---|---|---|---|---|']
    for d in sorted(docs, key=lambda d: (d['published'], d['title'])):
        title = d['title'].replace('|', '/')
        project_label = ', '.join(d['projects']) or ('CBDC 历史背景（未命名项目）' if d.get('context_scope_review') else '')
        lines.append(f"| {d['publisher']} | {d['format']} / {d['kind']} | [{title}]({d['url']}) | {d['published'] or '未核实'} | {project_label} |")
    (folder / 'inventory.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary
