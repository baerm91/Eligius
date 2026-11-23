import hashlib
import json
from pathlib import Path

from django.conf import settings

from .authority_inventory import inventory

REFERENCE_FIELDS = ('name_nom_id', 'DNB', 'WikiEn', 'WikiDe', 'uri_reference', 'nomisma_collection_uri')
SCHEMA = 'eligius-reviewed-authority-labels-v1'


def reviewed_path():
    return Path(settings.ELIGIUS_REVIEWED_AUTHORITY_LABELS_PATH)


def original_hash(references):
    return hashlib.sha256(json.dumps(references, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def record_hash(model, pk, values):
    records = [
        {'model': model, 'id': pk, 'label': values.get('name', ''), 'field': field, 'value': values[field]}
        for field in sorted(REFERENCE_FIELDS) if values.get(field) and str(values[field]).strip()
    ]
    return original_hash(inventory(records)['records'])
