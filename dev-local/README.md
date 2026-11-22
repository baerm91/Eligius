# Lokale Dev-Dateien (nicht für Git)

Dieser Ordner trennt **lokale/sensible** Dateien klar vom restlichen Projekt.

## Enthaltene Dateien

- `django.local.env.example` → Vorlage für lokale Django-Umgebungsvariablen
- `mysql.local.cnf.example` → Vorlage für lokale MySQL-Client-Verbindung

## Lokal erstellen (nicht committen)

1. `django.local.env.example` nach `django.local.env` kopieren
2. `mysql.local.cnf.example` nach `mysql.local.cnf` kopieren
3. Werte anpassen

Diese beiden lokalen Dateien sind in `.gitignore` eingetragen und werden nicht auf GitHub hochgeladen.

## Für ZIP-Weitergabe

Wenn du dein Projekt als ZIP weitergibst, sind lokale Dateien klar erkennbar durch:

- den Ordnernamen `dev-local/`
- die Dateinamen mit `.local.`

Dadurch ist sofort sichtbar, was lokal/sensibel ist.
