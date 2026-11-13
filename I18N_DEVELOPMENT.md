# Deutsch und Englisch für die Oberfläche

## Übersetzte Oberfläche

Übersetzt sind die gemeinsame Navigation und Fußzeile, die Objektsuche mit ihren
Facetten, Suchkategorien, Filtermarkierungen, Datumsauswahl, Diagrammbeschriftungen,
Suchvorschlägen und Leerzuständen. Ebenso die Beschriftungen der Objekt-/Typdetails,
Sammlungsansichten, Objektkarten, Personen-/Nominaldialoge, Paketansichten und
Neuerschließungen sowie zentrale Startseitenbeschriftungen.
Redaktionelle Projekt-/Rechtstexte, Lab-Anleitungen und interne Verwaltungsformulare
sind damit noch nicht vollständig übersetzt.
Sammlungsdaten, Normdaten, Eigennamen und wissenschaftliche Beschreibungen werden
nicht automatisch übersetzt. Es gibt keine Datenmigration.

## Sprachwahl und stabile Identifikatoren

`LocaleMiddleware` berücksichtigt zuerst das Sprachcookie, anschließend die
Browsersprache; Deutsch ist der Fallback. Unterstützt sind `de` und `en`.
Die DE-/EN-Schaltflächen funktionieren ohne JavaScript und speichern die Wahl
für ein Jahr. Der POST-Endpunkt `/i18n/setlang/` ist CSRF-geschützt und erlaubt
nur diese beiden Sprachen. Vorhandene URLs, URI-Namensräume, Slugs, Filterparameter
und Routennamen bleiben unverändert. Keine `i18n_patterns` und keine Sprachpräfixe.

Der Redirect übernimmt den sicheren Rücksprungpfad ausdrücklich, statt ihn neu
aufzulösen: Im bestehenden URLconf können doppelte Namen sonst `/` nach `/api/`
umkehren. Sprachwechsel lädt die Seite neu; ungespeicherte Formulareingaben und
Scrollposition werden derzeit nicht wiederhergestellt. URL-Filter bleiben erhalten.
Mit JavaScript übernimmt die Sprachwahl auch seit dem Laden geänderte Filter und
URL-Fragmente. Ohne JavaScript wird der serverseitige Pfad mit Query verwendet.
Die Textsuche stellt Kategorie und Begriff aus der URL wieder her.

Djangos Seitencache trennt bei `USE_I18N=True` nach aktiver Sprache.
Vorgeschaltete Caches müssen `Vary: Accept-Language, Cookie` beachten und dürfen
Seiten nicht ausschließlich nach URL zwischenspeichern.

## Übersetzungen ergänzen

Der versionierte Katalog liegt unter `slg/locale/en/LC_MESSAGES/django.po`.
Die kompilierte `django.mo` wird ebenfalls versioniert und durch den bestehenden
Docker-COPY-Schritt mit ausgeliefert. PO und MO immer gemeinsam aktualisieren;
nach einem Deployment alle Django-/ASGI-Worker neu starten (Katalogcache).

1. Statische UI-Texte mit `{% load i18n %}` und `{% translate "Deutscher Text" %}`
   markieren. Für variable Texte `blocktranslate` mit benannten Platzhaltern und
   für Mengen Pluralformen verwenden. Keine dynamischen Datenbankwerte übersetzen.
2. Python-Beschriftungen mit `gettext_lazy`, Meldungen mit `gettext` markieren.
   Die Filterkonfiguration verwendet `gettext_noop`, damit API-/MCP-Metadaten
   unverändert bleiben; nur die Anzeige im Template wird übersetzt.
   JavaScript verwendet Djangos `gettext` und `interpolate` über `/i18n/ui.js`.
   Dieser Endpunkt nutzt denselben `django`-Katalog wie die Templates.
   JavaScript-Quelltexte sind für `makemessages` zusätzlich in `slg/ui_messages.py`
   mit `gettext_noop` markiert. Neue JavaScript-Texte auch dort ergänzen.
   Übersetzungen mit variablen Inhalten benutzen benannte `%(variable)s`-Platzhalter.
3. Mit installiertem GNU gettext im Projektverzeichnis ausführen:

   ```sh
   python manage.py makemessages -l en --ignore=.venv --ignore=dev-local --ignore=_unused_html_backup
   python manage.py compilemessages -l en
   python manage.py test slg.test_ui_translations --settings=djangoproject.test_settings
   node --test scripts/test_ui_language.cjs
   ```

4. Übersetzungen prüfen, PO und MO zusammen committen, Desktop und schmale Ansicht
   kontrollieren. Fehlende englische Einträge fallen auf den deutschen Quelltext zurück.

Für Windows ohne gettext kann der vorhandene Katalog mit dem optionalen
Entwicklungswerkzeug `polib==1.2.0` kompiliert werden (keine Laufzeitabhängigkeit):

```sh
python -m pip install polib==1.2.0
python -c "import polib; p='slg/locale/en/LC_MESSAGES/django'; polib.pofile(p+'.po').save_as_mofile(p+'.mo')"
```

## Übersetzungsentwürfe über MCP

Der bestehende authentifizierte Editor-MCP (`/mcp/editor`,
`ELIGIUS_EDITOR_MCP_ENABLED=1`) bietet:

- `get_ui_translation_catalog()`: aktuelle englische UI-Texte und deutsche Schlüssel.
- `draft_ui_translations({"Sammlungen": "Collections"})`: prüfbarer Entwurf mit
  Vorher-/Nachher-Werten und PO-Einträgen. Nur bekannte Schlüssel und reiner Text;
  benannte Platzhalter müssen vollständig und unverändert erhalten bleiben.

Beide verwenden die bestehende Editor-Zugriffskontrolle. Der öffentliche MCP
erhält keine neuen Tools. Entwürfe schreiben weder Dateien noch Datenbankeinträge.
Geprüfte Vorschläge werden im Repository in die PO-Datei übernommen, kompiliert,
getestet und regulär ausgeliefert. Ein Repository-/Dateisystem-MCP kann diese
Dateibearbeitung übernehmen; der Eligius-Editor-MCP veröffentlicht sie nicht direkt.
Pluralformen sind über Django grundsätzlich möglich, werden vom MCP-Entwurfstool
aber noch nicht bearbeitet. Die aktuelle Entwurfsvalidierung unterstützt einfachen
Text und benannte `%(variable)s`-Platzhalter.

## Prüfung der zweiten Ausbaustufe

Die Sprach-/MCP-/WebMCP-Regressionstests verwenden die isolierten Testeinstellungen.
Browserprüfung: Suche ändern und absenden, Leerzustand, DE/EN bei aktiven Filtern,
Facetten-Autocomplete und 375-Pixel-Ansicht. Eine doppelte Bootstrap-Einbindung sowie
auf null Pixel initialisierte Select2-Suchfelder wurden dabei korrigiert.
Die Detailansicht wurde zusätzlich mit langen Namen und unvollständigen Daten geprüft.
Die lokale MySQL-Datenbank hatte bei der Prüfung einen älteren Schemastand
(`slg_slg.bildrechte_lizenz` fehlte); für Start-/Detailseiten wurde deshalb eine
separate SQLite-Vorschau mit Testdaten verwendet. Die lokale MySQL-Datenbank blieb
unverändert. Eine Prüfung mit dem aktuellen vollständigen Sammlungsbestand bleibt offen.
