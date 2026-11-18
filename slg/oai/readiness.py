"""Preparation checks; missing licenses do not invent rights or block development."""
from .rights import canonical_rights_uri, image_rights_uri, metadata_rights_uri


def collection_readiness(slg):
    issues = []
    if slg.kulturpool_rights_uri and not canonical_rights_uri(slg.kulturpool_rights_uri):
        issues.append('Konfigurierte Bildrechte-URI ungültig')
    if not image_rights_uri(slg):
        if (slg.bildrechte_lizenz or '').strip():
            issues.append('Bildrechte-URI fehlt: Lizenztext „%s“ ist keine eindeutige Lizenzangabe '
                          '(z. B. „CC BY-NC 4.0“) – bitte Kulturpool-Rechte-URI eintragen'
                          % slg.bildrechte_lizenz.strip()[:80])
        else:
            issues.append('Bildrechte-URI fehlt oder ist ungültig')
    if not metadata_rights_uri(slg):
        issues.append('Metadatenrechte-URI fehlt oder ist ungültig')
    return issues
