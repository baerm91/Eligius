# WebMCP – Architekturprüfung und Umsetzung

## Phase 1: geprüfter Bestand

- Remote MCP registriert fünf typisierte Funktionen in `slg/mcp_server.py`.
  Das offizielle SDK kann deren JSON-Schemas über die öffentliche Methode
  `list_tools()` liefern und dieselben Funktionen über `call_tool()` ausführen.
  Eine zweite Schema- oder Dispatcherimplementierung ist unnötig.
- Alle fachlichen Operationen laufen über `slg/services/public_api.py` und
  `slg/services/search.py`. `FILTER_PARAMETERS` und `filter_request()` bilden
  die bestehende Parameterprüfung; die MTOA-Abfrage bestimmt die Browse-Menge.
- Vorhandene Facet-/Stats-REST-Views haben teilweise ältere Antwortformen;
  Objekt-REST-Views enthalten Bearbeiterfunktionen. Für exakte Parität wird
  eine kleine, auf fünf Namen beschränkte öffentliche JSON-Brücke ergänzt.
- Browse verwendet wiederholte URL-Queryparameter für Mehrfachwerte und
  `True`/`False` für den Modus unbestimmter Objekte. Die UI navigiert bzw.
  aktualisiert `history.replaceState`; die aktuelle URL ist daher maßgeblich.
- Öffentliche Detailrouten sind benannt: `Objekt`, `Typ`, `Sammlung`,
  `Objektliste`. URLs werden serverseitig mit `reverse()` erzeugt.
- Die frühere Freigabeentscheidung gilt weiter: `Obj.freigabe` wird nach
  Vorgabe des Auftraggebers vorerst ignoriert. Die bestehende öffentliche
  Menge, explizite öffentliche Ausgabefelder und Paketfreigabe bleiben erhalten.
- Keine stabile gemeinsame Objekt-Fokus-/Modal-API vorhanden. Das optionale
  `show_object_in_current_context` wird deshalb nicht eingeführt.
- Aktuelle native API laut W3C-Entwurf: `document.modelContext.registerTool`,
  asynchrone Registrierung und Abmeldung über AbortSignal. Keine Polyfills.

## Phase 2: konkrete Umsetzung

1. Manifest aus den bestehenden fünf SDK-Tooldefinitionen; Input-Schemas
   unverändert übernehmen. HTTP-Aufrufe führen dieselben SDK-Tools aus.
2. Fünf eng begrenzte UI-Tools für Objekt, Typ, Sammlung und Browse-Filter.
   IDs/Filter serverseitig validieren, nur öffentliche benannte URLs erzeugen.
3. `get_current_context` ermittelt bei Aufruf anhand der aktuellen URL
   Seitenart, IDs und aktive zulässige Filter; keine Kontodaten oder Tokens.
4. Kleine optionale Browserdatei auf öffentlichen Seiten. Ohne native API
   keine Registrierung und keine API-Datenabrufe. Abbruch-/BFCache-Verhalten
   berücksichtigen; Daten nie automatisch vorladen.
5. Lab erklärt Remote MCP und WebMCP knapp als zwei Zugänge. Technische
   Details in separater Dokumentation.
6. Backend-Parität, Whitelists, öffentliche Felder, URLs, Browserregistrierung,
   Navigation und Verhalten ohne native Unterstützung testen. Nur Development
   als neues Release veröffentlichen, bestehenden Remote MCP nachprüfen.
