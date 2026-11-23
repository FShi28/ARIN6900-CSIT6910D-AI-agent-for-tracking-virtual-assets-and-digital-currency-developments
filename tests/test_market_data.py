"""Synthetic API fixtures; no live endpoint is contacted by these tests."""

import hashlib
import json

import pytest
import requests

from market_data import fetch, normalize, source_snapshot

STABLE = {'id': 'defillama_stablecoins', 'provider': 'DefiLlama', 'url': 'https://example.invalid/stablecoins', 'trust_env': False}
BTC = {'id': 'coingecko_bitcoin', 'provider': 'CoinGecko', 'url': 'https://example.invalid/bitcoin', 'trust_env': True}
RWA = {'id': 'defillama_rwa', 'provider': 'DefiLlama', 'url': 'https://example.invalid/protocols', 'trust_env': False}
PAYLOAD = {'peggedAssets': [
    {'id': 'test-usd', 'symbol': 'SYNUSD', 'pegType': 'peggedUSD', 'circulating': {'peggedUSD': 100}, 'price': .98},
    {'id': 'test-eur', 'symbol': 'SYNEUR', 'pegType': 'peggedEUR', 'circulating': {'peggedEUR': 200}, 'price': 1.1}]}


def test_stablecoins_keep_units_and_provenance_without_non_usd_pegs():
    rows = normalize(PAYLOAD, STABLE)
    assert len(rows) == 2
    assert rows[0]['value'] == 100 and rows[0]['unit'] == 'USD at peg'
    assert rows[0]['observed_at'] is None
    assert rows[0]['json_pointer'] == '/peggedAssets/0/circulating/peggedUSD'
    assert rows[1]['metric'] == 'price' and rows[1]['value'] == .98
    assert not any(r['metric'] == 'market_cap' for r in rows)


def test_bitcoin_and_rwa_are_distinct_metrics():
    rows = normalize([{'id': 'bitcoin', 'market_cap': 200, 'current_price': 20, 'total_volume': None,
                       'last_updated': '2026-10-01T12:00:00Z'}], BTC)
    assert [r['metric'] for r in rows] == ['market_cap', 'price']
    assert rows[0]['observed_at'] == '2026-10-01T12:00:00Z'
    rows = normalize([{'id': 'x', 'name': 'Synthetic RWA', 'category': 'RWA', 'tvl': 50},
                      {'id': 'y', 'name': 'Other', 'category': 'Dexes', 'tvl': 100}], RWA)
    assert len(rows) == 1 and rows[0]['metric'] == 'protocol_tvl'
    assert rows[0]['instrument'] == 'Synthetic RWA'


@pytest.mark.parametrize('value', [None, {}, [], {'peggedAssets': []}, {'peggedAssets': [None]}])
def test_bad_stablecoin_payload_is_rejected(value):
    with pytest.raises(ValueError):
        normalize(value, STABLE)


@pytest.mark.parametrize('value', [None, -1, float('nan'), float('inf'), True, '100'])
def test_invalid_values_never_become_zero(value):
    with pytest.raises(ValueError):
        normalize([{'id': 'bitcoin', 'market_cap': value}], BTC)


def test_duplicate_identity_rejected():
    with pytest.raises(ValueError, match='duplicate'):
        normalize({'peggedAssets': [PAYLOAD['peggedAssets'][0]] * 2}, STABLE)


def test_cached_response_and_stale_fallback_are_auditable(tmp_path):
    calls = []
    raw = json.dumps(PAYLOAD).encode()
    def fetcher(source):
        calls.append(source)
        return raw
    first = source_snapshot(tmp_path, STABLE, fetcher=fetcher, now=1000)
    second = source_snapshot(tmp_path, STABLE, fetcher=fetcher, now=1001)
    assert first == second and len(calls) == 1
    row = first['rows'][0]
    assert (tmp_path / row['raw_path']).read_bytes() == raw
    assert row['content_sha256'] == hashlib.sha256(raw).hexdigest()
    def fail(source):
        calls.append(source)
        raise requests.Timeout('Synthetic outage')
    stale = source_snapshot(tmp_path, STABLE, fetcher=fail, now=1900)
    assert stale['status'] == 'stale' and stale['rows'] == first['rows']
    assert 'Timeout' in stale['error']
    source_snapshot(tmp_path, STABLE, fetcher=fail, now=1901)
    assert len(calls) == 2
    assert len(list((tmp_path / 'data/market/raw').glob('*.json'))) == 1
    recovered = source_snapshot(tmp_path, STABLE, fetcher=fetcher, now=1961)
    assert recovered['status'] == 'available' and recovered['error'] is None


def test_initial_failure_has_no_fabricated_rows(tmp_path):
    result = source_snapshot(tmp_path, STABLE, fetcher=lambda s: b'<html>Not JSON</html>', now=1000)
    assert result['status'] == 'unavailable' and result['rows'] == []


def test_corrupt_saved_bytes_cannot_be_displayed(tmp_path):
    first = source_snapshot(tmp_path, STABLE, fetcher=lambda s: json.dumps(PAYLOAD).encode(), now=1000)
    (tmp_path / first['rows'][0]['raw_path']).write_bytes(b'{}')
    with pytest.raises(ValueError, match='hash'):
        source_snapshot(tmp_path, STABLE, fetcher=lambda s: b'', now=1001)


def test_http_429_is_not_retried(monkeypatch):
    calls = []
    class Response:
        status_code = 429
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): raise requests.HTTPError('429')
    class Session:
        def __init__(self): self.headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            assert kwargs['timeout'] == (5, 20) and kwargs['allow_redirects'] is False
            calls.append(url)
            return Response()
    monkeypatch.setattr('market_data.requests.Session', Session)
    with pytest.raises(requests.HTTPError): fetch(STABLE)
    assert len(calls) == 1
