# Normdaten-Pilot auf dem Dev-Server

Stand: 13. November 2026. Ausschließlich lesende HTTP-Abfragen und lokale
Berichtsdateien; keine Datenbankänderungen, keine Deployment-Änderungen.

## Ergebnisse

Quelle: http://46.101.237.189. Vollständige öffentliche Listen-APIs für
Münzstätten und Nominale, nicht die Zahl tatsächlich verwendeter Facettenwerte.

| Tabelle | Einträge | Normdatenfeld befüllt |
| --- | ---: | ---: |
| Münzstätten | 2.471 | 2.062 |
| Nominale | 461 | 305 |

2.366 erkannte Nomisma-Verweise auf 2.364 unterschiedliche Kennungen. Die
Mehrfachverwendung führt nicht zu einer automatischen Zusammenführung lokaler
Datensätze. 565 Einträge besitzen kein befülltes Normdatenfeld.

Ein nicht verwertbarer Wert: Münzstätte Nantes, ID 6789, enthält im Feld
`name_nom_id` den Text `Frankreich / Departement Loire-Atlantique`.
Dieser Wert wurde nur gemeldet, nicht geändert. Apostrophe in Nomisma-Kennungen
werden unterstützt, beispielsweise `ba'albakk`.

Pilot: je 20 unterschiedliche Nomisma-Kennungen aus den beiden Tabellen,
deterministisch über die sortierten Kennungen verteilt. Alle 40 lieferten genau
ein explizites englisches `skos:prefLabel`. Das ist keine zufällige Stichprobe und
keine Schätzung einer Fehlerquote oder Garantie für den Gesamtbestand.

Drei explizite Identitätsverweise wurden zu Wikidata verfolgt:
Cistophorus (Q747909), Quinarius (Q1249084), Shekel (Q1404428).
Alle drei lieferten englische Labels. Quellen bleiben getrennt; abweichende
Schreibweisen werden nicht still vereinheitlicht. Der Action-API-Abruf antwortete
in dieser Umgebung mit 403, der dokumentierte EntityData-Zugang funktionierte.

GND: technischer Abruf einer separaten Testkennung `118540238` mit RDF-
Content-Negotiation erfolgreich. Diese Kennung stammt nicht aus dem Dev-Export;
daraus folgt keine Aussage zur GND-Abdeckung des Eligius-Bestands.
Die Dev-Personenliste `/api/person/` antwortet ohne Anmeldung mit 401.
Ihr Serializer liefert zudem weder DNB- noch Wikipedia-Felder.
Ein echter GND-Datenpilot bleibt deshalb bis zum vollständigen Export offen.
Ein unmarkierter GND-Vorzugsname darf nicht als englische Übersetzung gelten.

## Wiederholen

Im Projektverzeichnis, mit installierten Projektabhängigkeiten:

```sh
python scripts/audit_authority_labels.py --base-url http://46.101.237.189 --output dev-local/authority-audit-dev --follow-wikidata
python manage.py test slg.test_authority_inventory --settings=djangoproject.test_settings
```

Ausgaben: `report.json`, die beiden API-Listen, Nomisma-RDF und Wikidata-JSON.
Der Lauf holt Daten neu; es gibt noch keinen dauerhaften Aktualisierungsdienst.
Nomisma wird in Gruppen von 20 Kennungen angefragt. Keine LLM-Aufrufe und keine
kostenpflichtigen Übersetzungsdienste. Einzelne Wikidata-Abruffehler bleiben als
Fehler im Bericht sichtbar. Ein fehlgeschlagener Nomisma-Abruf bricht den Lauf ab.

## Nächster Schritt auf Dev

Die neue Command-Datei und `slg/services/authority_inventory.py` auf dem Dev-Server
bereitstellen, dann im bestehenden Django-Anwendungsumfeld ausführen:

```sh
python manage.py export_authority_inventory > authority-inventory-dev.json
```

Der Befehl liest nur ausgewählte Spalten der vorhandenen Normdatentabellen,
führt keine Netzwerkaufrufe durch und schreibt keine Datenbankwerte. Er benötigt
keine Migration. Enthalten sind Originalwerte, lokale IDs, Feldnamen und
Abdeckungszahlen; auch unbenutzte Normdatensätze werden erfasst. Wikipedia-Links
werden zur späteren Identitätsauflösung festgehalten, nicht als Wikidata-URIs
umgedeutet. Der Export gehört nicht in ein öffentliches Webverzeichnis.

Danach GND-/Personen-Verweise aus genau diesem Export prüfen, Quellenkonflikte
anzeigen und einen Vorschlagsimport mit Herkunft und Prüfstatus ergänzen.
Erst nach Prüfung auf Dev denselben Ablauf explizit gegen Produktion ausführen.

## Prüfungen und Grenzen

Sechs Tests für URI-Erkennung, unveränderte Originale, Entitätenzuordnung,
Sprachkennzeichnung und Django-Export. Keine UI geändert, daher kein neuer
Browserworkflow. Noch keine Übersetzungen in Eligius gespeichert oder angezeigt.
Vor dem Wechsel zu Dev wurden Produktionstatistik und öffentliche Listen lesend
abgerufen. Die oben angegebenen Ergebnisse stammen ausschließlich vom Dev-Lauf.
