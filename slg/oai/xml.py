"""Namespace and XML 1.0 text helpers shared by both metadata formats."""
import re
from xml.etree import ElementTree as ET

from django.utils.html import strip_tags

NS = {
    'oai': 'http://www.openarchives.org/OAI/2.0/',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
    'edm': 'http://www.europeana.eu/schemas/edm/',
    'ore': 'http://www.openarchives.org/ore/terms/',
    'skos': 'http://www.w3.org/2004/02/skos/core#',
    'oai_dc': 'http://www.openarchives.org/OAI/2.0/oai_dc/',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}
for prefix, uri in NS.items():
    ET.register_namespace('' if prefix == 'oai' else prefix, uri)

INVALID_XML = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')


def qname(prefix, name):
    return f'{{{NS[prefix]}}}{name}'


def clean_text(value):
    return INVALID_XML.sub('', strip_tags(str(value))).strip() if value is not None else ''


def element(parent, prefix, name, value=None, **attributes):
    child = ET.SubElement(parent, qname(prefix, name), attributes)
    if value is not None:
        child.text = clean_text(value)
    return child
