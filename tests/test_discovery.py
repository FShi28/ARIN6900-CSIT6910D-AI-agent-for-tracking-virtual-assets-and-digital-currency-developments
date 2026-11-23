"""Bounded discovery against recorded official pages; no network in these tests."""

import copy
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from virtual_asset_agent.collectors.hkma import discover_candidates
from virtual_asset_agent.common import PipelineError, sha256
from virtual_asset_agent.config import load_sources, validate_enabled
from virtual_asset_agent.discovery import scan, ingest_discovered
from virtual_asset_agent.fetching import Download, SourceAccessError
from virtual_asset_agent.pipeline import ingest
from virtual_asset_agent.storage import Repository, init_database

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT/'tests/fixtures/hkma'
SOURCES = load_sources(ROOT/'config/sources.yaml')
SOURCE = SOURCES['hkma']
LISTING = (FIX/'listing_discovery.html').read_bytes()
TIME = '2026-10-16T04:59:00Z'
PROVENANCE = json.loads((FIX/'provenance_discovered_articles.json').read_bytes())


class RecordedFetcher:
    def __init__(self, source, log):
        self.calls = []
        self.closed = 0
    def get(self, url, expected_type):
        self.calls.append(url)
        assert expected_type == 'text/html'
        if url == SOURCE['discovery_url']:
            raw = LISTING
        else:
            record = next(r for r in PROVENANCE if r['source_url'] == url)
            raw = (FIX/record['filename']).read_bytes()
        return Download(raw, url, expected_type, TIME)
    def close(self):
        self.closed += 1


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr('virtual_asset_agent.pipeline.utc_now', lambda: '2026-10-16T06:00:00Z')
    (tmp_path/'db').mkdir()
    (tmp_path/'db/schema.sql').write_bytes((ROOT/'db/schema.sql').read_bytes())
    db = tmp_path/'data/ingestion/test.sqlite'
    init_database(db, tmp_path/'db/schema.sql')
    return tmp_path, db


def candidates(raw=LISTING, source=SOURCE):
    return discover_candidates(raw, SOURCE['discovery_url'], source, TIME)


def test_official_discovery_and_article_provenance():
    p = json.loads((FIX/'provenance_discovery.json').read_bytes())
    assert sha256(LISTING) == p['sha256']
    for r in PROVENANCE:
        assert sha256((FIX/r['filename']).read_bytes()) == r['sha256']
    found, skipped = candidates()
    assert len(found) == 10
    assert found[0]['listing_date'] == '2026-04-10'
    assert found[-1]['listing_date'] == '2022-01-12'
    assert len({c['source_url'] for c in found}) == 10
    assert all(not c['target_verified'] for c in found)
    assert skipped and all('/press-releases/' in c['source_url'] for c in found)


@pytest.mark.parametrize('replacement,reason', [(b'10 Apr 2021','outside_date_scope'),
    (b'10 Apr 2030','outside_date_scope'), (b'Unknown','missing_or_invalid_listing_date')])
def test_listing_dates_not_url_dates_control_scope(replacement, reason):
    raw = LISTING.replace(b'10 Apr 2026', replacement)
    found, skipped = candidates(raw)
    assert len(found) == 9 and any(s['reason'] == reason for s in skipped)


def test_duplicate_relative_links_collapse_and_external_links_excluded():
    soup = BeautifulSoup(LISTING,'html.parser')
    item = soup.select_one('li.related-information-item')
    item.insert_after(copy.copy(item))
    external = copy.copy(item)
    external.select_one('a')['href'] = 'https://evil.invalid/eng/news-and-media/press-releases/2026/04/20260410-4/'
    item.insert_after(external)
    found, skipped = candidates(str(soup).encode())
    assert len(found) == 10 and any(s['reason']=='unapproved_url' for s in skipped)


def test_layout_change_and_candidate_overflow_fail():
    with pytest.raises(PipelineError):
        candidates(b'<html><h1>Regulatory Regime for Stablecoin Issuers</h1></html>')
    source = copy.deepcopy(SOURCE);source['discovery']['max_candidates']=9
    with pytest.raises(PipelineError,match='bound'):
        candidates(source=source)


def test_scan_only_fetches_listing_and_does_not_write_database(workspace):
    root,db=workspace; client=RecordedFetcher(None,None)
    repo=Repository(db);before=repo.counts();repo.close()
    report=scan(root,db,SOURCES,fetcher_factory=lambda *a:client)
    assert report['counts']=={'new':10,'known':0,'retry':0}
    assert client.calls == [SOURCE['discovery_url']] and client.closed==1
    assert (root/report['manifest_path']).is_file()
    repo=Repository(db);assert repo.counts()==before;repo.close()


def test_batch_shared_session_limit_repeat_and_known_state(workspace):
    root,db=workspace;client=RecordedFetcher(None,None)
    first=ingest_discovered(root,db,SOURCES,limit=3,fetcher_factory=lambda *a:client)
    assert first['status']=='success' and first['attempted']==3 and first['remaining']==7
    assert len(client.calls)==4 and client.closed==1
    second=ingest_discovered(root,db,SOURCES,limit=3,fetcher_factory=RecordedFetcher)
    assert all(r['status']=='reused' for r in second['results'])
    assert {r['extraction_id'] for r in first['results']}=={r['extraction_id'] for r in second['results']}
    report=scan(root,db,SOURCES,fetcher_factory=RecordedFetcher)
    assert report['counts']=={'new':7,'known':3,'retry':0}
    for r in first['results']:
        assert r['published_at']==r['discovery_evidence']['candidate']['listing_date']


@pytest.mark.parametrize('blocked', [False,True])
def test_single_failure_continues_but_access_denial_stops_batch(workspace, blocked):
    root,db=workspace
    class Failing(RecordedFetcher):
        def get(self,url,expected_type):
            d=super().get(url,expected_type)
            if url==PROVENANCE[1]['source_url']:
                if blocked:raise SourceAccessError('HTTP 429')
                return Download(b'<html>bad layout</html>',url,'text/html',TIME)
            return d
    report=ingest_discovered(root,db,SOURCES,limit=3,fetcher_factory=Failing)
    assert report['status']=='partial_failure'
    assert report['attempted']==(2 if blocked else 3)
    assert report['stopped_for_source_access'] is blocked
    assert report['results'][0]['status']=='created'
    if not blocked:assert report['results'][2]['status']=='created'


def test_absent_target_never_downloaded(workspace):
    root,db=workspace;client=RecordedFetcher(None,None)
    with pytest.raises(PipelineError,match='not found'):
        ingest(root,db,SOURCES,document_url='https://www.hkma.gov.hk/eng/news-and-media/press-releases/2024/07/20240717-99/',
               discovered=True,fetcher_factory=lambda *a:client)
    assert client.calls==[SOURCE['discovery_url']]


def test_article_and_listing_date_mismatch_fails(workspace):
    root,db=workspace
    class WrongDate(RecordedFetcher):
        def get(self,url,expected_type):
            d=super().get(url,expected_type)
            if url==PROVENANCE[0]['source_url']:
                return Download(d.content.replace(b'10 Apr 2026',b'11 Apr 2026'),url,d.media_type,TIME)
            return d
    report=ingest_discovered(root,db,SOURCES,limit=1,fetcher_factory=WrongDate)
    assert report['status']=='partial_failure'
    assert 'inconsistent' in report['results'][0]['message']
    repo=Repository(db);assert repo.counts()['extractions']==0;repo.close()


@pytest.mark.parametrize('limit', [0,11,True])
def test_invalid_batch_limits_fail_before_network(workspace,limit):
    def never(*a):raise AssertionError('Must not fetch')
    with pytest.raises(PipelineError):
        ingest_discovered(*workspace,SOURCES,limit=limit,fetcher_factory=never)


def test_disabled_discovery_and_bad_config(workspace):
    sources=copy.deepcopy(SOURCES);sources['hkma']['discovery']['enabled']=False
    with pytest.raises(PipelineError):scan(*workspace,sources,fetcher_factory=RecordedFetcher)
    source=copy.deepcopy(SOURCE);source['discovery']['max_batch']=30
    with pytest.raises(PipelineError):validate_enabled(source)


def test_new_only_skips_successful_articles_without_fetching_them(workspace):
    root,db=workspace
    class ThreeLinks(RecordedFetcher):
        def get(self,url,expected_type):
            d=super().get(url,expected_type)
            if url==SOURCE['discovery_url']:
                soup=BeautifulSoup(d.content,'html.parser')
                allowed={r['source_url'].removeprefix('https://www.hkma.gov.hk') for r in PROVENANCE}
                for item in soup.select('li.related-information-item'):
                    a=item.select_one('a[href]')
                    if a is None or a['href'] not in allowed:item.decompose()
                return Download(str(soup).encode(),url,d.media_type,d.collected_at)
            return d
    ingest_discovered(root,db,SOURCES,limit=3,fetcher_factory=ThreeLinks)
    client=ThreeLinks(None,None)
    report=ingest_discovered(root,db,SOURCES,limit=3,new_only=True,fetcher_factory=lambda *a:client)
    assert report['attempted']==report['selected']==report['remaining']==0
    assert client.calls==[SOURCE['discovery_url']]
