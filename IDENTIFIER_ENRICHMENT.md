# GeoNames-, GND- und VIAF-Anreicherung

Füllt **leere** Felder `Mzstaette.geonames`, `Person.DNB` und `Person.VIAF` aus
expliziten Identitätsverweisen. Kein Namensabgleich, bestehende Werte werden nie
überschrieben.

## Regeln

1. Quelle ist der Nomisma-Datensatz der lokalen Nomisma-ID
   (`skos:exactMatch`/`skos:closeMatch` auf GeoNames, GND, VIAF).
2. Nur wenn Nomisma für das Feld **keinen** Verweis hat: das von Nomisma verlinkte
   Wikidata-Item (P1566 GeoNames, P227 GND, P214 VIAF; bevorzugter Rang zählt,
   veraltete Werte nicht).
3. Genau ein eindeutiger Wert → `auto` (wird geschrieben). Mehrere Werte →
   `review` (landet in `review.csv`). Kein Wert → `none`.
4. Feld schon befüllt → `present`; weicht der Nomisma-Wert ab →
   `present_differs` (nur gemeldet, nie geändert).

Gespeichert wird `geonames` als reine ID, `DNB` als `https://d-nb.info/gnd/{id}`,
`VIAF` als `https://viaf.org/viaf/{id}`. Der EDM-Export gibt GeoNames als
`https://sws.geonames.org/{id}/` aus (dereferenzierbares Europeana-Muster).

## Ablauf

Auf dem Server (nur lesend):

```sh
python manage.py export_identifier_inventory > identifier-inventory.json
```

Lokal (Nomisma-Checkout wie in `AUTHORITY_PROPOSALS.md`, Netz für Wikidata):

```powershell
.venv\Scripts\python.exe scripts/build_identifier_proposals.py --inventory identifier-inventory.json --output dev-local/identifier-proposals --nomisma-repo dev-local/nomisma-authority-source
```

`--skip-wikidata` lässt den Wikidata-Schritt weg (offline). Ergebnis:
`proposals.json` (maßgeblich), `review.csv` (mehrdeutige Fälle), `summary.json`,
`cache/` (Wikidata-Rohantworten).

Wieder auf dem Server:

```sh
python manage.py apply_identifier_proposals proposals.json            # Vorschau
python manage.py apply_identifier_proposals proposals.json --apply    # schreiben
```

Geschrieben wird nur, wenn das Zielfeld noch leer ist und die Nomisma-ID seit dem
Export unverändert ist; sonst wird der Datensatz übersprungen und gezählt. `--apply`
legt `applied-<Zeit>.json` mit alten und neuen Werten neben `proposals.json` ab
(Grundlage für ein Zurücksetzen).

Mehrdeutige Fälle: in `review.csv` die Spalte **Entscheidung** mit der gewählten ID
(oder URI) füllen, `-` oder leer = auslassen, dann

```sh
python manage.py apply_identifier_proposals proposals.json --decisions review.csv --apply
```

## Nebenwirkungen

- Kein MTOA-Neuaufbau: die Felder stehen nicht in der Projektion. Für betroffene
  Objekte wird nur der OAI-Zeitstempel (`last_modified`) vorgezogen, damit
  Kulturpool sie beim nächsten inkrementellen Harvest neu holt. Dasselbe gilt jetzt
  für Admin-Speicherungen mit `update_fields` ⊆ {`name_en`, `name_nom_id`,
  `geonames`, `DNB`, `VIAF`}.
- `DNB` gehört zu den Referenzfeldern freigegebener englischer Labels. Bereits
  freigegebene Personenlabels werden beim Apply auf den neuen Referenz-Hash
  übertragen, statt durch die neue GND ungültig zu werden.

## Probelauf (SQL-Dump 28.05.2026, nur Nomisma, ohne Wikidata)

| Feld | auto | review | none | present | present_differs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mzstaette.geonames | 947 | 192 | 1307 | 23 | 2 |
| Person.DNB | 390 | 0 | 3391 | 544 | 1 |
| Person.VIAF | 485 | 59 | 3659 | 123 | 0 |
