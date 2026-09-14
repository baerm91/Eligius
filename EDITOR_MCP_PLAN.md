# Editor-MCP: Modellprüfung und Implementierungsplan

## Bestehende Strukturen

Geprüft: `slg/models.py`, `filter_config.py` (default/unbestimmt), Browse/MTOA,
Serializer, Forms, Admin, Authentifizierung und Signals. Keine neuen Models,
Tabellen oder Migrationen erforderlich. Django Users/Groups/Permissions regeln
den Zugriff; `django_admin_log` dokumentiert Änderungen. `ObjektAenderung`
bildet öffentliche Korrekturvorschläge ab, ist auf Obj begrenzt und deshalb
für ausgeführte Bearbeiteraktionen weniger passend als LogEntry.

| Fachangabe | Bestimmtes Objekt | Unbestimmtes Objekt | Einordnung |
| --- | --- | --- | --- |
| Münzstätte | Typ.Mzstaette | Obj.idfk_Mzstaette | A/C |
| Nominal | Typ.Nominal | Obj.idfk_Nominal | A/C |
| Material | Typ.Metall | Obj.Metall | A/C |
| Datierung | Typ.dat_von/dat_bis/dat_verb | gleichnamige Obj-Felder | A/C |
| Av./Rv.-Legende | Typ.avleg/rvleg | Obj.avleg/rvleg | A/C |
| Av./Rv.-Bildtyp und Beschreibung | Typ.av_bildtyp/rv_bildtyp, avbeschr/rvbeschr | gleichnamige Obj-Felder | A/C |
| Beizeichen | Typ.av_beizeichen/rv_beizeichen | gleichnamige Obj-Felder | A/C |
| Offizin | Typ.av_offizin_symbol/rv_offizin_symbol | Obj besitzt eigene Symbolfelder sowie av_offizin/rv_offizin | D |
| Personen/Funktionen | Mztyp_Person mit Person, Funktion, appears_on_rev | Obj_Person mit eigenem Kontext | D |
| Gewicht, Durchmesser, Stempelstellung | Obj | Obj | B |
| Anmerkung, Workflow | jeweils am angesprochenen Model | jeweils am angesprochenen Model | D |

Objekt-Offizinen bleiben auch bei Typzuweisung erhalten (ObjInventorySerializer
zeigt insbesondere Obj.rv_offizin). Personen sind keine einfachen FK-Felder:
ihre Through-Modelle werden nur durch gezielte Relationsaktionen bearbeitet.
`preview_assign_depicted_person` / `assign_depicted_person` ergänzen fehlende
Mztyp_Person-Zuordnungen mit der bestehenden Funktion 2 auf explizit gewähltem
Avers oder Revers. RvBildtyp besitzt keine Personenrelation. Dafür gelten
change_muenztyp und add_mztyp_person wie für die Parent-/Inline-Bearbeitung im Admin.
Unbestimmten-Tools lehnen sämtliche Änderungen bei gesetztem Typ ab; damit
werden auch kontextsensitive Symbol-/Beizeichenfelder konservativ behandelt.

## Umsetzung

1. Eigener MCP-Server `/mcp/editor`, separat aktivierbar. Bestehende DRF-Tokens
   im Authorization-Header; Django-Sessions mit CSRF-Prüfung. Keine URL-Tokens:
   QueryParamTokenAuthentication ist vorhanden, wird für Schreibzugriffe wegen
   URL-/Proxy-Logs bewusst nicht übernommen. Kein neuer Authentifizierungsspeicher.
2. Aktive Benutzer mit `slg.change_obj` oder `slg.change_muenztyp` dürfen den
   Editor verwenden. Jede Aktion prüft die konkrete Model-Permission erneut;
   dieselben globalen Modelrechte wie im bestehenden Admin, keine neue Rolle.
3. Enge Feldlisten und Django/DRF-Feldvalidierung. Jede Änderung erhält eine
   Vorschau; signierter, kurzlebiger Token bindet Benutzer, Aktion, IDs, Werte,
   vollständigen bisherigen Zeilenstand einschließlich modified_at und Typwirkung.
4. Apply unter transaction.atomic und Zeilensperren; erneute Validierung und
   Konfliktprüfung. Alle Bulk-Zeilen werden vor dem ersten Schreiben geprüft.
   Aktualisierung nur der bestätigten Felder und modified_at mittels gezieltem
   UPDATE. Dadurch werden die Default-Ergänzungen in Model.save (Datum, Titel,
   Nominal→Material) nicht bei fachfremden Einzelaktionen ausgelöst. Keine
   Typ→Obj-Kopie. Bestehende MTOA-Projektion wird explizit synchronisiert.
5. LogEntry enthält Benutzer, Zeitpunkt, Aktion, Model/ID und alte/neue Werte;
   Audit und Projektion gehören zur selben Transaktion. Vorschauzustände werden
   nicht gespeichert. Geänderter Zeilenstand verhindert erneutes Apply.
6. Service- und Transporttests für Auth, CSRF, Rechte, Modellgrenzen, unveränderte
   öffentliche Tools, Konflikte, Rollback und Audit in isolierter Testdatenbank.

## Grenzen

Keine neuen Tabellen. Keine beliebigen ORM-/SQL-/Feldoperationen. Keine
Löschung/Ersetzung von Personenrollen, keine Obj_Person-Bearbeitung oder
Bearbeitung bestimmter Objekt-Offizinen in diesem Umfang.
Die Dargestellten-Aktion prüft zusätzlich den vollständigen bisherigen
Mztyp_Person-Relationsstand, Person, Funktion und Objektzuordnungen und führt
bis zu 100 Typzuweisungen atomar aus. Bereits vorhandene Relationen sind No-ops.
Die vorhandene MTOA ist eine bereits bestehende Anzeigeprojektion,
keine Speicherung von Typangaben in Obj. Gleichzeitige externe Änderungen
an Relationen/Lookup-Bezeichnungen ohne Sperrkonvention können eine Vorschau
veralten lassen; Apply prüft Hauptzeilen, Zieltyp und aktuelle Zuordnungsmenge.
