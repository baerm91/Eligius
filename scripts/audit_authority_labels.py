"""Read public vocabularies and resolve a bounded Nomisma pilot.

Writes review artifacts only. No database connection or writes to remote services.
Run from the repository root with the project's Python environment.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, SKOS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slg.services.authority_inventory import identify_authority, inventory


def nomisma_labels(xml, identifiers):
    graph = Graph().parse(data=xml, format='xml')
    results = []
    for identifier in identifiers:
        subject = URIRef('http://nomisma.org/id/' + identifier)
        labels = sorted({str(label) for label in graph.objects(subject, SKOS.prefLabel)
                         if isinstance(label, Literal) and label.language == 'en'})
        links = []
        for predicate in (SKOS.exactMatch, OWL.sameAs):
            for target in graph.objects(subject, predicate):
                ref = identify_authority(str(target))
                if ref and ref[0] in ('wikidata', 'gnd'):
                    links.append({'uri': str(target), 'predicate': str(predicate),
                                  'provider': ref[0], 'authority_id': ref[1]})
        results.append({'authority_id': identifier, 'english_labels': labels,
                        'status': 'candidate' if len(labels) == 1 else 'review_required',
                        'identity_links': sorted(links, key=lambda v: (v['uri'], v['predicate']))})
    return results


def wikidata_label(data, identifier):
    entity = data.get('entities', {}).get(identifier, {})
    label = entity.get('labels', {}).get('en', {})
    # Never treat a multilingual/default label or a redirect as confirmed English.
    english = label.get('value') if label.get('language') == 'en' and entity.get('id') == identifier else None
    gnd_ids = sorted({str(statement['mainsnak']['datavalue']['value'])
                      for statement in entity.get('claims', {}).get('P227', [])
                      if statement.get('rank') != 'deprecated'
                      and statement.get('mainsnak', {}).get('snaktype') == 'value'
                      and identify_authority('https://d-nb.info/gnd/' + str(statement['mainsnak']['datavalue']['value']))})
    return dict(authority_id=identifier, english_label=english,
                status='candidate' if english else 'review_required', gnd_ids=gnd_ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--base-url', default='http://46.101.237.189')
    parser.add_argument('--follow-wikidata', action='store_true',
                        help='Resolve only explicit Wikidata identity links found in the pilot.')
    parser.add_argument('--sample-per-model', default=20, type=int)
    args = parser.parse_args()
    if not 1 <= args.sample_per_model <= 100:
        parser.error('--sample-per-model must be between 1 and 100')
    args.output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['User-Agent'] = 'Eligius-Authority-Audit/1.0 (read-only pilot)'
    base = args.base_url.rstrip('/')
    if not base.startswith(('http://', 'https://')):
        parser.error('--base-url must be an HTTP(S) URL')
    records, coverage, selected = [], [], set()
    for model, endpoint in [('Mzstaette', '/api/mzstaette/'), ('Nominal', '/api/nominal/')]:
        response = session.get(base + endpoint, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError('Expected an unpaginated list; refusing an incomplete inventory')
        (args.output / f'{model}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        refs = [dict(model=model, id=r['id'], label=r['name'], field='name_nom_id', value=r['name_nom_id'])
                for r in data if (r.get('name_nom_id') or '').strip()]
        records.extend(refs)
        coverage.append(dict(model=model, total=len(data), populated=len(refs), endpoint=base + endpoint))
        ids = sorted({ref[1] for r in refs
                      if (ref := identify_authority(r['value'], allow_nomisma_id=True)) and ref[0] == 'nomisma'})
        # Deterministic, spread across sorted IDs. This is coverage exploration, not a random quality estimate.
        selected.update(ids[i * len(ids) // min(len(ids), args.sample_per_model)]
                        for i in range(min(len(ids), args.sample_per_model)))
    report = inventory(records)
    report.update(generated_at=datetime.now(timezone.utc).isoformat(), source=base, coverage=coverage,
                  limitations=['Only public mint and denomination tables; includes unused vocabulary entries.',
                               'Person endpoint requires authentication; DNB/Wikipedia fields are not exposed.',
                               'Pilot is deterministic and not statistically representative.',
                               'No entity identity or translation has been human-approved.'])
    report['pilot'] = []
    ids = sorted(selected)
    for offset in range(0, len(ids), 20):
        batch = ids[offset:offset + 20]
        response = session.get('https://nomisma.org/apis/getRdf',
                               params={'identifiers': '|'.join(batch), 'format': 'xml'}, timeout=45)
        response.raise_for_status()
        (args.output / f'nomisma-{offset // 20}.rdf').write_bytes(response.content)
        report['pilot'].extend(nomisma_labels(response.content, batch))
    report['wikidata_pilot'] = []
    if args.follow_wikidata:
        linked_ids = sorted({link['authority_id'] for row in report['pilot']
                             for link in row['identity_links'] if link['provider'] == 'wikidata'})
        for identifier in linked_ids:
            source_url = 'https://www.wikidata.org/wiki/Special:EntityData/' + identifier + '.json'
            try:
                response = session.get(source_url, timeout=30)
                response.raise_for_status()
                data = response.json()
                (args.output / f'wikidata-{identifier}.json').write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                report['wikidata_pilot'].append(dict(wikidata_label(data, identifier), source_url=source_url))
            except (requests.RequestException, ValueError) as error:
                report['wikidata_pilot'].append(dict(authority_id=identifier, source_url=source_url,
                                                     status='fetch_error', error=str(error)))
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'coverage': coverage, 'by_provider': report['by_provider'],
                      'unique_authorities': report['unique_authorities'], 'pilot_size': len(report['pilot']),
                      'with_one_english_label': sum(r['status'] == 'candidate' for r in report['pilot']),
                      'wikidata_candidates': sum(r['status'] == 'candidate' for r in report['wikidata_pilot']),
                      'identity_links': sum(len(r['identity_links']) for r in report['pilot'])}, indent=2))


if __name__ == '__main__':
    main()
