import pytest
from virtual_asset_agent.collectors.hkel_validation import validate_chapter


def test_filename_or_body_title_cannot_override_conflicting_metadata():
    xml = b'''<ordinance xmlns="http://www.xml.gov.hk/schemas/hklm/1.0"
    xmlns:dc="http://purl.org/dc/elements/1.1/" identifier="/hk/cap155!en">
    <meta><docNumber>155</docNumber><dc:identifier>/hk/cap155!en</dc:identifier>
    <dc:date>2026-09-10</dc:date></meta><main>Stablecoins Ordinance</main></ordinance>'''
    result = validate_chapter(xml, '656')
    assert result['status'] == 'quarantined'
    assert set(result['conflicts']) == {'root_identifier', 'doc_number', 'metadata_identifier'}
    corrected = validate_chapter(xml.replace(b'155', b'656'), '656')
    assert corrected['status'] == 'identity_validated'
    assert corrected['legal_completeness'] is False


def test_external_entities_are_not_accepted():
    with pytest.raises(ValueError):
        validate_chapter(b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///secret">]><x>&y;</x>', '656')
