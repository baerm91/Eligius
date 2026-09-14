# Eligius Lab und öffentlicher Remote MCP

## Architektur

Django/MySQL bleiben autoritativ. Die vorhandene MTOA-Projektion und
Personen-Bridge werden unverändert weiterverwendet. Es gibt keine neue
Datenbank und keine natürliche Sprachinterpretation im Server.

`slg/services/search.py` enthält die aus Browse extrahierte MTOA-Abfrage.
Browse, Charts, Facetten und MCP benutzen dieselbe Objektmenge.
`slg/services/public_api.py` enthält öffentliche Ausgaben, Pagination und
gemeinsame Aggregationen. `slg/mcp_server.py` ist ausschließlich die
Transportschicht mit fünf lesenden Tools. Synchrone ORM-Aufrufe laufen außerhalb
des ASGI-Eventloops; Datenbankverbindungen werden an den Aufrufgrenzen bereinigt.

`djangoproject.asgi:application` reicht `/mcp` und Lifespan direkt an das
offizielle SDK weiter; alle anderen URLs gehen an Django. Stateless Streamable
HTTP mit JSON-Antworten, ohne Session-Speicher und ohne Redirect am Endpoint.
Das offizielle SDK ist auf `mcp==2.2.0` festgeschrieben. Dokumentation:
[ASGI-Integration](https://py.sdk.modelcontextprotocol.io/run/asgi/).

## Öffentliche Daten

Der Auftraggeber hat bestätigt, dass `Obj.freigabe` für diesen MVP ignoriert
werden darf. Damit gilt die bisherige öffentliche Website-Objektmenge.
`public_objects()` ist die zentrale Stelle für eine spätere Freigaberegel.
Es werden nur ausdrücklich ausgewählte Katalogfelder ausgegeben, keine
Workflow-Daten, internen Anmerkungen, temporären Typdaten oder Benutzerinformationen.
Nicht veröffentlichte Pakete werden weder aufgelistet noch als Filter wirksam.
Die vorhandenen umfassenden REST-/Update-Serializer werden nicht exponiert.

Keine Schreibtools, beliebigen Modelnamen, SQL-Eingaben oder ORM-Pfade.
`FILTER_PARAMETERS` ist die Whitelist der fachlichen Filter; `unbestimmt`
ist zusätzlich der bestehende Browse-Modus. Unbekannte MCP-Filter werden
abgelehnt. Das [Bearbeiter-MCP](EDITOR_MCP_DEVELOPMENT.md) hat einen eigenen
Endpunkt, eigene Authentifizierung und getrennte Tools; die öffentliche
Schnittstelle bleibt unverändert read-only.

## URLs und Konfiguration

- `/mcp`: Remote MCP, nur unter ASGI und bei aktivierter Einstellung.
- `/lab/`: öffentlicher Einstieg „Connect your AI“.
- `/health`: GET, `200 {"status":"ok","mcp_enabled":true}` bei verfügbarer
  Datenbank, sonst 503 ohne interne Fehlerdetails. Prüft keine vollständige
  MCP-Kommunikation; dafür dient der SDK-Smoke-Test.

Beispiel für die Umgebung (Host durch den jeweiligen Deployment-Host ersetzen):

```sh
ELIGIUS_MCP_ENABLED=1
ELIGIUS_PUBLIC_BASE_URL=https://dev.example.org
ELIGIUS_MCP_ALLOWED_HOSTS=dev.example.org,localhost:*,127.0.0.1:*
ELIGIUS_MCP_ALLOWED_ORIGINS=https://dev.example.org
DJANGO_ALLOWED_HOSTS=dev.example.org,localhost,127.0.0.1
```

Die öffentliche Basis-URL muss beim Remote-Deployment absolut und mit HTTPS
gesetzt werden. Ohne Basis-URL liefern lokale Service-Aufrufe relative Links;
Lab verwendet dann die Request-URL. Host- und Origin-Prüfung bleiben aktiv.
Requests ohne Origin sind für serverseitige MCP-Clients erlaubt. Für einen
Browser-Client mit anderer Origin müssen dessen konkrete Origin sowie bei
Bedarf gezielte CORS-Regeln ergänzt werden. Die öffentliche MCP-Schicht
übernimmt nicht Djangos globale CORS-Einstellung.

Lokaler ASGI-Start mit den vorhandenen Django-/MySQL-Umgebungsvariablen:

```sh
python -m pip install -r requirements.txt
python -m uvicorn djangoproject.asgi:application --host 127.0.0.1 --port 8000
```

`manage.py runserver` und der bestehende WSGI-Einstieg bedienen kein MCP.
Beim bestehenden Reverse Proxy bleiben HTTPS, statische Dateien und Bilder
unverändert. Der ASGI-Prozess lauscht nur auf Loopback.

## Tools und Parameter

| Tool | Parameter | Ergebnis |
| --- | --- | --- |
| `search_objects` | `filters={}`, `page=1`, `page_size=25` | `total`, `page`, `page_size`, `has_more`, `results` |
| `get_object` | `object_id` (positive Eligius-ID) | Öffentliche Details, Maße, Merkmale, Datensatz-URL |
| `get_facets` | `facet`, `filters={}`, `page=1`, `page_size=25`, `include_current=false` | Paginierte Werte mit `name`, gegebenenfalls `id`, `count`; `total` zählt Werte |
| `get_distribution` | `dimension`, `filters={}`, `page=1`, `page_size=25` | Objektzahl `total`, `total_values`, Werte mit `count` und `percentage`, Pagination |
| `get_statistics` | `filters={}` | Objektzahl, vertretene Typen/Sammlungen/Münzstätten, Datierungs- und Gewichtsgrenzen |

Seitengröße 1–100, keine fachliche Obergrenze über alle Seiten. Suche sortiert
stabil nach Objekt-ID; Seiten hinter dem Ende sind leer. Gleichzeitige
Katalogänderungen können wie bei Browse seitenübergreifende Ergebnisse ändern.

Filterwerte dürfen Skalare oder Listen sein: OR innerhalb einer Facette,
AND zwischen Facetten. Namen sind bei exakten Filtern aus `get_facets` zu
übernehmen. Beispiele:

```json
{"filters":{"Praegeherren":["Valens"],"Muenzstaette":["Siscia"]},"page":1,"page_size":25}
```

ID-Filter: `Slg`, `SlgTeil`, `coin_type`, `Nominal_id`, `av_bildtyp`,
`rv_bildtyp`. `Paket` akzeptiert öffentliche Paket-IDs bzw. die bisherigen
Browse-Bezeichnungen. Andere Facetten benutzen die bisherige Browse-Semantik;
insbesondere Prägeherren und dargestellte Personen sind unterschiedliche Rollen.

`dat_von`/`dat_bis` wählen überlappende Datierungsbereiche, negative Jahre
stehen für v. Chr. Einzelne Grenzen sind möglich. `unbestimmt=true` liefert
Objekte ohne Typ, `false` solche mit Typ, weggelassen/`"Alle"` beide.
`num` und `invnr` werden nun auch im gemeinsamen MTOA-Pfad ausgewertet;
zuvor wurden diese deklarierten Filter dort ignoriert.

`get_facets` nimmt den Filter der eigenen Facette standardmäßig heraus,
entsprechend Browse. Für eine vollständige Einschränkung `include_current=true`
verwenden. `get_distribution` berücksichtigt immer alle aktiven Filter.
Anteile beziehen sich auf alle passenden Objekte, auch solche ohne Wert;
fehlende Werte erscheinen nicht als eigene Kategorie. Mehrfachzuordnungen
können in Summe über 100 % ergeben. Facetten zählen distinct Objekt-IDs.

Illustrative Antwort (keine Zusage über den aktuellen Datenbestand):

```json
{"total":2,"total_values":1,"dimension":"Praegeherren","page":1,"page_size":25,
 "has_more":false,"results":[{"id":3338,"name":"Valens","count":2,"percentage":100.0}]}
```

Suche liefert ID, Inventarnummer, Sammlung/-teil, Typ, Personen und Rollen,
Münzstätte, Nominal, Material, Datierung, Av./Rv.-Legende und Beschreibung
sowie die öffentliche URL. `get_object` ergänzt Gewicht, Durchmesser,
Stempelstellung und Merkmale.

Die alte ungefilterte `stats_api`-Antwort bleibt für die Startseite kompatibel.
Mit Queryparametern verwendet sie die gemeinsame gefilterte Bestandsstatistik.
`facet_api` behält seine Listenform und die ersten 50 Werte; unterstützt
`include_current_facet=1` und den auf Development vorhandenen Alias
`include_selected=1`.

## Tests

Portable Tests verwenden ausschließlich eine temporäre SQLite-Testdatenbank,
keine neue Anwendung oder dauerhafte Datenquelle. Legacy-MySQL-Migrationen
werden dort durch Schemaaufbau aus Modellen ersetzt:

```sh
python manage.py test slg.test_mcp slg.tests.FacetApiTests --settings=djangoproject.test_settings --noinput
```

Fixtures prüfen positive und negative Treffer, Rollen, Browse-/MCP-ID-Gleichheit,
Pagination, Verteilungen, private Pakete und interne Ausgaben. Transporttests
prüfen Handshake, Tool-Liste, Aufruf, Statelessness und Host-/Origin-Schutz.

Read-only Prüfung gegen die konfigurierte Development-MySQL-Datenbank:

```sh
python scripts/mcp_verify_data.py
# Optional zusätzlich gegen Browse-Code des vorherigen Releases:
python scripts/mcp_verify_data.py --baseline-views /path/to/previous/slg/views.py
python scripts/mcp_smoke.py https://dev.example.org/mcp
```

Der SDK-Smoke-Test verwendet den offiziellen Client über echten HTTP-Transport
und ruft alle fünf Tools auf. Reale leere Treffer sind gültig: Ein Name kann
als dargestellte Person vorkommen, ohne in derselben Menge als Prägeherr
erfasst zu sein. Die Filter dürfen diese Rollen nicht stillschweigend vermischen.

## Beispielprompts

- „Zeige mir alle Münzen des Valens aus Siscia.“
- „Welche Nominale kommen bei Valens in Siscia vor?“
- „Welche Prägeherren sind in Sammlung X vertreten?“
- „Vergleiche Sammlung X und Y nach Prägeherren und Münzstätten mit Prozentanteilen.“
- „Welche Münztypen des Pescennius Niger befinden sich in Eligius?“

Der Client entdeckt Werte, setzt fachlich passende Filter und blättert bei
`has_more` weiter. Eligius interpretiert keine natürliche Sprache.

## Spätere Übernahme auf Produktion

Produktionsdeployment gehört nicht zu diesem Task. Derselbe Code kann später
mit umgebungsspezifischer Basis-URL, Host-/Origin-Whitelist und bestehender
Datenbankkonfiguration unter ASGI laufen. Vorher die dann gültige Freigaberegel,
Proxygrenzen, Lastverhalten und Datenprojektion prüfen. Keine Produktionshosts
oder Zugangsdaten sind in den neuen MCP-Dateien hinterlegt.

Development wird als separates Release mit separater Python-Umgebung geprüft.
Ein Rollback stellt vorherigen Release-Link und ursprünglichen Dienststart
wieder her. Es sind weder Datenmigrationen noch Backfills für MCP erforderlich.

## Verifikation am 13. September 2026

Development: [Eligius Lab](https://46.101.237.189/lab/),
[MCP-Endpunkt](https://46.101.237.189/mcp),
[Healthcheck](https://46.101.237.189/health).

- Neun relevante automatisierte Tests bestehen unter Python 3.12 lokal und
  Python 3.10 auf Development. `manage.py check` und `pip check` erfolgreich.
- Zehn Echtdatenfälle wurden mit vollständiger Pagination gegen den früheren
  Browse-Code verglichen, darunter 8.309 Objekte einer Sammlung auf 84 Seiten.
- Alle 32 aggregierbaren Facetten getestet; externer offizieller SDK-Client
  ruft alle fünf Tools über HTTPS erfolgreich auf.
- Lab auf Desktop/Mobil geprüft; Health, Browse, Facetten, gefilterte Stats und
  öffentliche Objektseite antworten mit HTTP 200.
- Valens als Prägeherr: 221 Objekte. Valens als Prägeherr + Siscia: 0.
  Valens als dargestellte Person Av. + Siscia: 731. Dies entspricht dem
  bisherigen Browse-Bestand und verdeutlicht die getrennten Rollen.
- Die komplette historische Testsuite ist nicht grün: sieben bestehende Fehler
  in ObjSave-/NomismaRdf-Tests wurden auch mit unverändertem bisherigen
  View-Code reproduziert. Die portable Testkonfiguration enthält keine
  historischen Stammdaten; vier Fehler betreffen fehlende Workflow-FKs,
  drei den vorhandenen RDF-Abfragepfad. Keine MCP-Regression nachgewiesen.

Aktives Development-Release: `/djangoproject/releases/eligius-mcp-20260913`.
Python-Umgebung: `/djangoproject/shared/venv-mcp-20260913`.
Der vorhandene Dienst `eligius-gunicorn` verwendet die Drop-in-Datei
`/etc/systemd/system/eligius-gunicorn.service.d/mcp-asgi.conf`.
Apache-Konfiguration blieb unverändert, temporärer Prüfdienst wurde beendet.
Vorheriges Release: `/djangoproject/releases/eligius-20260522-070338-df323b7`.
Für einen Rollback den `current`-Link darauf setzen, ausschließlich diese
MCP-Drop-in-Datei deaktivieren und `daemon-reload`/Dienstneustart ausführen.
Die vorhandene lokale HTTP/HTTPS-Linkänderung in `MuenztypListCreate` wurde
bewahrt und nicht als Teil des MCP-Deployments mit veröffentlicht.
