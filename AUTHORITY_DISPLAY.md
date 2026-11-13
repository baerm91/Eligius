# Automatische englische Normdatenanzeige

Die sichtbaren Labels werden bei englischer Sprachwahl anhand der gespeicherten
Nomisma-, Wikidata- und GND-Kennungen aufgelöst. Originalnamen, URI-Felder,
Filterwerte und URLs werden nicht überschrieben. Priorität: Nomisma, Wikidata,
GND; fehlende englische Labels fallen auf das Original zurück. GND-Verweise auf
Wikidata werden nur mit bestätigtem Rückverweis verwendet. Unterschiedliche
Namensformen aus verschiedenen Quellen benötigen keine manuelle Freigabe.

## Quellenbestand installieren

Der vorhandene `scripts/build_authority_proposals.py` ruft Normdaten gebündelt und
mit Cache ab. Danach installiert folgender Befehl nur die englischen Quellennamen
und ihre Nachweise, ohne lokale Katalogtexte oder Freigabeentscheidungen:

```sh
python manage.py install_authority_labels /path/to/proposals.json
```

`ELIGIUS_AUTHORITY_LABELS_PATH` konfiguriert die JSON-Datei; Standard ist
`BASE_DIR/var/authority-labels.en.json`. Auf Dev liegt sie unter
`/djangoproject/shared/authority-labels.en.json` und überlebt Releases.
Eine Aktualisierung ersetzt die Datei atomar. Seitenaufrufe benötigen keine
externen Normdatenanfragen. Der Quellenbestand ist ein nachvollziehbarer Snapshot;
neu verknüpfte, darin noch fehlende URIs verwenden bis zum nächsten Abruf das Original.

Templates verwenden `display_label` für Modellinstanzen und `authority_text` für
die vorhandenen denormalisierten Suchkarten. Die Tabellenzuordnung wird maximal
60 Sekunden zwischengespeichert und bei lokalen Änderungen sofort invalidiert.
Gleichnamige Einträge mit verschiedenen Übersetzungen bleiben in textbasierten
Suchkarten beim Original, während ID-basierte Detailseiten korrekt auflösen.

Facetten liefern das unveränderte `name` als Filterwert sowie bei abweichendem
englischen Text ein zusätzliches `label`. Die Oberfläche verwendet `label` für die
Anzeige und sucht in beiden Sprachen. REST-Serializer ergänzen `display_name`,
ohne bestehende `name`-Felder umzudeuten. Literaturnachweise, Legenden und freie
Beschreibungen werden nicht durch den Namen einer referenzierten Entität ersetzt.
Av-/Rv-Bildtyptexte verwenden die separat gepflegten `name_en`-Felder.

## Prüfung

```sh
python manage.py test slg.test_authority_display slg.test_bildtyp_translations slg.test_ui_translations slg.test_mcp --settings=djangoproject.test_settings
```

Prüft Sprachwechsel, Original-/URI-Erhalt, englische Facettensuche, unveränderte
Filterwerte und Zählungen, Quellenfallback, Cache-Invalidierung und getrennte
Bildtypübersetzungen. Liveprüfung erfolgt auf Dev; Produktion wird nicht verändert.
