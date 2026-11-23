import json

from hk_relationships import relationship_report
from virtual_asset_agent.common import sha256


def fixture(root):
    (root/'config').mkdir()
    docs=[]
    for name in ('new','old'):
        (root/(name+'.txt')).write_text(name)
        docs.append(dict(url='https://official.test/'+name, document_id=name, authority='primary',
                         raw_path=name+'.txt', content_sha256=sha256(name.encode()), legal_status='not_assessed'))
    row=dict(id='r1', source_url=docs[0]['url'], source_sha256=docs[0]['content_sha256'],
             target_url=docs[1]['url'], target_sha256=docs[1]['content_sha256'], relation='supersedes',
             anchor='This circular supersedes', applies_to='Banks')
    (root/'config/hk_stablecoin_relationships.json').write_text(json.dumps([row]))
    chunks=[dict(document_id='new', chunk_id='c1', text='This circular supersedes the old circular.')]
    return docs,chunks


def test_relationship_is_evidence_not_automatic_legal_status(tmp_path):
    docs,chunks=fixture(tmp_path)
    rows=relationship_report(tmp_path,docs,chunks)
    assert rows[0]['status']=='evidence_validated'
    assert rows[0]['evidence_chunk_ids']==['c1']
    assert docs[1]['relationship_evidence'][0]['relation']=='supersedes'
    assert docs[1]['legal_status']=='not_assessed'
    assert chunks[0]['relationship_evidence_ids']==['r1']


def test_changed_source_requires_review(tmp_path):
    docs,chunks=fixture(tmp_path)
    (tmp_path/'new.txt').write_text('new version')
    docs[0]['content_sha256']=sha256(b'new version')
    assert relationship_report(tmp_path,docs,chunks)[0]['status']=='source_changed_requires_review'


def test_missing_target_and_missing_anchor_not_verified(tmp_path):
    docs,chunks=fixture(tmp_path)
    assert relationship_report(tmp_path,docs[:1],chunks)[0]['status']=='target_not_collected'
    chunks[0]['text']='Ordinary mention with no supersession.'
    assert relationship_report(tmp_path,docs,chunks)[0]['status']=='anchor_not_found'


def test_raw_target_tampering_invalidates_relation(tmp_path):
    docs,chunks=fixture(tmp_path)
    (tmp_path/'old.txt').write_text('tampered')
    assert relationship_report(tmp_path,docs,chunks)[0]['status']=='target_raw_invalid'
