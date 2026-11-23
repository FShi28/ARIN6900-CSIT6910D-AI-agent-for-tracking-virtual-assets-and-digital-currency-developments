"""Synthetic temporary database tests; no demo or live data is imported or changed."""

import json
import sqlite3
from pathlib import Path

import pytest

from virtual_asset_agent.common import PipelineError, identity, sha256
from virtual_asset_agent.reader import Reader, main
from virtual_asset_agent.storage import connect, init_database

ROOT=Path(__file__).resolve().parents[1]


def version(db, doc, label, when):
    vid=identity('version',doc,label)
    db.execute('INSERT INTO document_versions VALUES (?,?,?,?,?,?,?,?,?)',
        (vid,doc,sha256(label.encode()),'https://example.invalid/'+label,None,'data/raw/'+label+'.html','text/html',when,when))
    return vid


def extraction(db, vid, label, when, text, published='2024-07-17'):
    eid=identity('extraction',vid,label);cid=identity('chunk',eid,0)
    evidence={'body':{'locator':{'selector':'.synthetic-article'}}}
    db.execute('''INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (eid,vid,sha256(label.encode()),when,'Synthetic '+label,'en',published,None,None,'press_release','unknown',text,text,json.dumps(evidence)))
    db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?)',(cid,eid,0,text,0,len(text),None,None,None,None))
    db.execute('INSERT INTO extraction_asset_classes VALUES (?,?,?,?)',(eid,'stablecoin','test-only',cid))
    return eid,cid


@pytest.fixture
def dataset(tmp_path):
    path=tmp_path/'synthetic.sqlite';init_database(path,ROOT/'db/schema.sql');db=connect(path)
    db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',('hkma','Synthetic test source','Hong Kong','HKMA','primary_regulator',None,None,0))
    a,b=identity('document','a'),identity('document','b')
    for did,slug in [(a,'a'),(b,'b')]:
        db.execute('INSERT INTO documents VALUES (?,?,?)',(did,'hkma','https://example.invalid/'+slug))
    v1=version(db,a,'one','2025-01-01T00:00:00Z');v2=version(db,a,'two','2025-02-01T00:00:00Z')
    e1,c1=extraction(db,v1,'original','2025-01-02T00:00:00Z','Stablecoin reserve assets 100%_ 😀.')
    e2,c2=extraction(db,v2,'updated','2025-02-02T00:00:00Z','Stablecoin reserve assets changed.')
    vb=version(db,b,'unknown','2025-01-01T00:00:00Z');eb,cb=extraction(db,vb,'unknown-date','2025-01-02T00:00:00Z','Another stablecoin document.',None)
    db.commit();db.close()
    return dict(path=path,a=a,b=b,v1=v1,v2=v2,e1=e1,e2=e2,c1=c1,c2=c2,eb=eb)


def observation(db,eid,run,when):
    db.execute('''INSERT INTO html_observations
        (run_id,extraction_id,collected_at,downloaded_url,parent_url,raw_path,content_sha256,
         response_fingerprint,article_fingerprint,rule_id,change_type) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        (run,eid,when,'https://example.invalid/a','https://example.invalid/list','data/raw/a.html',
         'a'*64,'b'*64,'c'*64,'hkma-html-csrf-v1','unchanged'))


def test_read_only_and_no_file_changes(dataset):
    path=dataset['path'];before=sha256(path.read_bytes())
    with Reader(path) as reader:
        assert len(reader.list_documents())==2
        assert reader.db.execute('PRAGMA query_only').fetchone()[0]==1
        with pytest.raises(sqlite3.OperationalError):reader.db.execute('CREATE TABLE forbidden(x)')
        with pytest.raises(sqlite3.OperationalError):reader.db.execute("DELETE FROM sources")
    assert sha256(path.read_bytes())==before


def test_current_version_and_history_are_separate(dataset):
    with Reader(dataset['path']) as r:
        assert r.get_document(dataset['a'])['extraction_id']==dataset['e2']
        assert [x['chunk_id'] for x in r.search('reserve assets')]==[dataset['c2']]
        assert r.get_chunk(dataset['c1'])['text']=='Stablecoin reserve assets 100%_ 😀.'
        e=r.get_extraction(dataset['e1'],include_text=True)
        c=r.get_chunk(dataset['c1']);assert e['clean_text'][c['char_start']:c['char_end']]==c['text']
        assert c['citation']['reference']=='chunk:'+dataset['c1']
        assert c['citation']['html_body_locator']=={'selector':'.synthetic-article'}


def test_reversion_observation_and_new_processing_of_that_version(dataset):
    db=connect(dataset['path']);observation(db,dataset['e1'],'reversion','2025-03-01T00:00:00Z')
    enew,_=extraction(db,dataset['v1'],'reprocessed','2025-03-02T00:00:00Z','Stablecoin reserve assets reprocessed.')
    db.commit();db.close()
    with Reader(dataset['path']) as r:
        row=r.get_document(dataset['a'])
        assert row['version_id']==dataset['v1'] and row['extraction_id']==enew
        assert row['last_observed_at']=='2025-03-01T00:00:00Z'
        assert row['evidence_collected_at']=='2025-01-01T00:00:00Z'


def test_tied_observation_times_use_insertion_order(dataset):
    db=connect(dataset['path'])
    observation(db,dataset['e2'],'first','2025-03-01T00:00:00Z')
    observation(db,dataset['e1'],'second','2025-03-01T00:00:00Z')
    db.commit();db.close()
    with Reader(dataset['path']) as r:assert r.get_document(dataset['a'])['version_id']==dataset['v1']


def test_unprocessed_latest_version_never_falls_back(dataset):
    db=connect(dataset['path']);v=version(db,dataset['a'],'unparsed','2025-04-01T00:00:00Z');db.commit();db.close()
    with Reader(dataset['path']) as r:
        row=r.get_document(dataset['a']);assert row['state']=='unprocessed'
        assert row['version_id']==v and row['extraction_id'] is None and row['chunk_count']==0
        assert r.search('reserve assets')==[]
        assert r.get_extraction(dataset['e2'])['state']=='ready'


def test_filters_pagination_and_unknown_dates(dataset):
    with Reader(dataset['path']) as r:
        assert len(r.list_documents(published_from='2024-01-01'))==1
        assert r.list_documents(published_to='2023-12-31')==[]
        assert r.list_documents(source='mas')==[]
        assert len(r.list_documents(limit=1,offset=1))==1
        assert r.list_documents(offset=99)==[]
        assert r.list_chunks(dataset['e1'],offset=1)==[]


@pytest.mark.parametrize('q', ['%', '_', "' OR 1=1 --",'does-not-exist'])
def test_search_literals_are_not_wildcards_or_sql(dataset,q):
    with Reader(dataset['path']) as r:assert r.search(q)==[]


def test_case_insensitive_phrase_and_historical_literal_match(dataset):
    db=connect(dataset['path']);observation(db,dataset['e1'],'return','2025-03-01T00:00:00Z');db.commit();db.close()
    with Reader(dataset['path']) as r:
        assert len(r.search('RESERVE ASSETS'))==1
        assert len(r.search('100%_'))==1
        assert len(r.search('😀'))==1


@pytest.mark.parametrize('kwargs', [{'limit':0},{'limit':101},{'offset':-1},{'published_from':'2025-02-31'},
    {'published_from':'2025-02-01','published_to':'2025-01-01'}])
def test_invalid_bounds_and_dates(dataset,kwargs):
    with Reader(dataset['path']) as r:
        with pytest.raises((PipelineError,ValueError)):r.list_documents(**kwargs)


def test_bad_ids_empty_queries_and_missing_records(dataset):
    with Reader(dataset['path']) as r:
        for value in ('x','a'*64):
            with pytest.raises(PipelineError):r.get_chunk(value)
        for query in ('','  ','x'*201,'\x00'):
            with pytest.raises(PipelineError):r.search(query)


def test_missing_database_is_not_created_and_old_schema_is_not_migrated(tmp_path):
    path=tmp_path/'missing.sqlite'
    with pytest.raises(PipelineError):Reader(path)
    assert not path.exists()
    db=sqlite3.connect(path);db.execute('PRAGMA user_version=1');db.close()
    before=sha256(path.read_bytes())
    with pytest.raises(PipelineError,match='v2'):Reader(path)
    assert sha256(path.read_bytes())==before


def test_empty_database_has_no_demo_fallback(tmp_path):
    path=tmp_path/'empty.sqlite';init_database(path,ROOT/'db/schema.sql')
    with Reader(path) as r:assert r.list_documents()==r.search('stablecoin')==[]


def test_cli_missing_arguments_fail_without_queries(capsys):
    assert main(['chunk'])==1
    assert 'requires --chunk-id' in capsys.readouterr().err
