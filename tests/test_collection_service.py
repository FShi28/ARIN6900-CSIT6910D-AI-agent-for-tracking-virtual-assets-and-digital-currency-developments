"""Scheduler behavior uses temporary state, a fake clock and no live requests."""

import copy
import threading
from pathlib import Path

import pytest

import collection_service as service
from virtual_asset_agent.config import load_sources

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scheduled(tmp_path):
    now, runs = [100000.0], []

    def runner(root, db):
        runs.append((root, db))
        return {'status': 'success', 'counts': {'created': 1, 'reused': 0, 'failed': 0}}

    worker = service.CollectionService(tmp_path, runner, lambda: now[0])
    return worker, now, runs


def test_first_run_deadline_and_restart(scheduled):
    worker, now, runs = scheduled
    assert worker.tick()
    assert not worker.tick()
    restarted = service.CollectionService(worker.root, worker.runner, lambda: now[0])
    assert not restarted.tick()
    now[0] += 24 * 3600
    assert restarted.tick()
    assert len(runs) == 2
    assert restarted.snapshot()['state']['trigger'] == 'scheduled'


def test_pause_manual_request_and_interval(scheduled):
    worker, now, runs = scheduled
    worker.configure(False, 2)
    assert not worker.tick()
    assert worker.snapshot()['next_due'] is None
    worker.request_run()
    assert worker.tick()
    assert worker.snapshot()['state']['trigger'] == 'manual'
    assert not worker.tick()
    worker.configure(True, 2)
    now[0] += 7199
    assert not worker.tick()
    now[0] += 1
    assert worker.tick()
    assert len(runs) == 2


def test_failure_backoff_and_manual_recovery(scheduled):
    worker, now, runs = scheduled
    def failure(root, db):
        raise ValueError('Synthetic unavailable source')
    worker.runner = failure
    assert worker.tick()
    assert worker.snapshot()['state']['status'] == 'failed'
    assert worker.snapshot()['state']['error_type'] == 'ValueError'
    assert not worker.tick()
    worker.request_run()
    assert worker.tick()


def test_interrupted_run_is_recovered(scheduled):
    worker, now, runs = scheduled
    service.save_json(worker.state_path, {'status': 'running', 'handled_request_id': None})
    assert worker.tick()
    assert worker.snapshot()['state']['recovered_interrupted_run']


def test_overlapping_workers_do_not_duplicate_runs(scheduled):
    worker, now, runs = scheduled
    entered, release = threading.Event(), threading.Event()
    def slow(root, db):
        entered.set()
        assert release.wait(5)
        runs.append(1)
        return {'status': 'success'}
    worker.runner = slow
    thread = threading.Thread(target=worker.tick)
    thread.start()
    try:
        assert entered.wait(3)
        second = service.CollectionService(worker.root, slow, lambda: now[0])
        assert not second.tick()
    finally:
        release.set()
        thread.join(5)
    assert len(runs) == 1
    assert not second.tick()


def test_request_during_run_is_not_lost(scheduled):
    worker, now, runs = scheduled
    original = worker.runner
    def requesting(root, db):
        worker.request_run()
        return original(root, db)
    worker.runner = requesting
    assert worker.tick()
    worker.runner = original
    assert worker.tick()
    assert not worker.tick()


def test_worker_starts_once_and_stops(scheduled):
    worker, now, runs = scheduled
    worker.configure(False, 24)
    worker.start()
    thread = worker._thread
    assert worker.start()._thread is thread
    worker.stop()
    thread.join(3)
    assert not thread.is_alive()


@pytest.mark.parametrize('interval', [0, 169, True, 1.5])
def test_invalid_frequency_rejected(scheduled, interval):
    with pytest.raises(ValueError):
        scheduled[0].configure(True, interval)


def test_corrupt_settings_not_silently_reset(scheduled):
    worker, _, _ = scheduled
    service.save_json(worker.settings_path, {'enabled': True, 'interval_hours': 0})
    with pytest.raises(ValueError):
        worker.tick()
    assert not worker.state_path.exists()


@pytest.fixture
def cycle(tmp_path, monkeypatch):
    (tmp_path / 'db').mkdir()
    (tmp_path / 'db/schema.sql').write_bytes((ROOT / 'db/schema.sql').read_bytes())
    sources = copy.deepcopy(load_sources(ROOT / 'config/sources.yaml'))
    monkeypatch.setattr(service, 'load_sources', lambda path: sources)
    instances, targets = [], []
    class Client:
        def __init__(self, source, log):
            self.source = source
            self.closed = False
            instances.append(self)
        def get(self, url, expected_type):
            return (url, expected_type)
        def close(self):
            self.closed = True
    monkeypatch.setattr(service, 'Fetcher', Client)
    html = sources['hkma']['scope']['target_urls'][2]
    def batch(*args, **kwargs):
        client = kwargs['fetcher_factory'](None, None)
        assert client.get(html, 'text/html') == (html, 'text/html')
        client.close()
        assert not instances[0].closed
        return {'results': [{'source_url': html, 'status': 'reused'}],
                'remaining': 0, 'stopped_for_source_access': False}
    def ingest(*args, **kwargs):
        targets.append(kwargs['document_url'])
        return {'source_url': kwargs['document_url'], 'status': 'reused'}
    monkeypatch.setattr(service, 'ingest_discovered', batch)
    monkeypatch.setattr(service, 'ingest', ingest)
    return tmp_path, sources, instances, targets


def test_cycle_initializes_real_schema_and_checks_fixed_pdfs(cycle):
    root, sources, instances, targets = cycle
    result = service.collect_once(root, root / 'data/ingestion/hkma.sqlite')
    assert result['status'] == 'success'
    assert result['counts'] == {'created': 0, 'reused': 3, 'failed': 0}
    assert targets == sources['hkma']['scope']['target_urls'][:2]
    assert len(instances) == 1 and instances[0].closed  # MAS stays disabled.


@pytest.mark.parametrize('enabled', [True, False])
def test_cycle_routes_discovery_and_export_only_when_supplementary_enabled(cycle, monkeypatch, enabled):
    import hk_discovery
    import hk_stablecoin_data
    root, _, _, _ = cycle
    (root / 'config').mkdir()
    (root / 'config/hk_discovery.json').write_text('[]')
    calls = []
    def discover(path, blocked):
        calls.append(('discover', path, blocked))
        return [{'source_url': 'https://example.test/new.pdf', 'status': 'created'}]
    monkeypatch.setattr(hk_discovery, 'discover_hk', discover)
    monkeypatch.setattr(hk_stablecoin_data, 'export_corpus', lambda path: calls.append(('export', path)))
    result = service.collect_once(root, root / 'data/ingestion/hkma.sqlite', include_supplementary=enabled)
    assert [c[0] for c in calls] == (['discover', 'export'] if enabled else [])
    assert result['counts']['created'] == int(enabled)


def test_access_denial_stops_remaining_targets(cycle, monkeypatch):
    root, _, instances, targets = cycle
    def denied(*args, **kwargs):
        raise service.SourceAccessError('HTTP 429')
    monkeypatch.setattr(service, 'ingest_discovered', denied)
    result = service.collect_once(root, root / 'data/ingestion/hkma.sqlite')
    assert result['status'] == 'partial_failure'
    assert result['stopped_for_source_access']
    assert not targets and instances[0].closed


def test_document_failure_keeps_other_targets(cycle, monkeypatch):
    root, sources, instances, targets = cycle
    def one_failure(*args, **kwargs):
        url = kwargs['document_url']
        targets.append(url)
        if url == sources['hkma']['scope']['target_urls'][0]:
            raise ValueError('Synthetic parse failure')
        return {'source_url': url, 'status': 'reused'}
    monkeypatch.setattr(service, 'ingest', one_failure)
    result = service.collect_once(root, root / 'data/ingestion/hkma.sqlite')
    assert result['counts'] == {'created': 0, 'reused': 2, 'failed': 1}
    assert len(targets) == 2
