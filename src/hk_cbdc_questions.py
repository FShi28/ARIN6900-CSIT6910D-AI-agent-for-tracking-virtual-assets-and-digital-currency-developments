"""Evidence availability acceptance checks, not an LLM or retrieval accuracy score."""
import json
from collection_service import save_json
from virtual_asset_agent.common import utc_now
from hk_cbdc_data import corpus, validate
from hk_cbdc_evidence import evidence_report


def check_questions(root):
    docs, chunks = corpus(root)
    integrity = validate(root, docs, chunks)
    evidence = evidence_report(root, docs, chunks)
    claims = {c['id']: c for c in evidence['claims']}
    by_chunk = {c['chunk_id']: c for c in chunks}
    cases = json.loads((root / 'config/hk_cbdc_questions.json').read_text(encoding='utf-8'))
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate question ID')
    rows = []
    for case in cases:
        if case['expected'] not in ('supported', 'insufficient') or not case['limits']:
            raise ValueError('Question needs an explicit scope and evidence expectation')
        if case['expected'] == 'insufficient':
            if case['evidence_ids']:
                raise ValueError('Insufficient cases must not claim supporting evidence')
            rows.append(dict(case, status='documented_gap', citations=[]))
            continue
        selected = [claims.get(key) for key in case['evidence_ids']]
        ok = bool(selected) and integrity['status'] == 'passed' and all(
            c and c['status'] == 'evidence_validated' and c['evidence_chunk_ids'] for c in selected)
        citations = [dict(statement=c['statement'], as_of=c['as_of'],
            citation=by_chunk[c['evidence_chunk_ids'][0]]['citation'])
            for c in selected if c and c['status'] == 'evidence_validated' and c['evidence_chunk_ids']]
        rows.append(dict(case, status='evidence_available' if ok else 'needs_review', citations=citations))
    report = dict(checked_at=utc_now(), corpus_integrity=integrity['status'], cases=rows,
        supported_questions=sum(c['status'] == 'evidence_available' for c in rows),
        documented_gaps=sum(c['status'] == 'documented_gap' for c in rows),
        unresolved=sum(c['status'] == 'needs_review' for c in rows),
        scope='Checks reviewed source evidence availability. Does not test chatbot answers, retrieval ranking, Chinese semantic search or legal completeness.')
    folder = root / 'data/exports/hk_cbdc'
    save_json(folder / 'question_acceptance.json', report)
    lines = ['# CBDC 问题与证据验收', '', '这是数据证据检查，不是 chatbot 准确率评测。', '']
    for row in rows:
        lines.extend([f"## {row['question']}", '', f"状态：{row['status']}。{row['limits']}", ''])
        for c in row['citations']:
            cite = c['citation']
            lines.append(f"- {c['statement']}（{c['as_of']}）[原文]({cite['url']})")
        lines.append('')
    (folder / 'question_acceptance.md').write_text('\n'.join(lines), encoding='utf-8')
    return report
