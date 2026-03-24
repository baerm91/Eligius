# Eligius – Local Development (Docker MySQL)

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
python3 -m venv /home/goffosen/.venvs/eligius_min
source /home/goffosen/.venvs/eligius_min/bin/activate
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
# VENV_PATH=/home/goffosen/.venvs/eligius_min ./scripts/smoke.sh
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

## 8) Status Upgrade

- Django läuft auf **4.2 LTS**
- `mysqlclient` wurde für Dev durch **PyMySQL** ersetzt (kein System-Compile nötig)
- Alle `slg`-Migrations bis `0097` sind vorhanden
- `python manage.py test` findet aktuell keine Tests (`0 tests`)
