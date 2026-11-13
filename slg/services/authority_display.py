"""Language-aware presentation only. Never changes identifiers, filters or source fields."""
import json
from functools import lru_cache
from pathlib import Path
from threading import RLock
from time import monotonic

from django.apps import apps
from django.conf import settings
from django.utils.translation import get_language

from .authority_inventory import identify_authority

REFERENCE_FIELDS = ('name_nom_id', 'DNB', 'WikiEn', 'WikiDe', 'uri_reference', 'nomisma_collection_uri')
MODELS = ('Person', 'Nominal', 'Metall', 'Mzstaette', 'Region', 'Objekttyp',
          'Herstellungsmerkmale', 'Sek_Merkmale', 'Schlagwort', 'OffizinSymbol', 'Slg')
FACET_MODELS = {'Muenzstaette': 'Mzstaette', 'Nominal': 'Nominal', 'Nominal_id': 'Nominal',
    'material': 'Metall', 'region': 'Region', 'objekttyp': 'Objekttyp', 'obj_type': 'Objekttyp',
    'Praegeherren': 'Person', 'Person': 'Person', 'Dargestellte_AV': 'Person', 'Dargestellte_RV': 'Person',
    'her_merk': 'Herstellungsmerkmale', 'sek_merk': 'Sek_Merkmale',
    'av_schlagwort': 'Schlagwort', 'rv_schlagwort': 'Schlagwort', 'Slg': 'Slg',
    'av_bildtyp': 'AvBildtyp', 'rv_bildtyp': 'RvBildtyp'}


def english():
    return (get_language() or '').split('-')[0] == 'en'


@lru_cache(maxsize=2)
def _read_catalog(path, modified):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data['labels'] if data.get('schema') == 'eligius-authority-labels-v1' else {}
    except (OSError, ValueError, KeyError):
        return {}


def catalog():
    path = Path(getattr(settings, 'ELIGIUS_AUTHORITY_LABELS_PATH',
                        settings.BASE_DIR / 'var' / 'authority-labels.en.json'))
    try:
        modified = path.stat().st_mtime_ns
    except OSError:
        return {}, (str(path), None)
    return _read_catalog(str(path), modified), (str(path), modified)


def _label(values, labels):
    original = values.get('name', '')
    if values.get('name_en'):
        return values['name_en']
    refs = [identify_authority(values.get(field), allow_nomisma_id=field == 'name_nom_id')
            for field in REFERENCE_FIELDS]
    # Deterministic source priority; differences in authority naming aren't review work.
    for provider in ('nomisma', 'wikidata', 'gnd'):
        for ref in refs:
            if ref and ref[0] == provider:
                entry = labels.get(':'.join(ref))
                if entry and entry.get('label'):
                    return entry['label']
    return original


def display_label(instance):
    if instance is None:
        return ''
    if not english() or not hasattr(instance, '_meta'):
        return str(instance)
    if instance._meta.object_name not in (*MODELS, 'AvBildtyp', 'RvBildtyp'):
        return str(instance)
    labels, _ = catalog()
    fields = {f.name for f in instance._meta.concrete_fields}
    values = {field: getattr(instance, field) for field in (*REFERENCE_FIELDS, 'name', 'name_en') if field in fields}
    return _label(values, labels) or str(instance)


_indices = {}
_lock = RLock()


def clear_display_cache(*args, **kwargs):
    with _lock:
        _indices.clear()


def label_index(model_name):
    """One bounded cache per authority table, not a query per card or facet row.

    Other workers see edits within 60 seconds; source-file replacements are immediate.
    Duplicate original names with different translations deliberately fall back.
    """
    if model_name not in (*MODELS, 'AvBildtyp', 'RvBildtyp'):
        return {}, {}
    labels, version = catalog()
    with _lock:
        cached = _indices.get(model_name)
        if cached and cached[0] == version and cached[1] > monotonic():
            return cached[2], cached[3]
        model = apps.get_model('slg', model_name)
        fields = {f.name for f in model._meta.concrete_fields}
        columns = ['pk'] + [f for f in (*REFERENCE_FIELDS, 'name', 'name_en') if f in fields]
        by_id, variants = {}, {}
        for row in model.objects.values(*columns).iterator(chunk_size=2000):
            original = row.get('name', '')
            label = _label(row, labels)
            by_id[row['pk']] = label
            variants.setdefault(original, set()).add(label)
        by_name = {name: next(iter(values)) for name, values in variants.items() if len(values) == 1}
        _indices[model_name] = (version, monotonic() + 60, by_id, by_name)
        return by_id, by_name


def display_text(original, model_name):
    if not english() or not original:
        return original
    return label_index(model_name)[1].get(str(original), original)


def localize_facets(values, facet, term=None):
    """Keep name and ID as original query values; add a translated display label."""
    model = FACET_MODELS.get(facet)
    ids, names = label_index(model) if english() and model else ({}, {})
    result = []
    for value in values:
        label = ids.get(value.get('id'), names.get(value['name'], value['name']))
        if term and term.casefold() not in (str(value['name']) + ' ' + str(label)).casefold():
            continue
        result.append({**value, 'label': label} if label != value['name'] else value)
    return result
