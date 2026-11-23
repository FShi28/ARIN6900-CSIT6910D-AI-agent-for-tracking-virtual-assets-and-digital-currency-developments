"""Admission gate for an official HKeL XML candidate, not an ingestion adapter."""
import xml.etree.ElementTree as ET

NS = {'h': 'http://www.xml.gov.hk/schemas/hklm/1.0',
      'dc': 'http://purl.org/dc/elements/1.1/'}


def validate_chapter(content, chapter):
    if len(content) > 10 * 1024 * 1024 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('Unsupported or oversized XML')
    root = ET.fromstring(content)
    observed = dict(root_identifier=root.get('identifier'),
        doc_number=root.findtext('h:meta/h:docNumber', namespaces=NS),
        metadata_identifier=root.findtext('h:meta/dc:identifier', namespaces=NS),
        source_version_date=root.findtext('h:meta/dc:date', namespaces=NS))
    expected = '/hk/cap' + chapter + '!en'
    conflicts = [key for key, value in {
        'root_identifier': observed['root_identifier'] == expected,
        'doc_number': observed['doc_number'] == chapter,
        'metadata_identifier': observed['metadata_identifier'] == expected}.items() if not value]
    if root.find('h:main', NS) is None:
        conflicts.append('missing_main_body')
    return dict(status='quarantined' if conflicts else 'identity_validated',
                expected_chapter=chapter, observed=observed, conflicts=conflicts,
                legal_completeness=False)
