"""Validate the local CBDC data handoff; not chatbot or legal completeness."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from collection_service import file_lock, save_json
from hk_cbdc_data import corpus, export_corpus
from hk_cbdc_questions import check_questions
from virtual_asset_agent.common import utc_now


def validate_handoff(root):
    summary = export_corpus(root)
    questions = check_questions(root)
    docs, _ = corpus(root)
    evidence = json.loads((root / 'data/exports/hk_cbdc/evidence.json').read_text(encoding='utf-8'))
    claims = {c['id']: c for c in evidence['claims']}
    profiles = json.loads((root / 'config/hk_cbdc_projects.json').read_text(encoding='utf-8'))
    rows = []
    for project in profiles:
        selected = [d for d in docs if project['id'] in d['projects']]
        required = project['evidence_ids']
        supported = bool(required) and all(claims.get(i, {}).get('status') == 'evidence_validated' for i in required)
        rows.append(dict(project=project['id'], documents=len(selected),
            primary_documents=sum(d['authority'] == 'primary' for d in selected),
            pdf_documents=sum(d['format'] == 'pdf' for d in selected),
            reviewed_evidence_supported=supported))
    static = json.loads((root / 'config/hk_cbdc_sources.json').read_text(encoding='utf-8'))
    missing_static = sorted({d['url'] for d in docs} - {s['url'] for s in static})
    checkpoint_path = root / 'data/ingestion/hk_cbdc/run_checkpoint.json'
    refresh = json.loads(checkpoint_path.read_text(encoding='utf-8')) if checkpoint_path.exists() else {}
    checks = dict(integrity=questions['corpus_integrity'] == 'passed',
        all_reviewed_claims=evidence['total'] > 0 and evidence['validated'] == evidence['total'],
        all_project_profiles=bool(rows) and all(r['primary_documents'] and r['reviewed_evidence_supported'] for r in rows),
        questions=questions['supported_questions'] > 0 and questions['unresolved'] == 0,
        source_catalogue_portable=not missing_static and not summary['missing_configured_urls'],
        latest_complete_cycle=refresh.get('status') == 'success' and refresh.get('phase') == 'complete')
    report = dict(checked_at=utc_now(), status='passed' if all(checks.values()) else 'needs_review',
        data_status='passed' if all(v for k, v in checks.items() if k != 'latest_complete_cycle') else 'needs_review',
        refresh_status=refresh.get('status', 'not_run'),
        checks=checks, summary=summary, projects=rows, missing_static_urls=missing_static,
        last_cycle_started_at=refresh.get('started_at'), last_cycle_finished_at=refresh.get('finished_at'),
        limitations=['Data handoff check, not chatbot accuracy or exhaustive legal coverage.',
            'A successful saved cycle does not prove scheduler liveness or current freshness.',
            'Phase 1 full report and IMF research access gaps remain documented.',
            'Source catalogue is portable; local full texts are not bundled with Git.',
            'New PDF links require review. Discovery remains bounded to configured entry points.'])
    save_json(root / 'data/exports/hk_cbdc/handoff_validation.json', report)
    return report


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    with file_lock(root / 'data/ingestion/automation/run.lock'):
        report = validate_handoff(root)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    raise SystemExit(int(report['status'] != 'passed'))
