# Prüffähiger Übersetzungsbestand

Dieser Schritt erzeugt lokale Vorschläge aus einem gespeicherten Normdatenexport.
Er verbindet sich nicht mit der Eligius-Datenbank und verändert keine Website.
Ein vorgeschlagenes Entitätslabel ist keine vollständige Übersetzung eines
lokalen Titels, einer Beschreibung oder eines bibliografischen Zitats.

## Ausführen

```sh
python scripts/build_authority_proposals.py --inventory dev-local/authority-audit-dev/inventory-full.json --output dev-local/authority-proposals-dev
python manage.py test slg.test_authority_inventory slg.test_authority_proposals --settings=djangoproject.test_settings
```

Für größere Bestände bevorzugt den offiziellen Nomisma-Datenbestand lokal holen:

```sh
git clone --depth 1 --filter=blob:none --sparse https://github.com/nomisma/data.git dev-local/nomisma-authority-source
git -C dev-local/nomisma-authority-source sparse-checkout set id
python scripts/build_authority_proposals.py --inventory dev-local/authority-audit-dev/inventory-full.json --output dev-local/authority-proposals-dev --nomisma-repo dev-local/nomisma-authority-source
```

Der Lauf liest die versionierten Git-Objekte direkt. So bleiben auch auf Windows
Kennungen korrekt getrennt, deren Dateinamen sich nur durch Groß-/Kleinschreibung
unterscheiden. Commit-ID, Datei-Hash und dauerhafte GitHub-Quellenlinks werden
mitgespeichert. Der Arbeitsbaum des externen Checkouts wird nicht verändert.
Nomisma beschreibt dieses Repository als kanonischen RDF-Bestand:
https://github.com/nomisma/data.

Gleicher Ausgabepfad bedeutet Wiederverwendung des Abrufcaches. Ein neuer
Ausgabepfad erzeugt einen neuen Quellenstand. Rohantworten werden mit Abrufzeit,
URL und SHA-256 gespeichert. Fehlgeschlagene Abrufe werden nicht gecacht;
ein erneuter Lauf versucht sie wieder. Maximal drei gleichzeitige Abrufe und
zwei Request-Starts pro Sekunde, Nomisma gesammelt in Gruppen von 40 Kennungen.
Keine KI- oder kostenpflichtigen Übersetzungsaufrufe.
RDF-Datumswarnungen zu BCE-Jahren werden zusammengezählt statt einzeln ausgegeben;
der Lauf verarbeitet ausschließlich Bezeichnungen und Identitätsverweise, keine
Datumswerte. Die unveränderten RDF-Quellen bleiben erhalten.

## Ergebnisse

- `proposals.json`: maßgeblicher Datenbestand inklusive Originalwerten, IDs,
  ursprünglichen URI-Feldern, Quellennachweisen, Varianten und Prüfhinweisen.
- `review.csv`: kompakte Prüfliste, eine Zeile je lokalem Datensatz. Felder, die
  Tabellenprogramme als Formel auslegen könnten, erhalten ein Schutzapostroph;
  der unveränderte Wert steht in JSON.
- `changes.csv`: nur Vorschläge, die vom lokalen Text abweichen; hier beginnt
  die Textprüfung. Gleiche Labels erfordern keine Textänderung, gelten dadurch
  aber nicht automatisch als fachlich oder hinsichtlich ihrer URI bestätigt.
- `open.csv`: Fälle ohne englischen Vorschlag.
- `review.md`: lesbare Übersicht mit Links zu den Prüflisten.
- `summary.json`: Abdeckung, Prüfhinweise und Abruffehler.
- `cache/`: nachvollziehbare Rohantworten für Wiederholungen und Stichproben.

Die Dateien bleiben unter dem ignorierten `dev-local/`; der vollständige Export
einschließlich unbenutzter Normdatensätze wird nicht veröffentlicht.

## Regeln

Nomisma liefert nur explizite englische Labels der angefragten Entität. GND-Namen
ohne Sprachkennzeichen werden nur als Evidenz gespeichert. Für GND werden
ausschließlich explizite `owl:sameAs`-/`skos:exactMatch`-Verweise zu Wikidata
verfolgt, kein Namensabgleich. Eine Wikidata-Rückverknüpfung über P227 wird geprüft
und fehlende Bestätigung markiert. Keine rekursive Suche über weitere Quellen.
Wikipedia-Artikel werden in diesem Schritt nicht auf Wikidata abgebildet.

Pro lokalem Datensatz werden alle vorhandenen Referenzen gemeinsam betrachtet.
Abweichende Labels werden nebeneinander festgehalten. Nomisma hat lediglich bei
der Vorauswahl des anzuzeigenden Vorschlags Vorrang; Konflikte bleiben sichtbar.
Gleiche URI bedeutet nicht, dass lokale Datensätze zusammengeführt werden.

Jeder Vorschlag bleibt `pending_review`, jeder Fall ohne Label `unresolved`.
`approved` ist immer `false`. Der Hash des Originalstands erlaubt einem späteren
Import, inzwischen geänderte Ausgangsdaten zurückzuweisen. Ein solcher Import
in die Datenbank ist hier noch nicht enthalten. Die HTML-Prüfseite speichert
Entscheidungen separat; die ursprünglichen Vorschläge bleiben unverändert.

## HTML-Prüfseite

Jeder Vorschlagslauf erzeugt `pruefung.html`. Die Datei lässt sich lokal im
Browser öffnen und benötigt keinen Server. Für einen vorhandenen Export:

```powershell
.venv\Scripts\python.exe scripts/render_authority_review.py dev-local/authority-proposals-dev/proposals.json dev-local/authority-proposals-dev/pruefung.html
```

Die Seite bietet Suche, Filter, Original und bearbeitbare englische Bezeichnung,
Quellenvergleich, Prüfnotizen sowie Bestätigen, Zurückstellen und Ablehnen mit
Wechsel zum nächsten Datensatz. Strg+Enter bestätigt; Rückgängig nimmt die letzte
Entscheidung zurück. Bearbeitete Texte werden als Entwurf gespeichert.

Prüfstand und Auswahl bleiben im lokalen Browserspeicher erhalten, sofern dieser
verfügbar ist. Regelmäßig **Prüfstand exportieren** verwenden: Die JSON-Datei ist
eine übertragbare Sicherung. **Prüfstand laden** übernimmt passende Entscheidungen;
bei abweichendem Bestands- oder Originalhash wird die Datei vollständig abgelehnt.
Ein Import ersetzt passende lokale Entscheidungen und ist rückgängig machbar.
Keine dieser Aktionen schreibt in die Datenbank oder veröffentlicht Labels.
Die HTML-Datei enthält Bestandsdaten und ist nicht für öffentliche Ablage bestimmt.

## Prüfhinweise lesen

| Hinweis | Bedeutung |
| --- | --- |
| source_label_conflict | Quellen liefern verschiedene Labels. |
| check_person_name_and_titles | Abweichender Personenname; Titel und Zusätze vergleichen. |
| numbers_or_ordinals_missing | Zahlen oder römische Ordnungszahlen fehlen im Vorschlag. |
| check_parenthetical_information | Klammerzusätze im Original müssen erhalten bleiben. |
| preserve_uncertainty | Original enthält mögliche Unsicherheits- oder Ergänzungszeichen. |
| possible_german_catalogue_text | Trotz Sprachkennzeichen möglicherweise deutscher Katalogtext. |
| preserve_bibliographic_citation | Literaturzitat nicht durch ein Normdatenlabel ersetzen. |
| gnd_link_not_reciprocated | Wikidata bestätigt die verknüpfte GND-ID nicht. |
| unresolved_reference | Linkformat oder Quelle wird noch nicht aufgelöst; nicht automatisch fehlerhaft. |
| no_explicit_english_label | Kein verwendbarer englischer Vorschlag verfügbar. |
| source_fetch_or_parse_error | Quelle konnte nicht erfolgreich gelesen oder verarbeitet werden. |
| source_record_missing | Die Kennung ist im verwendeten Nomisma-Quellenstand nicht vorhanden. |

Die Textprüfungen sind Heuristiken. Fehlende Hinweise belegen keine fachliche
Richtigkeit. Gleichlautende Labels können korrekt sein, sind aber ebenfalls
noch nicht freigegeben.
