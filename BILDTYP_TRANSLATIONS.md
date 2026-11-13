# Englische Bildtypbeschreibungen

AvBildtyp und RvBildtyp behalten `name` unverändert. `name_en` enthält die
redaktionell gespeicherte englische Beschreibung (bis 500 Zeichen).
Migration `0104_bildtyp_english` vor dem Start des neuen Codes ausführen.
Diese Änderung ist lokal implementiert; sie deployt oder migriert keinen Server.

## Bearbeiten und austauschen

Im jeweiligen Django-Admin stehen Original und bearbeitbare Übersetzung
nebeneinander. Filter „Englische Übersetzung: Fehlt“ und Suche über beide Sprachen
helfen bei der Stapelbearbeitung. Mit „Sichern“ werden die Änderungen gespeichert.

Für Export Zeilen auswählen und Aktion „Ausgewählte … exportieren“ verwenden.
CSV, XLSX und JSON stehen über django-import-export zur Verfügung. Nur `name_en`
bearbeiten; `id`, `name` und `revision` unverändert lassen. Importieren zeigt eine
Vorschau und benötigt eine Bestätigung. Leere Übersetzungszellen bleiben unverändert;
zum gezielten Löschen das Admin-Feld leeren. Unbekannte/doppelte IDs und geänderte
Ausgangsdaten brechen den Import ab, ohne Teiländerungen zu speichern. Der Hash
umfasst Modell, ID, Original und bisherigen englischen Text: auch Exporte der
falschen Seite und inzwischen korrigierte Übersetzungen werden zurückgewiesen.
Normale Admin-Änderungsprotokolle gelten auch für gespeicherte Übersetzungen.

## MCP-Entwürfe

Nur der authentifizierte Editor-MCP bietet `get_bildtyp_translation_batch`
(Seite `av`/`rv`, maximal 50 Zeilen, Cursor `after_id`, standardmäßig nur fehlende)
und `draft_bildtyp_translations`. Zusätzlich zu den Editorrechten ist das jeweilige
Modelländerungsrecht nötig. Der Entwurfsaufruf prüft die Originalstände und liefert
JSON für den oben beschriebenen Admin-Import. Er schreibt nichts in die Datenbank;
maschinelle Entwürfe werden dadurch nicht automatisch veröffentlicht.

## Anzeige und Grenzen

Objekt-/Typdetails, die Schlagwort-Detailseiten und Bildtyp-Facetten verwenden bei
englischer Sprachwahl das englische Feld, andernfalls das Original. Facetten-IDs,
URLs und Filterwerte bleiben unverändert. `__str__`, Originalfelder, bestehende
Rohdatenexporte und REST-`name`-Felder bleiben deutsch; diese Änderung ist keine
vollständige Übersetzung aller Ausgabewege.

Der automatische Bezug von Normdatenlabels (Nomisma/Wikidata/GND) ist weiterhin
ein separater, noch nicht in die öffentliche Anzeige integrierter Arbeitsstand.
Die lokale HTML-Prüfseite stellt keine Veröffentlichung dar.
