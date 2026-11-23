"""Check reviewed evidence locations without claiming exhaustive legal coverage."""
import json
import re
from collections import Counter

from collection_service import save_json
from virtual_asset_agent.common import sha256, utc_now


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()


def coverage_report(root, documents, chunks):
    path = root / 'config/hk_stablecoin_coverage.json'
    if not path.exists():
        return None
    config = json.loads(path.read_text(encoding='utf-8'))
    by_url = {d['url']: d for d in documents}
    hashes = {}
    rows = []
    for check in config['checks']:
        reference = config['sources'][check['source']]
        doc = by_url.get(reference['url'])
        row = dict(check, source_url=reference['url'], status='missing_document',
                   new_document_discovery=reference['new_document_discovery'],
                   existing_url_refresh='Every 24 hours only while the configured collection worker runs',
                   legal_completeness='not_established', evidence_chunk_ids=[])
        if doc:
            row.update(document_title=doc['title'], collected_at=doc.get('collected_at'),
                       published=doc.get('published'), content_sha256=doc['content_sha256'])
            if doc['raw_path'] not in hashes:
                raw_path = root / doc['raw_path']
                hashes[doc['raw_path']] = sha256(raw_path.read_bytes()) if raw_path.exists() else None
            if doc['authority'] != 'primary':
                row['status'] = 'not_primary_evidence'
            elif hashes[doc['raw_path']] != doc['content_sha256']:
                row['status'] = 'raw_evidence_invalid'
            elif doc['content_sha256'] != reference['reviewed_sha256']:
                row['status'] = 'source_changed_requires_review'
            else:
                candidates = [c for c in chunks if c['document_id'] == doc['document_id']
                    and (check['page_start'] is None or
                         c.get('page_start') is not None
                         and c['page_end'] >= check['page_start']
                         and c['page_start'] <= check['page_end'])]
                text = normalized('\n'.join(c['text'] for c in candidates))
                if normalized(check['anchor']) in text:
                    row['status'] = 'evidence_located'
                    row['evidence_chunk_ids'] = [c['chunk_id'] for c in candidates]
                else:
                    row['status'] = 'anchor_not_found'
        row['citation_url'] = reference['url'] + (f"#page={check['page_start']}" if check['page_start'] else '')
        rows.append(row)
    report = dict(generated_at=utc_now(), checklist_reviewed_on=config['reviewed_on'],
        purpose=config['purpose'], legal_completeness=False, checks=len(rows),
        by_status=dict(Counter(r['status'] for r in rows)), global_gaps=config['global_gaps'], rows=rows)
    folder = root / 'data/exports/hk_stablecoins'
    save_json(folder / 'coverage.json', report)
    lines = ['# 香港稳定币：六个重点的证据核对表', '',
        f"生成时间：{report['generated_at']}；核对清单审核日：{config['reviewed_on']}。", '',
        '**本表是资料覆盖核对，不是全部法律义务清单，也不是合规意见。**', '',
        f"共 {len(rows)} 个预先选定的核对项；定位到证据 {report['by_status'].get('evidence_located', 0)} 项。该数量不是法律完整率。", '',
        '页码为 PDF 阅读器的物理页码；例如 AML 指引正文印刷页码比 PDF 页码少一。网页使用标题／段落定位。', '',
        '| 重点 | 核对项 | 适用机构 | 原文、章节及位置 | 证据状态 |',
        '|---|---|---|---|---|']
    for row in rows:
        location = (f"PDF {row['page_start']}–{row['page_end']} 页" if row['page_start'] else '网页正文')
        label = f"{row.get('document_title', row['source'])} · {row['section']} · {location}"
        status = '已定位原文' if row['status'] == 'evidence_located' else row['status']
        lines.append(f"| {row['topic']} | {row['check']} | {row['applies_to']} | [{label}]({row['citation_url']}) | {status} |")
    lines += ['', '## 尚未解决的缺口', ''] + ['- ' + gap for gap in config['global_gaps']]
    lines += ['', '## 自动更新范围', '',
        '- 表内成功收录的文件均进入固定链接定时刷新；只有电脑联网、不休眠，且收集进程持续运行时才会执行。',
        '- HKMA 稳定币专题页支持新链接发现；该页面之外的 HKMA 通函归档及 SFC 通函归档尚未自动扫描。',
        '- 发现文件变化不等于已经核验其法律影响：原文哈希改变会将本表对应条目标为 source_changed_requires_review。',
        '- 抓取或解析失败保留旧版本。最后成功采集时间保存在 coverage.json，不表示此后没有新规定。',
        '- 条例／宪报仍缺原始全文；不得用咨询稿、新闻稿、监管解释或此表替代条例。', '']
    (folder / 'coverage.md').write_text('\n'.join(lines), encoding='utf-8')
    return report
