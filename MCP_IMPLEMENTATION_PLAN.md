# Eligius Remote MCP – Implementierungsplan

## Phase 1: Befund am bestehenden Code

- `/browse/` ruft `objekt_list_view_mtoa()` auf. Die tatsächlich maßgebliche
  Suchfunktion ist `_get_filtered_mtoa_queryset()` in `slg/views.py`.
  Sie nutzt die vorhandene MySQL-Projektion `MuenztypObjektAnzeige` und
  `MtoaPerson`, einschließlich Rollen, bestimmter/unbestimmter Objekte,
  überlappender Datierung, Referenzen, Merkmalen und öffentlicher Pakete.
- `FILTER_PARAMETERS` beschreibt die fachlichen Filter. `build_filters()` und
  `apply_filters()` arbeiten auf `Obj` und bilden teilweise einen älteren Pfad.
  Insbesondere Personenfilter im Facettenkontext und Datierung sind nicht
  identisch mit der aktuellen Browse-Abfrage. Sie dürfen deshalb nicht zur
  unabhängigen MCP-Suche werden.
- `facet_api` nutzt für einige Dimensionen MTOA, ansonsten den älteren Obj-Pfad.
  Die Aggregation ist bisher auf 50 Werte begrenzt. Für vollständige Analysen
  benötigt die gemeinsame Funktion Pagination nach der Aggregation.
- `stats_api` ignoriert Filter und zählt globale Tabellen. Gefilterte
  Bestandsstatistik muss aus der gemeinsamen Browse-Menge abgeleitet werden.
- `ObjSerializer` und Update-Serializer enthalten `__all__`; auch der vorhandene
  Detailserializer enthält Workflow und temporäre Typdaten. Diese sind keine
  geeignete öffentliche Ausgabe. Wiederverwendbar sind explizite kleine
  Vokabularserializer und Model-Methoden (z. B. öffentliche Objekt-URL).
- `Obj.freigabe` existiert, wird von Browse und ObjektDetail nicht geprüft.
  `Paket.online_freigegeben` wird dagegen ausdrücklich ausgewertet. Die
  fachliche Objektfreigaberegel muss vor Veröffentlichung geklärt werden.
- Django besitzt unveränderte WSGI- und ASGI-Einstiege. Lokal startet bisher
  `runserver`. Die tatsächliche Remote-Prozess-/Proxykonfiguration ist noch
  zu prüfen; Development-URL laut Auftraggeber: https://46.101.237.189/.
- Eine bestehende lokale Änderung in `MuenztypListCreate.get_queryset()`
  (HTTP/HTTPS- und Slash-Varianten) bleibt erhalten.

## Phase 2: kleinster gemeinsamer MVP

1. Bestehende MTOA-Filterfunktion und ihre Zuordnungen in
   `slg/services/search.py` verschieben. Browse und Charts importieren dieselbe
   Funktion. `FILTER_PARAMETERS` bleibt die externe Filter-Whitelist;
   fehlende unterstützte Filter dürfen nicht stillschweigend ignoriert werden.
2. Facetten gemeinsam aus der gefilterten Browse-Menge aggregieren.
   Personenrollen korrekt berücksichtigen, Objekte distinct zählen,
   Facettenwerte paginieren. Browse behält die bisherige Top-50-Antwortform.
   Distribution berücksichtigt alle aktiven Filter und berechnet Anteile
   relativ zur Objektmenge; Mehrfachzuordnungen können über 100 % summieren.
3. Fünf read-only Tools: `search_objects`, `get_object`, `get_facets`,
   `get_distribution`, `get_statistics`. Explizite öffentliche Ausgabefelder,
   Default 25 Treffer, maximal 100 pro Seite, keine Gesamtbegrenzung.
4. Offizielles SDK `mcp==2.2.0` (aktuelle veröffentlichte Version bei Prüfung)
   über Streamable HTTP in den bestehenden ASGI-Einstieg einbinden.
   Stateless, JSON-Antworten, gemeinsamer Lifespan, Host-/Origin-Whitelist
   und öffentliche Basis-URL aus Settings/Environment. Keine zweite Anwendung
   mit eigener Fachlogik. WSGI bleibt als bisheriger Einstieg verfügbar.
5. `/lab/` im bestehenden Seitenlayout: verständlicher Einstieg, Endpoint,
   öffentliche Daten/read-only, fünf Tools und Beispielprompts.
   `/health` als einfacher Service-/Datenbankcheck.
6. Automatisierte Tests mit aussagekräftigen Fixtures: Browse-/MCP-ID-Parität
   für die angeforderten Kombinationen, Personenrollen, unbestimmte Objekte,
   Pagination, Facetten/Anteile, Freigabe und Parameter-Whitelist.
   Zusätzlich SDK-Handshake und Toolaufrufe über echten HTTP-Transport.
7. Nur Development deployen: vorhandenen Dienst/Reverse Proxy zuerst
   untersuchen, dann gezielt ASGI aktivieren bzw. einbinden und HTTPS prüfen.
   Produktion bleibt unberührt. Entwicklerdokumentation mit Konfiguration,
   Beispielen, Tests und späterer Übernahme auf Produktion ergänzen.

## Umsetzung und Verifikation

Der Auftraggeber bestätigte den Development-SSH-Zugang und dass `freigabe`
für diesen MVP ignoriert werden darf. Die bestehende öffentliche Objektmenge
bleibt damit maßgeblich; interne Ausgabefelder und private Pakete sind ausgeschlossen.

Implementiert und auf Development aktiviert: fünf Tools, gemeinsamer Queryservice,
gemeinsame Facetten/Verteilungen, gefilterte Statistiken, Lab und Healthcheck.
Apache leitet weiterhin an denselben Loopback-Port weiter. Der bestehende
systemd-Dienst verwendet nun den ASGI-Einstieg mit Uvicorn. Vorheriges Release
und vorherige Python-Umgebung bleiben unverändert für Rollback verfügbar.

Verifiziert: neun relevante Tests lokal und auf Development, zehn vollständige
Echtdaten-ID-Vergleiche gegen den vorherigen Browse-Code, 32 Facetten sowie
alle fünf Tools mit dem offiziellen SDK-Client über öffentliches HTTPS.
Lab wurde auf Desktop und Mobilgeräten visuell geprüft. Kein Produktionsdeployment.

Die breitere Alttestsuite hat sieben reproduzierte, bereits vorher bestehende
Fehler (Obj-Save-Fixture-Fremdschlüssel und Nomisma-RDF-Pfad). Diese sind nicht
Teil der MCP-Änderung. Der bestehende Nominal-Facettentest besteht nun ebenfalls.
