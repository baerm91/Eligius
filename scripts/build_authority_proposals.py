"""Resolve a saved inventory into local review files; no Django or database writes."""
import argparse
import csv
import io
import hashlib
import json
import logging
import sys
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_authority_labels import nomisma_labels, wikidata_label
from scripts.render_authority_review import render as render_review
from slg.services.authority_inventory import identify_authority
from slg.services.authority_proposals import ISSUE_LABELS, build_proposals, gnd_evidence


class CachedHTTP:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.next_request = 0

    def get(self, url, params=None, accept=None):
        key = hashlib.sha256(json.dumps([url, params, accept], sort_keys=True).encode()).hexdigest()
        path = self.directory / (key + '.json')
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        headers = {'User-Agent': 'Eligius-Authority-Review/1.0 (https://eligius.donau-uni.ac.at/)'}
        if accept:
            headers['Accept'] = accept
        for attempt in range(3):
            with self.lock:
                delay = max(0, self.next_request - time.monotonic())
                self.next_request = max(self.next_request, time.monotonic()) + 0.5
            time.sleep(delay)
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code in (429, 502, 503, 504) and attempt < 2:
                retry = response.headers.get('Retry-After', '')
                wait = max(2 ** (attempt + 1), int(retry) if retry.isdigit() else 0)
                if wait > 60:
                    raise RuntimeError(f'Rate limited; retry later ({wait}s): {url}')
                with self.lock:
                    self.next_request = max(self.next_request, time.monotonic() + wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            result = dict(source_url=response.url, retrieved_at=datetime.now(timezone.utc).isoformat(),
                          response_sha256=hashlib.sha256(response.content).hexdigest(),
                          body=response.content.decode('utf-8-sig'))
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            temporary.replace(path)
            return result
        raise RuntimeError(f'Fetch failed: {url}')


def provenance(response):
    return {k: v for k, v in response.items() if k != 'body'}


def parallel(items, function, name):
    results = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {pool.submit(function, item): item for item in items}
        for index, future in enumerate(as_completed(pending), 1):
            item = pending[future]
            try:
                results[item] = future.result()
            except Exception as error:
                results[item] = {'error': f'{type(error).__name__}: {error}'}
            if index % 25 == 0 or index == len(items):
                print(f'{name}: {index}/{len(items)}', flush=True)
    return results


def csv_text(value):
    text = str(value or '')
    # Avoid spreadsheet formula interpretation; canonical data remains in JSON.
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def git_rdf_blobs(repository, revision, identifiers):
    # Read committed objects, not checkout files: Windows can conflate case-distinct IDs.
    specs = ''.join(f'{revision}:id/{identifier}.rdf\n' for identifier in identifiers)
    raw = subprocess.check_output(['git', '-C', str(repository), 'cat-file', '--batch'], input=specs.encode())
    stream = io.BytesIO(raw)
    results = {}
    for identifier in identifiers:
        header = stream.readline().decode().rstrip()
        if header.endswith(' missing'):
            results[identifier] = None
        else:
            _, kind, size = header.split()
            if kind != 'blob':
                raise ValueError(f'Expected RDF blob: {identifier}')
            results[identifier] = stream.read(int(size))
            if stream.read(1) != b'\n':
                raise ValueError('Invalid git batch response')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nomisma-repo', type=Path, help='Local checkout of the official nomisma/data repository.')
    args = parser.parse_args()
    # rdflib attempts to convert BCE gYear literals to Python dates. We consume
    # labels/identity links only; retain raw RDF and count these unrelated warnings.
    date_warnings = Counter()

    class DateConversionFilter(logging.Filter):
        def filter(self, record):
            if 'Failed to convert Literal lexical form' in record.getMessage() and 'XMLSchema#gYear' in record.getMessage():
                date_warnings['count'] += 1
                return False
            return True

    logging.getLogger('rdflib.term').addFilter(DateConversionFilter())
    raw = args.inventory.read_bytes()
    inventory = json.loads(raw.decode('utf-8-sig'))
    records = inventory['records']
    args.output.mkdir(parents=True, exist_ok=True)
    http = CachedHTTP(args.output / 'cache')
    authorities = {ref for r in records if (ref := identify_authority(
        r['value'], allow_nomisma_id=r['field'] == 'name_nom_id'))}
    resolved = {}
    ids = sorted(i for provider, i in authorities if provider == 'nomisma')
    batches = [tuple(ids[i:i + 40]) for i in range(0, len(ids), 40)]
    repository_revision = None
    if args.nomisma_repo:
        repository_revision = subprocess.check_output(
            ['git', '-C', str(args.nomisma_repo), 'rev-parse', 'HEAD'], text=True).strip()
        origin = subprocess.check_output(['git', '-C', str(args.nomisma_repo), 'remote', 'get-url', 'origin'], text=True).strip()
        if origin not in ('https://github.com/nomisma/data.git', 'https://github.com/nomisma/data', 'git@github.com:nomisma/data.git'):
            parser.error('Expected the official nomisma/data origin')

    def fetch_nomisma(batch):
        if args.nomisma_repo:
            rows = []
            blobs = git_rdf_blobs(args.nomisma_repo, repository_revision, batch)
            for identifier in batch:
                try:
                    body = blobs[identifier]
                    if body is None:
                        raise FileNotFoundError(f'No RDF at revision {repository_revision}: {identifier}')
                    row = nomisma_labels(body, [identifier])[0]
                    rows.append(dict(row, source_url=f'https://github.com/nomisma/data/blob/{repository_revision}/id/{quote(identifier)}.rdf',
                                     revision=repository_revision, retrieved_at=datetime.now(timezone.utc).isoformat(),
                                     response_sha256=hashlib.sha256(body).hexdigest()))
                except Exception as error:
                    rows.append(dict(authority_id=identifier, english_labels=[], error=f'{type(error).__name__}: {error}',
                                     error_kind='missing_source_record' if isinstance(error, FileNotFoundError) else 'parse_error'))
            return rows
        response = http.get('https://nomisma.org/apis/getRdf', {'identifiers': '|'.join(batch), 'format': 'xml'})
        return [dict(row, **provenance(response)) for row in nomisma_labels(response['body'], batch)]

    for batch, result in parallel(batches, fetch_nomisma, 'Nomisma batches').items():
        if isinstance(result, dict):
            for identifier in batch:
                resolved[('nomisma', identifier)] = result
            continue
        for row in result:
            resolved[('nomisma', row['authority_id'])] = dict(row, candidates=[
                dict(label=label, provider='nomisma', uri='http://nomisma.org/id/' + row['authority_id'],
                     source_url=row['source_url'], retrieved_at=row['retrieved_at']) for label in row['english_labels']])

    def fetch_gnd(identifier):
        response = http.get('https://d-nb.info/gnd/' + identifier, accept='application/rdf+xml')
        return dict(gnd_evidence(response['body'], identifier), **provenance(response))

    gnd = parallel(sorted(i for provider, i in authorities if provider == 'gnd'), fetch_gnd, 'GND')
    wd_ids = {i for provider, i in authorities if provider == 'wikidata'}
    wd_ids.update(q for result in gnd.values() for q in result.get('wikidata_ids', []))

    def fetch_wikidata(identifier):
        response = http.get('https://www.wikidata.org/wiki/Special:EntityData/' + identifier + '.json')
        data = json.loads(response['body'])
        result = wikidata_label(data, identifier)
        return dict(result, revision=data.get('entities', {}).get(identifier, {}).get('lastrevid'),
                    **provenance(response), candidates=[dict(label=result['english_label'], provider='wikidata',
                    uri='http://www.wikidata.org/entity/' + identifier, source_url=response['source_url'],
                    retrieved_at=response['retrieved_at'])] if result['english_label'] else [])

    wikidata = parallel(sorted(wd_ids), fetch_wikidata, 'Wikidata')
    resolved.update({('wikidata', k): v for k, v in wikidata.items()})
    for identifier, result in gnd.items():
        candidates = [dict(label=label, provider='gnd', uri='http://d-nb.info/gnd/' + identifier,
                           source_url=result['source_url'], retrieved_at=result['retrieved_at'])
                      for label in result.get('english_labels', [])]
        linked = []
        for q in result.get('wikidata_ids', []):
            wd = wikidata[q]
            linked.append({**wd, 'authority_id': q})
            candidates.extend(dict(c, via_gnd='http://d-nb.info/gnd/' + identifier,
                                   reciprocal_gnd=identifier in wd.get('gnd_ids', []))
                              for c in wd.get('candidates', []))
        resolved[('gnd', identifier)] = dict(result, candidates=candidates, linked_wikidata=linked)
    proposals = build_proposals(records, resolved)
    summary = dict(entities=len(proposals), with_candidates=sum(bool(p['candidates']) for p in proposals),
                   without_candidates=sum(not p['candidates'] for p in proposals),
                   unchanged_labels=sum(p['original'] == p['proposed_entity_label'] for p in proposals),
                   changed_labels=sum(bool(p['candidates']) and p['original'] != p['proposed_entity_label'] for p in proposals),
                   issues=dict(Counter(issue for p in proposals for issue in p['issues'])),
                   approved=0,
                   fetch_errors=sum('error' in v and v.get('error_kind') != 'missing_source_record' for v in resolved.values()),
                   missing_source_records=sum(v.get('error_kind') == 'missing_source_record' for v in resolved.values()))
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), inventory_sha256=hashlib.sha256(raw).hexdigest(),
                  unrelated_rdf_date_conversion_warnings=date_warnings['count'],
                  nomisma_repository_revision=repository_revision,
                  inventory_generated_at=inventory.get('generated_at'), summary=summary, proposals=proposals,
                  scope='Dev authority references; not all database records. Entity labels are not full-text translations.')
    (args.output / 'proposals.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    render_review(args.output / 'proposals.json', args.output / 'pruefung.html')
    for filename, selected in [
        ('review.csv', proposals),
        ('changes.csv', [p for p in proposals if p['candidates'] and p['original'] != p['proposed_entity_label']]),
        ('open.csv', [p for p in proposals if not p['candidates']]),
    ]:
        with (args.output / filename).open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow(['Modell', 'ID', 'Original', 'Labelvorschlag', 'Status', 'Pruefhinweise', 'Alternativen', 'Quellen'])
            for p in sorted(selected, key=lambda p: (not bool(p['issues']), p['model'], p['id'])):
                writer.writerow([csv_text(v) for v in [p['model'], p['id'], p['original'], p['proposed_entity_label'],
                    'Offen' if p['status'] == 'unresolved' else 'Ungeprüfter Vorschlag',
                    '; '.join(ISSUE_LABELS[i] for i in p['issues']), ' | '.join(sorted({c['label'] for c in p['candidates']})),
                    ' | '.join(sorted({c['source_url'] for c in p['candidates']}))]])
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    explanation = [
        '# Übersetzungsvorschläge aus dem Dev-Bestand', '',
        f"Erstellt (UTC): {report['generated_at']}",
        f"Normdatenexport (UTC): {report['inventory_generated_at']}", '',
        f"- Lokale Datensätze mit Referenzen: {summary['entities']}",
        f"- Mit englischem Labelvorschlag: {summary['with_candidates']}",
        f"- Ohne Labelvorschlag: {summary['without_candidates']}",
        f"- Vorschlag identisch mit Original: {summary['unchanged_labels']}",
        f"- Vorschlag weicht vom Original ab: {summary['changed_labels']}",
        '- Freigegeben oder veröffentlicht: 0', '',
        'Die Abdeckung bezieht sich auf Datensätze mit befüllten Referenzfeldern, '
        'nicht auf alle Objekte oder alle übersetzbaren Felder.', '',
        '## Dateien', '',
        '- [Interaktive HTML-Prüfseite](pruefung.html): korrigieren, bestätigen und Prüfstand exportieren.',
        '- [Abweichende Vorschläge zuerst prüfen](changes.csv).',
        '- [Offene Fälle ohne Vorschlag](open.csv).',
        '- [Gesamte Prüfliste](review.csv): eine Zeile pro lokalem Datensatz.',
        '- [Vollständige Vorschläge und Herkunft](proposals.json).',
        '- [Zählwerte](summary.json).', '',
        'Ein Entitätslabel ersetzt keinen lokalen Titel mit Zusätzen. '
        'Gleiche Labels können korrekt sein; auch sie sind noch nicht freigegeben.', '',
        '## Prüfhinweise (können sich überschneiden)', '',
    ]
    explanation.extend(f'- {ISSUE_LABELS[key]}: {value}' for key, value in sorted(summary['issues'].items()))
    if repository_revision:
        explanation.extend(['', f'Nomisma-Stand: https://github.com/nomisma/data/tree/{repository_revision}'])
    (args.output / 'review.md').write_text('\n'.join(explanation) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
