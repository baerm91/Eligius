# DE/EN-Prüfung am Dev-Server – 13. November 2026

Geprüft über Chrome auf http://46.101.237.189/ (im Browser HTTPS).
Die nachfolgend genannten Korrekturen liegen lokal, noch nicht auf dem Dev-Server.
Keine Änderungen an Datenbankinhalten, URLs oder URI-Identifikatoren.

## Tatsächlich durchlaufene Abläufe

- Startseite auf Englisch: Navigation, zentrale Texte, Objektkarten.
- Suche über die Facette Münzstätte: Siscia, 5.818 Treffer.
- Wechsel EN → DE bei unveränderter Such-URL und Trefferzahl.
- Ergänzung der Titelsuche Gallienus: 35 Treffer; erneuter Wechsel auf Englisch
  erhält `/browse/?Muenzstaette=Siscia&q=Gallienus` und beide Filter.
- Öffnen von `/objekt/1416/`, englische Detailbeschriftungen und Desktopdarstellung.
- Browser-Zurück stellt die kombinierte Suche wieder her.
- Suchformular bei 375 Pixel Breite: Beschriftungen und Eingaben lesbar;
  Kategorie Title und Suchbegriff Gallienus wiederhergestellt.
- Nicht vorhandener Titel: 0 Treffer und „No objects found.“; Mint-Filter bleibt.
- Suchchip entfernt: wieder 5.818 Treffer; Reset: 71.265 Treffer.

## Lokale Korrekturen

- Positionsanzeige verwendet eine vollständige Übersetzung mit Platzhaltern:
  „1 of 10“ statt „1 from 10“. Lokal im Browser „1 of 1“ bestätigt.
- Stückzahl-Kürzel und Ersatz-Bildbeschriftungen auf der Startseite übersetzbar.
- Avers-/Revers-Alternativtexte in der Objektansicht übersetzt.
- Motivstatistik: Mengenbeschriftungen, Rang, Zeitraum und Gesamtzeitraum übersetzt.
  Numerische Nullwerte werden bei Prozenten und Jahreszahlen erhalten.
- PO-/MO-Katalog und extrahierbare JavaScript-Schlüssel gemeinsam aktualisiert.

## Automatische Prüfung

- 13 Django-Tests aus slg.test_ui_translations bestanden.
- 2 JavaScript-Tests aus scripts/test_ui_language.cjs bestanden.
- 29 gerenderte Inline-Skriptblöcke mit node --check geprüft: keine Syntaxfehler.
- Diff-Whitespace-Prüfung bestanden.

## Abgrenzung und offene Prüfung

- Die korrigierte Motivstatistik ist noch mit realen Daten nach dem Deployment
  im Browser zu kontrollieren; die lokale Vorschau besitzt keine entsprechende
  Statistik. Lokal wurden Katalogauslieferung und gerenderte JavaScript-Syntax geprüft.
- Personenfunktion „Münzherr/in“, Material, Herstellungsverfahren, Titel und
  wissenschaftliche Beschreibungen kommen aus Daten und bleiben vorerst deutsch.
- Redaktionelle Langtexte und interne Verwaltungsansichten sind nicht vollständig
  übersetzt. Keine vollständige Prüfung aller Seiten oder aller Facettenkombinationen.
- Typdetail und weiteres Nachladen großer Trefferlisten wurden in diesem Dev-Audit
  nicht als eigener Browserworkflow geprüft.
- Auf der Startseite wurde ein d3-cloud-Konsolenfehler beobachtet
  („Cannot set properties of undefined (setting 'cloud')“); die Wortwolken waren
  dennoch sichtbar. Ursache und Script-Ladereihenfolge separat prüfen.

Nächster Schritt: Änderungen regulär auf den Dev-Server deployen, Django-/ASGI-Worker
neu starten und Positionsanzeige sowie Motivstatistik dort erneut kontrollieren.
