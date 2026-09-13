# Eligius WebMCP

WebMCP ergänzt Remote MCP auf der geöffneten öffentlichen Webseite. Es gibt
keinen Chatbot, kein LLM, keine neue Datenbank und keine zweite Suchlogik.
Aktivierung erfolgt zunächst ausschließlich auf Development.

## Architektur und gemeinsame Definitionen

`slg/webmcp.py` ist eine kleine öffentliche JSON-Brücke. Das Manifest übernimmt
die fünf bestehenden Remote-MCP-Schemas unverändert über die öffentliche
SDK-Methode `MCPServer.list_tools()`. Datenaufrufe verwenden
`MCPServer.call_tool()` und damit dieselbe Validierung, dieselben registrierten
Callbacks und dieselben Services wie Remote MCP:

`slg/mcp_server.py` → `slg/services/public_api.py` →
`slg/services/search.py` → bestehende Django-/MySQL-Daten.

`allowed_filter_names()` und `filter_request()` bleiben die gemeinsame
Whitelist/Normalisierung auf Basis von `FILTER_PARAMETERS`. In JavaScript
werden weder Queries noch Aggregationen oder fachliche Filter implementiert.

Die Browserdatei `slg/static/js/eligius-webmcp.js` wird außerhalb des vererbbaren
Scriptblocks der öffentlichen Navbar eingebunden, damit sie auch auf Browse,
Objekt-, Typ- und Sammlungsseiten vorhanden ist. Sie registriert ausschließlich
bei nativer `document.modelContext.registerTool`-Unterstützung. Ohne diese API
erfolgen weder Registrierung noch Manifest-/Datenabrufe. Keine Polyfills.

## Tools

| Tool | Parameter | Wirkung |
| --- | --- | --- |
| `search_objects` | identisch zu Remote MCP: `filters`, `page`, `page_size` | öffentliche Daten lesen |
| `get_object` | `object_id` | öffentliche Daten lesen |
| `get_facets` | `facet`, `filters`, Pagination, `include_current` | Facetten serverseitig zählen |
| `get_distribution` | `dimension`, `filters`, Pagination | absolute/relative Verteilung lesen |
| `get_statistics` | `filters` | serverseitige Kennzahlen lesen |
| `navigate_to_object` | `object_id` | aktuelle Registerkarte zur öffentlichen Objektseite navigieren |
| `navigate_to_coin_type` | `type_id` | öffentliche Typseite öffnen |
| `open_collection` | `collection_id` | öffentliche Sammlungsseite öffnen |
| `set_browse_filters` | `filters` | normale Browse-URL öffnen und bisherige Filter ersetzen |
| `clear_browse_filters` | keine | ungefilterte Browse-Seite öffnen |
| `get_current_context` | keine | aktuelle Seitenart, IDs und Browse-Filter lesen |

Die fünf Navigations-/Filtertools haben `readOnlyHint=false`, weil sie den
Seitenzustand ändern, obwohl sie keine Katalogdaten schreiben. Daten-/Kontexttools
sind als lesend gekennzeichnet. Navigation wird erst nach Rückgabe des
Toolergebnisses ausgelöst. Alle Ziel-URLs erzeugt Django mit `reverse()` nach
Validierung der ID/Filter; es gibt keinen frei wählbaren Navigations-URL-Parameter.

Beispiele:

```json
{"filters":{"Praegeherren":["Valens"],"Muenzstaette":["Siscia"]}}
```

Dies sind die Argumente für `search_objects` oder `set_browse_filters`.
Letzteres öffnet `/browse/?Praegeherren=Valens&Muenzstaette=Siscia`.
Listen werden als wiederholte Queryparameter kodiert, Boolean-Werte im
bestehenden Browse-Format `True`/`False`. Pagination wird dabei zurückgesetzt.

Für „in dieser Auswahl“ zuerst `get_current_context` aufrufen und dessen
`filters` explizit an ein Datentool übergeben. Weggelassene Filter behalten die
Remote-MCP-Semantik und werden nicht stillschweigend durch Seitenfilter ersetzt.
Der Kontext liest die URL bei jedem Aufruf neu, auch nach `replaceState`.

```json
{"page_type":"browse","filters":{"Praegeherren":["Valens"]}}
```

Objektkontext enthält zusätzlich `object_id`, `type_id` und `collection_id`.
Typ- und Sammlungskontext liefern die jeweilige ID. Andere Seiten liefern
`other`, Lab `lab`. Tokens, Kontodaten und Präsentationsparameter werden nicht
übermittelt bzw. zurückgegeben. Das optionale Fokus-/Modaltool wurde mangels
einer stabilen bestehenden gemeinsamen UI-Funktion nicht implementiert.

## Öffentliche Daten und Begrenzung

Die zuvor vereinbarte Remote-MCP-Freigabepraxis bleibt unverändert:
`Obj.freigabe` wird nach Vorgabe des Auftraggebers vorerst ignoriert, die
bestehende öffentliche Website-Menge ist maßgeblich. Interne Ausgabefelder
und nicht freigegebene Pakete bleiben ausgeschlossen. WebMCP erweitert keine
Datenberechtigungen und benutzt niemals die Login-/Token-Identität des Browsers.
Browser-Fetches verwenden `credentials: omit`.

Es existieren ausschließlich fünf freigegebene Datentoolnamen. Neue Remote-Tools
werden nicht automatisch über die Browserbrücke freigegeben. SQL, ORM-Pfade,
beliebige Modelnamen und generische JavaScript-/URL-Tools gibt es nicht.

Die POST-Endpunkte sind ausdrücklich read-only und deshalb CSRF-exempt:
Sie lesen öffentliche Daten oder erzeugen eine URL, navigieren aber selbst
nicht und führen keine Schreiboperationen aus. JSON-Eingaben sind auf 64 KiB
begrenzt. Fehlerantworten enthalten keine internen Exceptions. Responses sind
`no-store`; die bestehenden Grenzen von 25 standardmäßig bzw. maximal 100
Treffern pro Seite bleiben wirksam, ohne Gesamtlimit. Aggregationen bleiben
serverseitig. Automatisch geladen wird in unterstützten Browsern nur das kleine
Toolmanifest, kein Datenbestand.

## Endpunkte und Aktivierung

- `GET /api/webmcp/manifest/`: fünf gemeinsame Daten- und sechs UI-/Kontextdefinitionen.
- `POST /api/webmcp/data/<tool_name>/`: JSON-Argumente eines freigegebenen Datentools.
- `POST /api/webmcp/navigation/<tool_name>/`: validierte relative Ziel-URL.
- `GET /api/webmcp/context/?url=<relative-page-url>`: öffentlicher Seitenkontext.

Diese Endpunkte sind bei deaktivierter Einstellung nicht verfügbar (404).

```sh
ELIGIUS_WEBMCP_ENABLED=1
```

Standard ist deaktiviert. Der Schalter ist unabhängig von `ELIGIUS_MCP_ENABLED`;
beide Schnittstellen verwenden dieselben Python-Abhängigkeiten aus
`requirements.txt`. Es ist keine zusätzliche Installation erforderlich.

## Browserunterstützung

WebMCP ist ein sich entwickelnder Webstandard und benötigt einen sicheren
Kontext sowie einen Browser/Agenten mit nativer API. Die Integration benutzt
`document.modelContext`, nicht die frühere `navigator.modelContext`-Variante.
Sie meldet eigene Tools bei `pagehide` per AbortSignal ab und bei Wiederherstellung
aus dem Back/Forward-Cache erneut an. Abgebrochene Aufrufe navigieren nicht.

Primärquellen, geprüft am 13. September 2026:

- [W3C-Community-Entwurf](https://webmachinelearning.github.io/webmcp/)
- [Chrome: imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api)
- [Chrome: Verfügbarkeit und Entwicklungsflag](https://developer.chrome.com/docs/ai/webmcp)

Chrome beschreibt eine experimentelle Aktivierung über
`chrome://flags/#enable-webmcp-testing`; entscheidend ist tatsächlich vorhandene
Feature-Unterstützung. Die normale Eligius-Seite erfordert keine Aktivierung.

## Development-Prüfung

```sh
python manage.py test slg.test_webmcp slg.test_mcp slg.tests.FacetApiTests --settings=djangoproject.test_settings --noinput
node --test scripts/test_webmcp_browser.cjs
python scripts/webmcp_smoke.py https://dev.example.org
```

Die 16 Backendtests prüfen Browse-/Remote-/WebMCP-Parität mit vollständiger
Pagination, Schemagleichheit, alle Datenfunktionen, Navigation, Kontext,
ungültige Eingaben und öffentliche Felder/Pakete. Acht JavaScript-Tests prüfen
den Adapter in einer isolierten Node-VM; ihre Testdoubles sind keine auf der
Webseite installierten Polyfills.

Mit `agent-browser` lässt sich die native Browserregistrierung und Ausführung
zusätzlich prüfen (Chrome mit experimenteller WebMCP-Unterstützung):

```sh
agent-browser --session webmcp open https://46.101.237.189/lab/
agent-browser --session webmcp webmcp list
agent-browser --session webmcp webmcp invoke get_current_context
agent-browser --session webmcp webmcp invoke get_statistics --params '{"filters":{"Praegeherren":["Valens"]}}'
agent-browser --session without-webmcp --no-webmcp open https://46.101.237.189/lab/
```

In den Netzwerkwerkzeugen darf nach dem Laden ohne native Unterstützung kein
Request an `/api/webmcp/` erscheinen. Mit Unterstützung wird zunächst nur das
Manifest geladen. Navigationstools müssen reale Seitenwechsel auslösen und
sich auf der Zielseite erneut registrieren.

### Ergebnis auf Development, 13. September 2026

Die 16 Backendtests bestanden lokal und auf dem Development-Host; alle acht
JavaScript-Tests bestanden. Der öffentliche HTTPS-Paritätscheck bestand für
alle fünf Datentools und Schemas. Im nativen Chrome 152 wurden alle elf Tools
registriert und ausgeführt: Objekt 1271, Typ 2968, Sammlung 1, Browse mit
Valens/Siscia sowie das Zurücksetzen der Filter öffneten die korrekten Seiten.
Der Kontext entsprach nach jedem Seitenwechsel der aktuellen Seite.
Die Valens-Abfrage lieferte 221 Objekte, identisch zur Remote-Schnittstelle.

Ein separat mit `--no-webmcp` gestarteter Browser hatte keine native API,
zeigte den vorgesehenen Lab-Hinweis und erzeugte null WebMCP-API-Anfragen.
Lab wurde auf Desktop und bei 390 Pixeln Breite ohne horizontalen Überlauf
geprüft. Die normale Typseite `/typ/2968/` meldet unabhängig von WebMCP
`Waypoint is not defined` aus ihrem bestehenden Skript. Dieser bestehende
UI-Fehler betrifft nicht die hier geprüfte Navigation oder Toolregistrierung.

## Development-Deployment

Der Auftraggeber bestätigte: `main` deployed automatisch ausschließlich
Development. Änderungen werden deshalb committed und über diesen bestehenden
Weg veröffentlicht. Der WebMCP-Schalter wird nur im Development-Dienst gesetzt;
keine Produktionsänderungen.

Bei der Vorbereitung fiel ein bestehender Deploy-Fehler auf: Der feste
Drei-Sekunden-Check lief vor dem Abschluss des ASGI-Starts und löste alle zehn
Minuten erneut ein Deployment desselben Commits aus. Der Development-Deploy-
Check wartet nun mit begrenzten Retries auf `/health`. Die vorherige Fassung
liegt als Backup neben dem vorhandenen Deployskript auf dem Development-Server.
