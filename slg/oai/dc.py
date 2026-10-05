"""Required OAI Dublin Core fallback, projected from the same EDM mapping."""
from xml.etree import ElementTree as ET

from .edm import serialize_edm
from .identifiers import object_uri
from .xml import element, qname

TERM_MAPPING = {'isPartOf': 'relation', 'temporal': 'date', 'medium': 'format',
                'spatial': 'coverage', 'extent': 'format'}


def serialize_dc(row, obj, request):
    root = ET.Element(qname('oai_dc', 'dc'), {
        qname('xsi', 'schemaLocation'): 'http://www.openarchives.org/OAI/2.0/oai_dc/ http://www.openarchives.org/OAI/2.0/oai_dc.xsd',
    })
    edm = serialize_edm(row, obj, request)
    for child in edm.find(qname('edm', 'ProvidedCHO')):
        namespace, name = child.tag[1:].split('}')
        if namespace == 'http://purl.org/dc/terms/':
            name = TERM_MAPPING.get(name)
        elif namespace != 'http://purl.org/dc/elements/1.1/':
            continue
        if name:
            element(root, 'dc', name, child.text or child.get(qname('rdf', 'resource')))
    element(root, 'dc', 'identifier', object_uri(request, obj.pk))
    return root
