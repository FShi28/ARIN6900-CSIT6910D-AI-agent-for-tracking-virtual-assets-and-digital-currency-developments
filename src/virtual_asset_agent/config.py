"""Load and validate explicit source configuration."""

from datetime import date, datetime

import yaml

from .common import PipelineError, allowed_url


def load_sources(path):
    with open(path, encoding='utf-8') as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not isinstance(data.get('sources'), list):
        raise PipelineError('Configuration requires a sources list')
    sources = {}
    for source in data['sources']:
        if not isinstance(source, dict):
            raise PipelineError('Each source must be a mapping')
        required = ('source_id', 'source_name', 'jurisdiction', 'regulator', 'source_type', 'enabled')
        if any(key not in source for key in required):
            raise PipelineError('Missing required source configuration')
        if source['source_id'] in sources or not isinstance(source['source_id'], str):
            raise PipelineError('Source identifiers must be unique strings')
        pair = (source['jurisdiction'], source['regulator'])
        if pair not in (('Hong Kong', 'HKMA'), ('Singapore', 'MAS')):
            raise PipelineError('Unsupported jurisdiction/regulator pair')
        if source['source_type'] != 'primary_regulator' or type(source['enabled']) is not bool:
            raise PipelineError('Invalid source type or enabled flag')
        if source['enabled']:
            validate_enabled(source)
        sources[source['source_id']] = source
    return sources


def validate_enabled(source):
    try:
        if source['collector'] != 'hkma' or source['regulator'] != 'HKMA':
            raise PipelineError('Only the HKMA collector is implemented')
        scope, http, processing = source['scope'], source['http'], source['processing']
        if scope['allowed_hosts'] != ['www.hkma.gov.hk']:
            raise PipelineError('HKMA pilot must use the verified official host')
        allowed_url(source['base_url'], scope['allowed_hosts'])
        allowed_url(source['discovery_url'], scope['allowed_hosts'])
        if not source.get('verified_at'):
            raise PipelineError('Enabled source requires a verification timestamp')
        datetime.strptime(source['verified_at'], '%Y-%m-%dT%H:%M:%SZ')
        date.fromisoformat(scope['published_from'])
        if (type(scope['max_documents']) is not int or not 1 <= scope['max_documents'] <= 3
                or not isinstance(scope['target_urls'], list)
                or not 1 <= len(scope['target_urls']) <= scope['max_documents']):
            raise PipelineError('This pilot allows up to three approved document URLs')
        targets = [allowed_url(url, scope['allowed_hosts']) for url in scope['target_urls']]
        if len(set(targets)) != len(targets):
            raise PipelineError('Approved document URLs must be unique after normalization')
        discovery = source.get('discovery', {})
        if discovery:
            if (type(discovery['enabled']) is not bool
                    or discovery['rule'] != 'hkma_stablecoin_press_releases_v1'
                    or type(discovery['max_candidates']) is not int
                    or not 1 <= discovery['max_candidates'] <= 20
                    or type(discovery['max_batch']) is not int
                    or not 1 <= discovery['max_batch'] <= min(10, discovery['max_candidates'])):
                raise PipelineError('Invalid bounded discovery configuration')
        if not isinstance(http['user_agent'], str) or not http['user_agent'].strip():
            raise PipelineError('HTTP User-Agent is required')
        for key, low, high in [('timeout_seconds', 1, 60), ('max_retries', 0, 3),
                               ('min_interval_seconds', 1, 60), ('max_redirects', 0, 5),
                               ('max_bytes', 1024, 20 * 1024 * 1024)]:
            value = http[key]
            if type(value) not in (int, float) or not low <= value <= high:
                raise PipelineError(f'Invalid HTTP setting: {key}')
        for key in ('max_retries', 'max_redirects', 'max_bytes'):
            if type(http[key]) is not int:
                raise PipelineError(f'HTTP {key} must be an integer')
        if type(http['trust_env']) is not bool:
            raise PipelineError('trust_env must be boolean')
        if (processing['parser'] != 'hkma_regulatory_pdf_html_v3'
                or processing['cleaner'] != 'whitespace_preserving_v1'
                or processing['asset_rule'] != 'stablecoin_word_v1'
                or type(processing['chunk_max_chars']) is not int
                or not 200 <= processing['chunk_max_chars'] <= 4000):
            raise PipelineError('Unsupported processing configuration')
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(f'Invalid enabled source configuration: {exc}') from exc
