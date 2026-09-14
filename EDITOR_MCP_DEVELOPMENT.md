# Authentifizierter Editor-MCP

`/mcp/editor` ist ein eigener stateless Streamable-HTTP-Server unter ASGI.
`/mcp` behält seine fünf öffentlichen Lesetools. Der Editor stellt diese
Lesetools ebenfalls bereit und ergänzt interne Abfragen und begrenzte Änderungen.

## Aktivierung und Rechte

Im ASGI-Prozess `ELIGIUS_EDITOR_MCP_ENABLED=1` setzen und neu starten.
Standardmäßig aus, unabhängig von `ELIGIUS_MCP_ENABLED`. Wie beim Public-MCP
müssen `ELIGIUS_MCP_ALLOWED_HOSTS`, `ELIGIUS_MCP_ALLOWED_ORIGINS` und
`DJANGO_ALLOWED_HOSTS` zum Deployment passen. Remote über HTTPS; der Reverse
Proxy muss Authorization weiterreichen. WSGI/runserver bedienen den MCP nicht.

Authentifizierung mit vorhandenen DRF-Tokens:

```text
Authorization: Token <vorhandener DRF-Token>
Accept: application/json, text/event-stream
```

Alternativ Django-Session mit passendem `X-CSRFToken`-Header für POST.
Die bestehende CSRF-Origin-Prüfung bleibt aktiv. URL-Tokens werden nicht
akzeptiert. Kein neuer Token-Speicher oder OAuth-Discovery-Endpunkt; Clients
müssen eigene Authentifizierungsheader oder Sessions unterstützen.

Aktive Benutzer benötigen `slg.change_obj` oder `slg.change_muenztyp`, direkt
oder über Django-Gruppen. Jede Schreibaktion prüft das jeweilige Modelrecht
erneut. `is_staff` allein gewährt keinen Zugriff; aktive Superuser besitzen
beide Rechte. Keine automatische Rechtezuweisung. Die bestehenden Modelrechte
gelten global, nicht pro Sammlung.

## Tools

| Vorschau | Anwenden | Vorschauparameter |
| --- | --- | --- |
| preview_type_assignment | assign_coin_type | object_ids, type_id, optional Typ_unsicher |
| preview_type_removal | remove_coin_type | object_ids |
| preview_coin_type_update | apply_coin_type_update / update_coin_type | type_id, changes |
| preview_update_unidentified_object_data | update_unidentified_object_data | object_ids, changes |
| preview_update_unidentified_legend | update_unidentified_legend | object_ids, changes (avleg/rvleg) |
| preview_update_object_measurements | update_object_measurements | object_ids, changes (gewicht/durchmesser/stempelstellung) |
| preview_update_object_note | update_object_note | object_ids, changes (anmerkung) |
| preview_coin_type_legend | update_coin_type_legend | type_id, changes (avleg/rvleg) |
| preview_workflow_status | set_workflow_status | model (Obj/Muenztyp), record_ids, workflow_id |

Apply nimmt `preview_token` und `confirmed=true` entgegen; Workflow zusätzlich
das gewählte `model`. Ohne Bestätigung keine Änderung. Der Client muss die
Vorschau dem Benutzer vorlegen; der Server kann diese Benutzerinteraktion
nicht verifizieren.

`changes` akzeptiert ausschließlich die in der Toolbeschreibung genannten
Django-Feldnamen. Relationen nehmen IDs, `null` löscht einen Wert. ORM-Pfade
und fremde Felder werden abgelehnt. Django-Feldvalidierung, Dezimalpräzision,
Stempelstellungs-Choices, Datumsreihenfolge und nichtnegative Maße werden
geprüft. Maximal 100 unterschiedliche Objekt-IDs; genau ein Typ pro Typänderung.

Weitere Abfragen: `get_editor_object(object_id)` liefert `object_data` und
`coin_type` getrennt (change_obj erforderlich).
`search_coin_types(mint_id, nominal_id, page)` findet Typen, 25 pro Seite.
Die fünf bekannten Public-Lesetools bleiben verfügbar.

Beispiel für tools/call:

```json
{"name":"preview_type_assignment","arguments":{"object_ids":[123],"type_id":456}}
```

Nach Prüfung der alten/neuen Zuordnung und ausdrücklicher Bestätigung:

```json
{"name":"assign_coin_type","arguments":{"preview_token":"<aus Vorschau>","confirmed":true}}
```

Münzstätte eines Typs ändern:

```json
{"name":"preview_coin_type_update","arguments":{"type_id":456,"changes":{"Mzstaette":789}}}
```

Die Vorschau zeigt Model, alte/neue Werte und Anzahl zugeordneter Objekte.
Es wird ausschließlich Muenztyp geändert. Bei bestimmten Objekten lehnen
Unbestimmten-Tools direkte typbezogene Änderungen ab.

Auch `Muenztyp.link` ist über `preview_coin_type_update` bearbeitbar. Zum
Entfernen `changes: {"link": null}` (alternativ `{"link": ""}`) übergeben,
danach mit dem Vorschau-Token `apply_coin_type_update` ausführen. Neue Werte
unterliegen der bestehenden URL-Feldvalidierung. Für die Typen 2503, 12829,
12728, 11085, 13306 und 13305 wird jeweils eine eigene Vorschau und Bestätigung
benötigt. Die Freischaltung im Code ändert keine bestehenden Daten.

## Speicherung und Konflikte

### Dargestellte Personen am Münztyp

Die Relation ist `Muenztyp → Mztyp_Person → Person`, mit
`idfk_PersonFunktion=2` (bestehende Browse-Semantik für Dargestellte).
`appears_on_rev=true` bedeutet Revers, `false` Avers. Sie hängt nicht an
`rv_bildtyp`. `Obj_Person` ist ein separater Objektkontext.

Für additive Zuweisungen gibt es zwei separate Tools:

```json
{"name":"preview_assign_depicted_person","arguments":{"type_ids":[123,456],"person_id":2622,"side":"rv"}}
```

Die Typ-IDs im Beispiel sind Platzhalter. Bis zu 100 unterschiedliche IDs
(also auch 30 Münztypen) können gemeinsam geprüft werden. Die Vorschau nennt
Person, Funktion, Seite, alte/neue Relationen, bereits vorhandene Zuordnungen
und die Zahl betroffener Objekte. Bestehende Personen auf beiden Seiten und
andere Rollen bleiben erhalten; es wird ausschließlich ergänzt.

```json
{"name":"assign_depicted_person","arguments":{"preview_token":"<aus Vorschau>","confirmed":true}}
```

Benötigt `slg.change_muenztyp` **und** `slg.add_mztyp_person` (die bestehenden
Parent-/Inline-Rechte im Django-Admin). Vorschau und Apply prüfen beide Rechte.
Der komplette Batch wird atomar mit Audit und bestehender MTOA-Projektion
ausgeführt. Der Typ erhält nur einen neuen modified_at-Zeitstempel; Obj,
Obj_Person, Bildtypen und andere Typfelder bleiben unverändert. Keine neuen
Tabellen oder Migrationen. Ist die Relation bereits vorhanden, bleibt der
entsprechende Typ unverändert, ohne doppelten Eintrag oder Audit einer Änderung.
Ein vollständig unveränderter No-op kann wiederholt werden.

Konfliktprüfung umfasst auch den bisherigen Relationsstand (Through-Änderungen
müssen modified_at nicht aktualisieren), die Person, Funktion und die
Objektzuordnungen. Das normale `preview_coin_type_update` akzeptiert weiterhin
keine frei benannten Personenfelder. Nach Deployment und ASGI-Neustart werden
28 statt 26 Editor-Tools registriert. Bestehende Daten werden beim Deployment
nicht zugeordnet.

Keine neuen Models, Tabellen, Migrationen oder Preview-Datensätze.
Modellzuordnung: [EDITOR_MCP_PLAN.md](EDITOR_MCP_PLAN.md). Weitere Personenrollen,
Ersetzungen/Löschungen und Offizinänderungen an bestimmten Objekten gehören
nicht zum Schreibumfang.

Signierte Vorschauen gelten zehn Minuten und binden Benutzer, Aktion und
geprüfte Daten. Apply vergleicht vollständige Hauptzeilen einschließlich
modified_at, bei Typzuweisung den Zieltyp und bei Typänderung die
Zuordnungsmenge. Manipulation, Ablauf, Rechteentzug oder Konflikt erfordern
eine neue Vorschau. Erfolgreiches Apply macht den bisherigen Token ungültig.

Änderung, LogEntry und bestehende MTOA-Projektion werden gemeinsam atomar
gespeichert. Das Audit enthält Benutzer, Zeitpunkt, Model/ID, Aktion und
alte/neue Werte. Die Projektion wird über die bestehende Funktion in Batches
aktualisiert, auch bei mehr als 500 Objekten. Keine Typdatenkopie in Obj.
Gezielte UPDATEs verhindern fachfremde Default-Ergänzungen aus Model.save;
geändert werden nur bestätigte Felder und modified_at. Fehler im Audit oder
Projektionsaufbau rollen alles zurück.

## Tests

```powershell
.venv/Scripts/python.exe manage.py test slg.test_editor_persons slg.test_editor_mcp slg.test_mcp slg.test_webmcp --settings=djangoproject.test_settings --noinput
```

Isolierte SQLite-Testdatenbank: echte HTTP-MCP-Aufrufe für Token-/Session-Auth,
CSRF und Preview/Apply; Service-Tests für Modellgrenzen, Audit, Konflikte,
Replay und Bulk-Rollback. Bestehende Public-/WebMCP-Tests laufen mit.
MySQL-spezifische parallele Transaktionen sind in der Deployment-Umgebung
gesondert zu prüfen. Die Tests verbinden sich nicht mit der Entwicklungsdatenbank.

Der zusätzliche vollständige Lauf (`test slg`) enthält sieben unabhängig
reproduzierbare Bestandsfehler in `slg.tests`: vier ObjSave-Testfixtures mit
fehlenden Standard-Fremdschlüsseln und drei RDF-Tests wegen des Query-Pfads
`obj_ref_set` statt `obj_ref`. Diese fachfremden Stellen wurden nicht geändert.
