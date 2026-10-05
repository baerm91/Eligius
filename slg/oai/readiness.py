"""Preparation checks; missing licenses do not invent rights or block development."""
from .edm import valid_uri


def collection_readiness(slg):
    issues = []
    if not (valid_uri(slg.kulturpool_rights_uri) or valid_uri(slg.bildrechte_lizenz)):
        issues.append('Bildrechte-URI fehlt oder ist ungültig')
    if slg.kulturpool_rights_uri and not valid_uri(slg.kulturpool_rights_uri):
        issues.append('Konfigurierte Bildrechte-URI ungültig')
    if not valid_uri(slg.kulturpool_metadata_rights_uri):
        issues.append('Metadatenrechte-URI fehlt oder ist ungültig')
    return issues
