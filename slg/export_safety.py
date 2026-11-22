"""Schutz gegen CSV-/Excel-Formula-Injection in Exporten.

Zellen, die mit ``=``, ``+``, ``-``, ``@``, Tab oder CR beginnen, werden von
Tabellenkalkulationen als Formel interpretiert. Solche Texte bekommen ein
führendes Apostroph (OWASP-Empfehlung). Zahlen und rein numerische Texte
(z. B. negative Jahreszahlen wie ``-44``) bleiben unverändert.
"""
import re

import tablib
from import_export.formats import base_formats

FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')
_NUMBER_RE = re.compile(r'[+-]?\d+(?:[.,]\d+)?')


def neutralize_formula(value):
    if (isinstance(value, str) and value and value[0] in FORMULA_PREFIXES
            and not _NUMBER_RE.fullmatch(value)):
        return "'" + value
    return value


def neutralize_dataset(dataset):
    """Gibt eine Kopie des tablib-Datasets mit neutralisierten Textzellen zurück."""
    safe = tablib.Dataset(headers=dataset.headers, title=dataset.title)
    for row in dataset:
        safe.append([neutralize_formula(cell) for cell in row])
    return safe


def _safe_format(base):
    class SafeFormat(base):
        def export_data(self, dataset, **kwargs):
            return super().export_data(neutralize_dataset(dataset), **kwargs)

    SafeFormat.__name__ = SafeFormat.__qualname__ = 'Safe' + base.__name__
    return SafeFormat


SafeCSV = _safe_format(base_formats.CSV)
SafeXLS = _safe_format(base_formats.XLS)
SafeXLSX = _safe_format(base_formats.XLSX)
SafeTSV = _safe_format(base_formats.TSV)
SafeODS = _safe_format(base_formats.ODS)

#: Für settings.EXPORT_FORMATS (django-import-export Admin-Exporte).
SAFE_EXPORT_FORMATS = [
    fmt for fmt in (SafeCSV, SafeXLS, SafeXLSX, SafeTSV, SafeODS,
                    base_formats.JSON, base_formats.YAML, base_formats.HTML)
    if fmt.is_available()
]
