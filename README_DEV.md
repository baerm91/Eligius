# Eligius – Local Development (Docker MySQL)

## Produktion aktualisieren (Windows)

Nachdem der GitHub-Abgleich nach GitLab abgeschlossen ist, im Eligius-Ordner
`deploy-uni.bat` doppelklicken. Alternativ lässt sich das PowerShell-Skript
direkt ausführen:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy-production.ps1
```

Das Skript benötigt Windows PowerShell 5.1 oder neuer, Git, PuTTY/Plink, Docker Desktop
mit Linux-Containern und ein bestehendes Docker-Login mit Schreibrecht auf
`dwb-gitlab.donau-uni.ac.at/zms/eligius`. Es verbindet sich per SSH
mit `eligius.donau-uni.ac.at` (geprüfter Hostschlüssel). SSH-Benutzer und
persönlicher PuTTY-Schlüssel stehen nicht im Repo, sondern lokal in
`dev-local/deploy.local.ps1`:

```powershell
$DeployUser = '<ssh-benutzer>'
$DeployKeyPath = 'C:\Pfad\zu\privatekey.ppk'
```

Alternativ gehen die Parameter `-User`/`-KeyPath` oder die Umgebungsvariablen
`ELIGIUS_DEPLOY_USER`/`ELIGIUS_DEPLOY_KEY`. Falls das Registry-Login
abgelaufen ist, einmal `docker login dwb-gitlab.donau-uni.ac.at -u <benutzer>`
ausführen und den Registry-Token bei der Passwortabfrage eingeben.

Das Skript baut den GitLab-Commit aus einem separaten Verzeichnis und prüft das
Image mit Django-Tests. Vor dem Webcontainer-Wechsel prüft es den Migrationsplan
und erstellt ein Datenbank-Backup im Serververzeichnis `~/eligius-backups`.
Nach erfolgreichem Start aktualisiert es `latest` und gleicht den Registry-Digest,
die laufende GitLab-Revision und den Healthcheck ab. Die abschließende Meldung
**Live** oder **Bereits live** bestätigt den veröffentlichten Stand.

Mit `-CheckOnly` lassen sich Zugang, Build und Tests prüfen, ohne ein Image
hochzuladen oder Produktion umzustellen. Bei einem fehlgeschlagenen Start
versucht das Skript, das vorherige Webimage wieder einzusetzen. Eine bereits
ausgeführte Datenbankmigration wird dabei nicht automatisch zurückgenommen.

Deutsch/Englisch, stabile URLs und MCP-Übersetzungsentwürfe:
[I18N_DEVELOPMENT.md](I18N_DEVELOPMENT.md).

Öffentlicher Remote MCP und Eligius Lab: siehe [MCP_DEVELOPMENT.md](MCP_DEVELOPMENT.md)
für ASGI-Start, Konfiguration, Tools und Tests. `runserver` bedient weiterhin
die Django-Seiten; `/mcp` benötigt den dort beschriebenen ASGI-Start.

Die optionale native Browserintegration ist in [WEBMCP_DEVELOPMENT.md](WEBMCP_DEVELOPMENT.md)
beschrieben. Sie verwendet dieselben fünf Datentools und ergänzt Navigation,
Browse-Filter und Seitenkontext. Aktivierung: `ELIGIUS_WEBMCP_ENABLED=1`.

## Listen-API und lokale Frontend-Bibliotheken

DRF-Listen mit dem Standard-Paginator liefern ohne Parameter weiterhin ein
JSON-Array. Mit `?page=1` oder `?page_size=50` liefern sie
`count`, `next`, `previous` und `results`. Die Seiten sind nach
Primärschlüssel sortiert. Die Standardgröße ist 100, das Maximum 500.
Filter bleiben in den Navigationslinks erhalten. Endpunkte mit eigenem
Paginator behalten ihr bisheriges Verhalten.

Die öffentlichen Templates laden die folgenden Assets über Django Staticfiles
aus `slg/static/vendor/`. Die Verzeichnisse enthalten die jeweiligen
Lizenztexte. Die Quellen sind die gleichnamigen npm-Pakete und bei den
Schriften die Pakete unter `@fontsource-variable`.

| Bibliothek | Version |
| --- | --- |
| jQuery | 3.7.1 |
| Bootstrap / Bootstrap Icons | 5.3.0 / 1.11.1 |
| Cookie Consent | 3.1.1 |
| Select2 (CSS) | 4.1.0-rc.0 |
| LightGallery (CSS und Schrift) | 1.6.11 |
| Leaflet / Leaflet.markercluster / Leaflet.fullscreen | 1.9.4 / 1.4.1 / 2.4.0 |
| MapLibre GL / @maplibre/maplibre-gl-leaflet | 5.24.0 / 0.1.2 |
| noUiSlider / ECharts | 14.7.0 / 5.5.0 |
| Cormorant Garamond, Plus Jakarta Sans, Josefin Sans, Inter, Outfit, Playfair Display | 5.3.0 |

Die Basiskarte bezieht ihre Kartendaten weiterhin von OpenFreeMap.

## 1) Voraussetzungen

- Docker Desktop läuft
- MySQL-Container läuft (bei dir aktuell: `mysql` auf `127.0.0.1:3306`)
- Projektpfad: `d:\Prog-Proj\Eligius`

## 2) Lokale Dev-Dateien anlegen (nicht für Git)

Wir nutzen bewusst den Ordner `dev-local/`, damit lokale/sensible Dateien
klar sichtbar sind (auch bei ZIP-Weitergabe) und nicht committed werden.

```powershell
Copy-Item .\dev-local\django.local.env.example .\dev-local\django.local.env
Copy-Item .\dev-local\mysql.local.cnf.example .\dev-local\mysql.local.cnf
```

Danach Werte in folgenden lokalen Dateien prüfen/anpassen:

- `dev-local/django.local.env`
- `dev-local/mysql.local.cnf`

Beide Dateien sind in `.gitignore` eingetragen.

## 3) Python-Umgebung

```bash
python3 -m venv ~/.venvs/eligius_min
source ~/.venvs/eligius_min/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
```

## 4) Django starten (Windows / PowerShell)

Ein-Klick-Start (empfohlen):

```powershell
.\start-dev.ps1
```

Alternative per CMD/Doppelklick:

```bat
start-dev.bat
```

`start-dev.ps1` erstellt bei Bedarf `.venv`, installiert Dependencies und startet
danach automatisch `scripts/dev_server.ps1`.

Manuell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip setuptools wheel
pip install -r requirements.txt

.\scripts\dev_server.ps1
```

`dev_server.ps1` lädt automatisch `dev-local/django.local.env` und startet
den Django Dev-Server auf `http://127.0.0.1:8000`.

## 5) DB-Client-Konfig (manuell)

Beispieldatei:
- `dev-local/mysql.local.cnf.example`

Lokale Datei:
- `dev-local/mysql.local.cnf` (wird nicht committed)

Inhalt (lokal):

```ini
[client]
database = djangoproject
user = root
password = root
host = 127.0.0.1
port = 3306
default-character-set = utf8mb4
```

## 6) Django-Commands (manuell, alternativ)

```powershell
.\.venv\Scripts\Activate.ps1

$env:DJANGO_DB_CNF_PATH='dev-local/mysql.local.cnf'
$env:DJANGO_SECRET_KEY='dev'
$env:DJANGO_DEBUG='1'
$env:DJANGO_ALLOWED_HOSTS='*'

python manage.py check
python manage.py showmigrations slg
python manage.py runserver 127.0.0.1:8000
```

Hinweis: Das Script stellt auch sicher, dass ein `django_site` mit ID 1 existiert (fix für Admin-Login-500 bei fehlendem Site-Record).

### Schneller Smoke-Test

```bash
./scripts/smoke.sh
# optional:
# VENV_PATH=~/.venvs/eligius_min ./scripts/smoke.sh
```

### Route-Sweep (Webseiten-/API-Basischeck)

```powershell
.\.venv\Scripts\Activate.ps1
$env:DJANGO_DB_CNF_PATH='dev-local/mysql.local.cnf'
$env:DJANGO_SECRET_KEY='dev'
$env:DJANGO_DEBUG='1'
$env:DJANGO_ALLOWED_HOSTS='*'
python scripts/route_sweep.py
```

## 7) SQL-Dump reimport (falls nötig)

```bash
docker exec -i mysql mysql -uroot -proot \
  -e "DROP DATABASE IF EXISTS djangoproject; CREATE DATABASE djangoproject CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

docker cp "d:\Prog-Proj\Eligius\djangoproject (4).sql" mysql:/tmp/djangoproject.sql
docker exec mysql sh -lc "mysql -uroot -proot djangoproject < /tmp/djangoproject.sql"
```

## 8) Git-Schutz gegen lokale Dateien

Damit keine lokalen Dateien/venvs versehentlich auf GitHub landen:

```bash
# einmal pro Clone:
git config core.hooksPath .githooks
```

Der Hook `.githooks/pre-push` ruft `scripts/prepush_guard.sh` auf und blockt Pushes,
wenn verbotene lokale/dev-Dateien bereits getrackt sind (z. B. `.venv/`, `.env*`, `dev-local/`, `*.sql`, `*.sqlite3`).

## 9) Status Upgrade

- Django läuft auf **4.2 LTS**
- `mysqlclient` wurde für Dev durch **PyMySQL** ersetzt (kein System-Compile nötig)
- Alle `slg`-Migrations bis `0097` sind vorhanden
- `python manage.py test` findet aktuell keine Tests (`0 tests`)
