"""Build review-only label proposals. Source text and identifiers are never replaced."""
import hashlib
import json
import re
from collections import defaultdict

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, SKOS

from slg.services.authority_inventory import identify_authority

ISSUE_LABELS = {
    'possible_german_catalogue_text': 'Möglicherweise deutscher Katalogtext trotz Englisch-Kennzeichnung',
    'numbers_or_ordinals_missing': 'Zahlen oder Ordnungszahlen fehlen im Vorschlag',
    'preserve_uncertainty': 'Unsicherheit oder Ergänzungszeichen erhalten',
    'check_parenthetical_information': 'Klammerzusätze prüfen und erhalten',
    'check_person_name_and_titles': 'Personenname, Titel und Zusätze vergleichen',
    'preserve_bibliographic_citation': 'Literaturzitat nicht ersetzen',
    'unresolved_reference': 'Referenz noch nicht aufgelöst',
    'source_fetch_or_parse_error': 'Quelle fehlt oder konnte nicht verarbeitet werden',
    'source_record_missing': 'Normdatenkennung im verwendeten Quellenstand nicht gefunden',
    'source_label_conflict': 'Quellen liefern unterschiedliche Labels',
    'no_explicit_english_label': 'Kein explizites englisches Label gefunden',
    'gnd_link_not_reciprocated': 'GND-Verknüpfung von Wikidata nicht bestätigt',
}


def gnd_evidence(xml, identifier):
    graph = Graph().parse(data=xml, format='xml')
    names, english, wikidata = set(), set(), set()
    for prefix in ('http://d-nb.info/gnd/', 'https://d-nb.info/gnd/'):
        for predicate, value in graph.predicate_objects(URIRef(prefix + identifier)):
            if isinstance(value, Literal) and (
                str(predicate).startswith(('http://d-nb.info/standards/elementset/gnd#preferredName',
                                           'https://d-nb.info/standards/elementset/gnd#preferredName'))
                or predicate == SKOS.prefLabel
            ):
                names.add((str(value), value.language or ''))
                if value.language == 'en':
                    english.add(str(value))
            if predicate in (OWL.sameAs, SKOS.exactMatch):
                ref = identify_authority(str(value))
                if ref and ref[0] == 'wikidata':
                    wikidata.add(ref[1])
    return dict(preferred_names=[dict(value=v, language=lang or None) for v, lang in sorted(names)],
                english_labels=sorted(english), wikidata_ids=sorted(wikidata))


def normalized(text):
    return ' '.join(text.split()).casefold()


def review_flags(original, label, model):
    flags = []
    if not label:
        return flags
    if re.search(r'\b(?:Fürstin|Fürst|Gräfin|Graf|König|Königin|Bischof|Abt|gest|geb)\b|BLKÖ', label):
        flags.append('possible_german_catalogue_text')
    original_numbers = set(re.findall(r'\d+|\b[IVXLCDM]+\b', original))
    label_numbers = set(re.findall(r'\d+|\b[IVXLCDM]+\b', label))
    if original_numbers - label_numbers:
        flags.append('numbers_or_ordinals_missing')
    if re.search(r'\?|\[|\]|\.{3}|…|\b(?:wohl|vermutlich|unsicher)\b', original, re.I):
        flags.append('preserve_uncertainty')
    if '(' in original or ')' in original:
        flags.append('check_parenthetical_information')
    if model.endswith('.Person') and normalized(original) != normalized(label):
        flags.append('check_person_name_and_titles')
    if model.endswith('.Ref'):
        flags.append('preserve_bibliographic_citation')
    return flags


def build_proposals(records, resolved):
    grouped = defaultdict(list)
    for record in records:
        grouped[(record['model'], record['id'])].append(record)
    proposals = []
    for (model, pk), references in sorted(grouped.items()):
        original = references[0].get('label') or ''
        candidates, issues, evidence = [], [], []
        for ref in references:
            authority = identify_authority(ref['value'], allow_nomisma_id=ref['field'] == 'name_nom_id')
            if not authority:
                issues.append('unresolved_reference')
                continue
            result = resolved.get(authority, {'error': 'not_resolved'})
            evidence.append({**result, 'provider': authority[0], 'authority_id': authority[1]})
            if result.get('error_kind') == 'missing_source_record':
                issues.append('source_record_missing')
            elif result.get('error'):
                issues.append('source_fetch_or_parse_error')
            if any(v.get('error') for v in result.get('linked_wikidata', [])):
                issues.append('source_fetch_or_parse_error')
            for candidate in result.get('candidates', []):
                if candidate['label']:
                    candidates.append(candidate)
        # Deduplicate exact evidence paths, never merge different local entities.
        candidates = list({json.dumps(c, sort_keys=True): c for c in candidates}.values())
        variants = {normalized(c['label']) for c in candidates}
        if len(variants) > 1:
            issues.append('source_label_conflict')
        preferred = next((c['label'] for c in candidates if c['provider'] == 'nomisma'),
                         candidates[0]['label'] if candidates else None)
        if not candidates:
            issues.append('no_explicit_english_label')
        for candidate in candidates:
            issues.extend(review_flags(original, candidate['label'], model))
            if candidate.get('reciprocal_gnd') is False:
                issues.append('gnd_link_not_reciprocated')
        original_hash = hashlib.sha256(json.dumps(references, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        proposals.append(dict(model=model, id=pk, original=original, original_sha256=original_hash,
                              proposed_entity_label=preferred,
                              status='unresolved' if not candidates else 'pending_review',
                              approved=False, issues=sorted(set(issues)), candidates=candidates,
                              references=references, evidence=evidence))
    return proposals
