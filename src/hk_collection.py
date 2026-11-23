"""Durable HK-only collection stages. Resumption never asserts legal completeness."""
import json
import time
import uuid
from hashlib import sha256
from urllib.parse import urlsplit

from collection_service import CollectionBusy, file_lock, save_json, collect_once
from virtual_asset_agent.common import utc_now
from research_publications import collect_research
from hk_discovery import discover_hk
from hk_stablecoin_data import selected_sources, export_corpus, audit_topic, corpus


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def fingerprint(root):
    paths = sorted((root / 'config').glob('*')) + sorted((root / 'src').rglob('*.py'))
    digest = sha256()
    for path in paths:
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def status(root):
    folder = root / 'data/ingestion/hk_stablecoins'
    state = read(folder / 'run_checkpoint.json', {'status': 'not_started'})
    busy = False
    try:
        with file_lock(root / 'data/ingestion/automation/run.lock'):
            pass
    except CollectionBusy:
        busy = True
    return dict(checkpoint=state, collection_lock_held=busy,
                effective_status='interrupted' if state['status'] == 'running' and not busy else state['status'],
                scheduler_settings=read(root / 'data/ingestion/automation/settings.json', {}),
                scheduler_last_run=read(root / 'data/ingestion/automation/state.json', {}),
                scheduler_process_liveness='unknown; settings alone do not prove a running worker',
                corpus=read(root / 'data/exports/hk_stablecoins/summary.json', {}))


def run(root, resume=False):
    folder = root / 'data/ingestion/hk_stablecoins'
    with file_lock(root / 'data/ingestion/automation/run.lock'):
        prior = read(folder / 'run_checkpoint.json', {})
        key = fingerprint(root)
        if resume:
            if not prior or prior.get('fingerprint') != key:
                raise ValueError('No matching checkpoint; run a fresh collection after configuration/code changes')
            age = time.time() - prior['started_epoch']
            if not 0 <= age < 24 * 3600:
                raise ValueError('Checkpoint is older than 24 hours; run a fresh collection')
            if prior.get('status') == 'success':
                # A no-op is not a fresh collection: retain all persisted timestamps.
                return dict(prior, resume_noop=True)
            state = prior
        else:
            state = dict(run_id=uuid.uuid4().hex, fingerprint=key, started_epoch=time.time(),
                         started_at=utc_now(), stages={}, results=[])
        state.update(status='running', resumed=resume)
        state.pop('finished_at', None)
        def persist():
            state['updated_at'] = utc_now()
            save_json(folder / 'run_checkpoint.json', state)
            save_json(folder / 'runs' / (state['run_id'] + '.json'), state)
        persist()
        actions = {
            'hkma': lambda: collect_once(root, root / 'data/ingestion/hkma.sqlite',
                                        include_supplementary=False, source_ids={'hkma'})['results'],
            'research': lambda: collect_research(root, selected_sources(root)),
            'discovery': lambda: discover_hk(root, {urlsplit(r['source_url']).hostname
                for n in ('hkma', 'research') for r in state['stages'].get(n, {}).get('output', [])
                if r.get('error_type') == 'SourceAccessError'}),
            'export': lambda: export_corpus(root),
            'topic_audit': lambda: audit_topic(root, {d['url'] for d in corpus(root)[0]}),
        }
        # If an upstream phase needs work, rebuild every dependent downstream phase.
        rerun = False
        for name, action in actions.items():
            old = state['stages'].get(name, {})
            rerun = rerun or old.get('status') != 'success'
            if not rerun:
                continue
            state['active_stage'] = name
            stage = dict(status='running', started_at=utc_now())
            state['stages'][name] = stage
            persist()
            try:
                value = action()
                failed = (any(r.get('status') == 'failed' for r in value) if isinstance(value, list)
                          else bool(value.get('missing_configured_urls')) or value.get('primary_database_present') is False)
                stage.update(status='partial_failure' if failed else 'success', output=value)
            except Exception as exc:
                stage.update(status='failed', error_type=type(exc).__name__, error=str(exc))
            stage['finished_at'] = utc_now()
            state['results'] = [r for n in ('hkma', 'research', 'discovery')
                                for r in state['stages'].get(n, {}).get('output', [])]
            save_json(folder / 'last_run.json', state['results'])
            persist()
        state.update(status='success' if all(s['status'] == 'success' for s in state['stages'].values())
                     else 'partial_failure', finished_at=utc_now(), active_stage=None)
        persist()
        return state
