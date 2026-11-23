"""Propose GeoNames/GND/VIAF identifiers from Nomisma and Wikidata; no Django or DB writes.

Input: output of `manage.py export_identifier_inventory`. Output directory:
proposals.json (authoritative), review.csv (ambiguous cases with a decision
column), summary.json, cache/ (raw Wikidata responses).
"""
import argparse
import csv
import hashlib
import json
import logging
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_authority_proposals import CachedHTTP, csv_text, git_rdf_blobs
from slg.services.authority_inventory import identify_authority
from slg.services.identifier_enrichment import (
    INVENTORY_SCHEMA,
    PROPOSAL_SCHEMA,
    decide,
    nomisma_links,
)

REVIEW_COLUMNS = ['Modell', 'ID', 'Name', 'Nomisma', 'Feld', 'Kandidaten', 'Quellen', 'Entscheidung']


def fetch_wikidata(http, ids):
    entities = {}
    ids = sorted(ids)
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        response = http.get('https://www.wikidata.org/w/api.php', {
            'action': 'wbgetentities', 'ids': '|'.join(batch), 'props': 'claims', 'format': 'json'})
        data = json.loads(response['body'])
        for key, entity in data.get('entities', {}).items():
            if 'missing' in entity:
                continue
            entities[key] = entity
            entities[entity.get('id', key)] = entity
            redirect = entity.get('redirects', {})
            if redirect.get('from'):
                entities[redirect['from']] = entity
        print(f'Wikidata: {min(start + 50, len(ids))}/{len(ids)}', flush=True)
    return entities


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nomisma-repo', type=Path, required=True,
                        help='Local checkout of the official nomisma/data repository.')
    parser.add_argument('--skip-wikidata', action='store_true',
                        help='Only Nomisma links (offline); Wikidata fallback cases stay without proposal.')
    args = parser.parse_args()
    logging.getLogger('rdflib.term').setLevel(logging.ERROR)  # BCE gYear literals; dates are not used
    raw = args.inventory.read_bytes()
    inventory = json.loads(raw.decode('utf-8-sig'))
    if inventory.get('schema') != INVENTORY_SCHEMA:
        parser.error('Unbekanntes Inventarformat; erwartet export_identifier_inventory.')
    origin = subprocess.check_output(['git', '-C', str(args.nomisma_repo), 'remote', 'get-url', 'origin'], text=True).strip()
    if origin.removesuffix('.git') not in ('https://github.com/nomisma/data', 'git@github.com:nomisma/data'):
        parser.error('Expected the official nomisma/data origin')
    revision = subprocess.check_output(['git', '-C', str(args.nomisma_repo), 'rev-parse', 'HEAD'], text=True).strip()
    args.output.mkdir(parents=True, exist_ok=True)

    records = inventory['records']
    nomisma_of = {}
    for record in records:
        ref = identify_authority(record.get('name_nom_id'), allow_nomisma_id=True)
        if ref and ref[0] == 'nomisma':
            nomisma_of[(record['model'], record['id'])] = ref[1]
    ids = sorted(set(nomisma_of.values()))
    links, missing = {}, set()
    for start in range(0, len(ids), 500):
        batch = ids[start:start + 500]
        for identifier, body in git_rdf_blobs(args.nomisma_repo, revision, batch).items():
            if body is None:
                missing.add(identifier)
                continue
            try:
                links[identifier] = nomisma_links(body, identifier)
            except Exception as error:  # keep going; record shows up as 'none'
                missing.add(identifier)
                print(f'Nomisma {identifier}: {type(error).__name__}: {error}', file=sys.stderr)
        print(f'Nomisma: {min(start + 500, len(ids))}/{len(ids)}', flush=True)

    # Wikidata only where Nomisma itself has no link of the needed kind.
    needed = set()
    for record in records:
        identifier = nomisma_of.get((record['model'], record['id']))
        found = links.get(identifier) or {}
        kinds = ['geonames'] if record['model'] == 'slg.Mzstaette' else ['gnd', 'viaf']
        if any(not found.get(kind) for kind in kinds):
            needed.update(found.get('wikidata', []))
    entities = fetch_wikidata(CachedHTTP(args.output / 'cache'), needed) if needed and not args.skip_wikidata else {}

    proposals = []
    for record in records:
        identifier = nomisma_of.get((record['model'], record['id']))
        for row in decide(record['model'], record, links.get(identifier), entities):
            source = (f'https://github.com/nomisma/data/blob/{revision}/id/{identifier}.rdf'
                      if identifier and identifier in links else None)
            for candidate in row['candidates']:
                candidate['source_url'] = (f"https://www.wikidata.org/wiki/{candidate['wikidata']}"
                                           if candidate['via'] == 'wikidata' else source)
            proposals.append(row)

    summary = {}
    for model, field in sorted({(p['model'], p['field']) for p in proposals}):
        summary[f'{model}.{field}'] = dict(Counter(p['status'] for p in proposals
                                                   if p['model'] == model and p['field'] == field))
    summary['nomisma_records_missing'] = len(missing)
    summary['wikidata_fallback'] = 'skipped' if args.skip_wikidata else len(needed)
    report = dict(schema=PROPOSAL_SCHEMA, generated_at=datetime.now(timezone.utc).isoformat(),
                  inventory_sha256=hashlib.sha256(raw).hexdigest(),
                  inventory_generated_at=inventory.get('generated_at'),
                  nomisma_repository_revision=revision, summary=summary, proposals=proposals)
    (args.output / 'proposals.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (args.output / 'review.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(REVIEW_COLUMNS)
        for p in proposals:
            if p['status'] != 'review':
                continue
            writer.writerow([csv_text(v) for v in [
                p['model'], p['id'], p['label'], p['name_nom_id'], p['field'],
                ' | '.join(c['value'] for c in p['candidates']),
                ' | '.join(sorted({c['source_url'] or '' for c in p['candidates']})), '']])
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
