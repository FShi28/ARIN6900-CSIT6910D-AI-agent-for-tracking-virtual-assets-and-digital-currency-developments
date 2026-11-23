import json
from contextlib import nullcontext

import pytest

import hk_collection as hk
import collection_service as generic


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    calls = []
    def base(*args, **kwargs):
        assert kwargs == {'include_supplementary': False, 'source_ids': {'hkma'}}
        calls.append('hkma')
        return {'results': [{'source_url':'https://www.hkma.gov.hk/a', 'status':'reused'}]}
    monkeypatch.setattr(hk, 'collect_once', base)
    monkeypatch.setattr(hk, 'selected_sources', lambda root: [])
    monkeypatch.setattr(hk, 'collect_research', lambda *a: calls.append('research') or [])
    monkeypatch.setattr(hk, 'discover_hk', lambda *a: calls.append('discovery') or [])
    monkeypatch.setattr(hk, 'export_corpus', lambda *a: calls.append('export') or
                        {'documents':1, 'missing_configured_urls':[], 'primary_database_present':True})
    monkeypatch.setattr(hk, 'corpus', lambda *a: ([], []))
    monkeypatch.setattr(hk, 'audit_topic', lambda *a: calls.append('audit') or {'links':[]})
    return tmp_path, calls


def test_interrupted_phase_resumes_without_repeating_successful_phase(pipeline, monkeypatch):
    root, calls = pipeline
    def crash(*a):
        raise KeyboardInterrupt()
    monkeypatch.setattr(hk, 'collect_research', crash)
    with pytest.raises(KeyboardInterrupt):
        hk.run(root)
    assert hk.status(root)['effective_status'] == 'interrupted'
    monkeypatch.setattr(hk, 'collect_research', lambda *a: calls.append('research') or [])
    state = hk.run(root, resume=True)
    assert state['status'] == 'success'
    assert calls == ['hkma', 'research', 'discovery', 'export', 'audit']
    assert (root / 'data/ingestion/hk_stablecoins/runs' / (state['run_id']+'.json')).exists()
    hk.run(root, resume=True)
    assert len(calls) == 5


def test_failed_upstream_stage_rebuilds_downstream(pipeline, monkeypatch):
    root, calls = pipeline
    monkeypatch.setattr(hk, 'collect_research', lambda *a: [dict(source_url='https://source.test/a',status='failed')])
    first = hk.run(root)
    assert first['status'] == 'partial_failure'
    calls.clear()
    monkeypatch.setattr(hk, 'collect_research', lambda *a: calls.append('research') or [])
    assert hk.run(root, resume=True)['status'] == 'success'
    assert calls == ['research','discovery','export','audit']


def test_resume_rejects_changed_configuration(pipeline):
    root, calls = pipeline
    hk.run(root)
    (root/'config').mkdir()
    (root/'config/hk_discovery.json').write_text('[]')
    with pytest.raises(ValueError, match='matching'):
        hk.run(root, resume=True)


def test_resume_rejects_stale_checkpoint(pipeline, monkeypatch):
    root, _ = pipeline
    state = hk.run(root)
    monkeypatch.setattr(hk.time, 'time', lambda: state['started_epoch'] + 86401)
    with pytest.raises(ValueError, match='24 hours'):
        hk.run(root, resume=True)


def test_successful_resume_does_not_rewrite_freshness(pipeline):
    root, calls = pipeline
    hk.run(root)
    path = root/'data/ingestion/hk_stablecoins/run_checkpoint.json'
    before = path.read_bytes()
    result = hk.run(root, resume=True)
    assert result['resume_noop'] is True
    assert path.read_bytes() == before
    assert len(calls) == 5


def test_overlapping_writer_is_rejected(pipeline):
    root, calls = pipeline
    with hk.file_lock(root/'data/ingestion/automation/run.lock'):
        assert hk.status(root)['collection_lock_held']
        with pytest.raises(hk.CollectionBusy):
            hk.run(root)
    assert not calls


def test_source_filter_skips_even_enabled_other_jurisdiction(tmp_path, monkeypatch):
    db = tmp_path/'test.sqlite'; db.touch()
    monkeypatch.setattr(generic, 'Reader', lambda *a: nullcontext())
    monkeypatch.setattr(generic, 'load_sources', lambda *a: {'mas': {'enabled':True}})
    result = generic.collect_once(tmp_path, db, include_supplementary=False, source_ids={'hkma'})
    assert result['results'] == []
