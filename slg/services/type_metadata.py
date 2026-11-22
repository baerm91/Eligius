"""Fetch and import coin type metadata from supported catalogues."""

import logging
import re
import textwrap
from datetime import date
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.db import IntegrityError, transaction
from rdflib import XSD, Graph, Literal, Namespace, URIRef
from requests.exceptions import RequestException

from ..models import (
    Muenzstand,
    Mzstaette,
    Mztyp_Person,
    Nominal,
    Person,
    PersonFunktion,
)


def extract_year(literal):
    if isinstance(literal, Literal):
        if literal.datatype == XSD.gYear:
            if literal.startswith('-'):  # Überprüfen auf negatives Jahr
                return str(literal)  # Direkte Verwendung des String-Werts
            elif isinstance(literal.value, date):
                return str(literal.value.year)  # Extrahieren des Jahres aus dem Datum
            else:
                return str(literal.value)  # Verwendung des Wertes, wenn kein Datum
    return None



# --- Sichere Verarbeitung externer Typ-Links (SSRF / SPARQL-Injection) -------
TYPE_LINK_HOSTS = {
    'numismatics': ('numismatics.org',),
    'rpc': ('rpc.ashmus.ox.ac.uk',),
}
TYPE_LINK_TIMEOUT = 20
TYPE_LINK_MAX_REDIRECTS = 3
TYPE_LINK_MAX_BYTES = 5 * 1024 * 1024
_SAFE_IRI_RE = re.compile(r'^https?://[^\s<>"{}|\\^`]+$')


def _host_matches(hostname, allowed_hosts):
    hostname = (hostname or '').lower().rstrip('.')
    return any(hostname == host or hostname.endswith('.' + host) for host in allowed_hosts)


def _normalize_type_link(link):
    """Gibt (art, url) für erlaubte Typ-Links zurück, sonst (None, None).

    Die Prüfung erfolgt auf dem geparsten Hostnamen (kein Substring-Vergleich),
    erlaubt nur http/https, keine Zugangsdaten und keine Nicht-Standardports.
    """
    link = (link or '').strip()
    if not link:
        return None, None
    if '://' not in link:
        link = 'https://' + link
    try:
        parts = urlparse(link)
        port = parts.port
    except ValueError:
        return None, None
    if parts.scheme not in ('http', 'https') or parts.username or parts.password:
        return None, None
    if port not in (None, 80, 443):
        return None, None
    for kind, hosts in TYPE_LINK_HOSTS.items():
        if _host_matches(parts.hostname, hosts):
            return kind, link
    return None, None


def _safe_sparql_iri(value):
    """Lässt nur IRIs zu, die gefahrlos in ``<...>`` interpoliert werden können."""
    value = str(value or '').strip()
    if not _SAFE_IRI_RE.match(value):
        raise ValueError('Ungültige IRI für SPARQL-Abfrage')
    return value


def _safe_get(url, allowed_hosts, **kwargs):
    """requests.get mit Timeout, Host-Allowlist und geprüften Redirects."""
    kwargs.setdefault('timeout', TYPE_LINK_TIMEOUT)
    current = url
    for _ in range(TYPE_LINK_MAX_REDIRECTS + 1):
        parts = urlparse(current)
        if parts.scheme not in ('http', 'https') or not _host_matches(parts.hostname, allowed_hosts):
            raise RuntimeError('Externe URL ist nicht erlaubt')
        if parts.username or parts.password or parts.port not in (None, 80, 443):
            raise RuntimeError('Externe URL ist nicht erlaubt')
        response = requests.get(current, allow_redirects=False, stream=True, **kwargs)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get('Location')
            response.close()
            if not location:
                raise RuntimeError('Ungültige Weiterleitung')
            current = urljoin(current, location)
            continue
        content = response.raw.read(TYPE_LINK_MAX_BYTES + 1, decode_content=True)
        response.close()
        if len(content) > TYPE_LINK_MAX_BYTES:
            raise RuntimeError('Antwort zu groß')
        response._content = content
        response._content_consumed = True
        return response
    raise RuntimeError('Zu viele Weiterleitungen')


def process_download_infos(obj):
    # Stellen Sie sicher, dass das Objekt einen Link enthält
    if not obj.link:
        return False, "Fehlermeldung"  # Beenden, falls kein Link vorhanden ist

    link_kind, safe_link = _normalize_type_link(obj.link)
    if link_kind is None:
        return False, "Link-Domain wird nicht unterstützt (nur numismatics.org und rpc.ashmus.ox.ac.uk)"

    # Code zur Verarbeitung des Links und der Daten
    try:
        # Alle Ergebniswerte vorbelegen: Jeder Zweig/Abbruch darf sie leer lassen,
        # ohne dass später ein UnboundLocalError entsteht.
        obverse_uri = None
        reverse_uri = None
        praegeherr_list, avpor_list, rvpor_list = [], [], []
        dat_von = dat_bis = nom = mint = avleg = rvleg = ""
        # Beispiel: Setzen von Feldern basierend auf geparsten Daten
        if link_kind == 'numismatics':
            # Normalize link - SPARQL database typically uses HTTP URIs
            if safe_link.startswith("https://"):
                http_link = "http://" + safe_link[8:]
            else:
                http_link = safe_link
            try:
                http_link = _safe_sparql_iri(http_link)
            except ValueError as exc:
                return False, str(exc)

            sparql_endpoint = 'https://nomisma.org/query'

            def run_sparql(query):
                normalized_query = textwrap.dedent(query).strip()
                params = {'query': normalized_query, 'output': 'json'}
                encoded_params = urlencode(params)
                sparql_query_url = f"{sparql_endpoint}?{encoded_params}"

                try:
                    response = requests.get(sparql_query_url, timeout=30)
                    response.raise_for_status()
                except RequestException as exc:
                    raise RuntimeError(
                        f"SPARQL-Request fehlgeschlagen: {exc}"
                    ) from exc

                try:
                    return response.json()
                except ValueError as exc:
                    raise RuntimeError(
                        "SPARQL-Antwort konnte nicht als JSON gelesen werden"
                    ) from exc

            # Query 1: Main type information
            # Try with HTTP URI first, then HTTPS if no results
            query_main = f"""
            SELECT * WHERE {{
              <{http_link}> ?p ?o
            }}
            """
            try:
                data_main = run_sparql(query_main)
            except RuntimeError as exc:
                return False, str(exc)

            # If no results with HTTP, try HTTPS URI
            if not data_main.get('results', {}).get('bindings', []):
                https_link = "https://" + http_link[7:] if http_link.startswith("http://") else http_link
                query_main_https = f"""
                SELECT * WHERE {{
                  <{https_link}> ?p ?o
                }}
                """
                try:
                    data_main_https = run_sparql(query_main_https)
                    if data_main_https.get('results', {}).get('bindings', []):
                        data_main = data_main_https
                        http_link = https_link  # Use HTTPS link for subsequent queries
                except RuntimeError:
                    pass  # Keep original data_main

            # Define your namespaces
            nmo = "http://nomisma.org/ontology#"

            # Extract data from main query
            praegeherr_list = []
            dat_von = ""
            dat_bis = ""
            nom = ""
            mint = ""
            obverse_uri = None
            reverse_uri = None

            for binding in data_main.get('results', {}).get('bindings', []):
                p = binding.get('p', {}).get('value', '')
                o = binding.get('o', {})
                o_value = o.get('value', '')

                if p == nmo + 'hasAuthority':
                    praegeherr_list.append(o_value)
                elif p == nmo + 'hasStartDate':
                    # Extract year from gYear datatype
                    dat_von = o_value.lstrip('0') if o_value else ""
                elif p == nmo + 'hasEndDate':
                    dat_bis = o_value.lstrip('0') if o_value else ""
                elif p == nmo + 'hasDenomination':
                    nom = o_value
                elif p == nmo + 'hasMint':
                    mint = o_value
                elif p == nmo + 'hasObverse':
                    obverse_uri = o_value
                elif p == nmo + 'hasReverse':
                    reverse_uri = o_value

            # Query 2: Obverse information
            avleg = ""
            avpor_list = []
            if obverse_uri:
                try:
                    obverse_uri = _safe_sparql_iri(obverse_uri)
                except ValueError as exc:
                    return False, str(exc)
                query_obverse = f"""
                SELECT * WHERE {{
                  <{obverse_uri}> ?p ?o
                }}
                """
                try:
                    data_obverse = run_sparql(query_obverse)
                except RuntimeError as exc:
                    return False, str(exc)

                for binding in data_obverse.get('results', {}).get('bindings', []):
                    p = binding.get('p', {}).get('value', '')
                    o_value = binding.get('o', {}).get('value', '')

                    if p == nmo + 'hasLegend':
                        avleg = o_value
                    elif p == nmo + 'hasPortrait':
                        avpor_list.append(o_value)

            # Query 3: Reverse information
            rvleg = ""
            rvpor_list = []
            if reverse_uri:
                try:
                    reverse_uri = _safe_sparql_iri(reverse_uri)
                except ValueError as exc:
                    return False, str(exc)
                query_reverse = f"""
                SELECT * WHERE {{
                  <{reverse_uri}> ?p ?o
                }}
                """
                try:
                    data_reverse = run_sparql(query_reverse)
                except RuntimeError as exc:
                    return False, str(exc)

                for binding in data_reverse.get('results', {}).get('bindings', []):
                    p = binding.get('p', {}).get('value', '')
                    o_value = binding.get('o', {}).get('value', '')

                    if p == nmo + 'hasLegend':
                        rvleg = o_value
                    elif p == nmo + 'hasPortrait':
                        rvpor_list.append(o_value)

        elif link_kind == 'rpc':
            # Fetch HTML content and parse to find the RDF link
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36'}
            rpc_hosts = TYPE_LINK_HOSTS['rpc']
            try:
                response = _safe_get(safe_link, rpc_hosts, headers=headers)
            except (RequestException, RuntimeError) as exc:
                return False, f"Abruf fehlgeschlagen: {exc}"

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                rdf_link = soup.find('a', string='rdf')

                if rdf_link:
                    rdf_url = urljoin(response.url or safe_link, rdf_link.get('href') or '')
                else:
                    # Wenn kein RDF-Link gefunden wurde, aus der if-Abfrage aussteigen
                    # messages.warning(request, f"Kein RDF-Link für {obj.link} gefunden.")
                    return False, "Kein RDF-Link gefunden"

                # RDF/XML selbst (geprüft) laden und rdflib nur die Daten übergeben,
                # damit rdflib keine beliebigen URLs (file://, interne Hosts) öffnet.
                try:
                    rdf_response = _safe_get(rdf_url, rpc_hosts, headers=headers)
                    rdf_response.raise_for_status()
                except (RequestException, RuntimeError) as exc:
                    return False, f"RDF-Abruf fehlgeschlagen: {exc}"
                g = Graph()
                g.parse(data=rdf_response.content, format='xml', publicID=rdf_url)

                # Define your namespaces
                nmo = Namespace("http://nomisma.org/ontology#")

                # Use rdflib's functions to find the information you want
                praegeherr_list = []
                for s, p, o in g.triples((None, nmo.hasAuthority, None)):
                    praegeherr_list.append(str(o))

                dat_von = ""
                for s, p, o in g.triples((None, nmo.hasStartDate, None)):
                    dat_von = extract_year(o)

                dat_bis = ""
                for s, p, o in g.triples((None, nmo.hasEndDate, None)):
                    dat_bis = extract_year(o)

                nom = ""
                for s, p, o in g.triples((None, nmo.hasDenomination, None)):
                    nom = str(o)

                mint = ""
                for s, p, o in g.triples((None, nmo.hasMint, None)):
                    mint = str(o)

                # Find the obverse for that TypeSeriesItem
                type_series_item_uri = URIRef(safe_link)
                for s, p, o in g.triples((type_series_item_uri, nmo.hasObverse, None)):
                    obverse_uri = o

                # Now find the legend for that obverse
                # (Subjekt None würde in rdflib auf ALLE Knoten passen.)
                avleg = ""
                avpor_list = []
                if obverse_uri is not None:
                    for s, p, o in g.triples((obverse_uri, nmo.hasLegend, None)):
                        avleg = str(o)
                    for s, p, o in g.triples((obverse_uri, nmo.hasPortrait, None)):
                        avpor_list.append(str(o))

                # Find the reverse for that TypeSeriesItem
                for s, p, o in g.triples((type_series_item_uri, nmo.hasReverse, None)):
                    reverse_uri = o

                # Now find the legend for that reverse
                rvleg = ""
                rvpor_list = []
                if reverse_uri is not None:
                    for s, p, o in g.triples((reverse_uri, nmo.hasLegend, None)):
                        rvleg = str(o)
                    for s, p, o in g.triples((reverse_uri, nmo.hasPortrait, None)):
                        rvpor_list.append(str(o))
            else:
                return False, "RDF-Link nicht gefunden"

        try:
            if dat_von:
                obj.dat_von = int(dat_von)
            if dat_bis:
                obj.dat_bis = int(dat_bis)
        except ValueError:
            print("Invalid value for dat_von or dat_bis:", dat_von, dat_bis)

        if not obj.avleg:
            obj.avleg = avleg
        if not obj.rvleg:
            obj.rvleg = rvleg
        if obj.Nominal is None and nom:
            nom_get = Nominal.objects.filter(name_nom_id=nom).first()
            if nom_get:
                obj.Nominal = nom_get

        if not obj.Mzstaette and mint:
            mint_get = Mzstaette.objects.filter(name_nom_id=mint).first()
            if mint_get:
                obj.Mzstaette = mint_get

        if link_kind == 'numismatics':
            obj.Muenzstand = Muenzstand.objects.get(id=424)

        # Erst die Typdaten speichern, dann Personen verknüpfen: eine unbekannte
        # Nomisma-Person darf die übrigen geladenen Felder nicht verwerfen.
        try:
            obj.save()
        except Exception as e:
            # Hier gibt es weder request noch message_user; der Aufrufer zeigt die Meldung an.
            logging.getLogger(__name__).exception('Münztyp %s konnte nach dem Typdaten-Abruf nicht gespeichert werden', obj.pk)
            return False, f"Fehler beim Speichern: {e}"

        missing = []
        for uris, funktion_id, on_rev in ((praegeherr_list, 1, 0), (avpor_list, 2, 0), (rvpor_list, 2, 1)):
            for uri in uris:
                if not uri:
                    continue
                person = Person.objects.filter(name_nom_id=uri).first()
                if person is None:
                    missing.append(str(uri))
                    continue
                try:
                    with transaction.atomic():
                        Mztyp_Person.objects.create(
                            Mztyp=obj, idfk_Person=person,
                            idfk_PersonFunktion=PersonFunktion.objects.get(id=funktion_id),
                            appears_on_rev=on_rev)
                except IntegrityError:
                    pass  # Verknüpfung existiert bereits

        if missing:
            return True, ("Daten erfolgreich verarbeitet. Nicht in Eligius vorhandene Personen "
                          "(name_nom_id): " + ", ".join(sorted(set(missing))))
        return True, "Daten erfolgreich verarbeitet"

    except Exception as e:
        print(f"Fehler bei der Verarbeitung: {e}")
        return False, f"Fehler bei der Verarbeitung: {e}"
