# Eligius – Local Development (WSL + Docker MySQL)

## 1) Voraussetzungen

- Docker Desktop läuft
- Container `djangoproject-mysql` läuft auf `127.0.0.1:3307`
- Projektpfad: `/mnt/e/Eligius/eligius`

## 2) Python-Umgebung (stabil, außerhalb von /mnt/e)

```bash
python3 -m venv /home/goffosen/.venvs/eligius_min
source /home/goffosen/.venvs/eligius_min/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
```

## 3) DB-Client-Konfig

Beispieldatei:
- `mysql.cnf.example`

Lokale Datei:
- `mysql.cnf` (wird nicht committed)

Inhalt (lokal):

```ini
[client]
database = djangoproject
user = django
password = django_change_me
host = 127.0.0.1
port = 3307
default-character-set = utf8mb4
```

## 4) Django-Commands

```bash
cd /mnt/e/Eligius/eligius
source /home/goffosen/.venvs/eligius_min/bin/activate

export DJANGO_DB_CNF_PATH='/mnt/e/Eligius/eligius/mysql.cnf'
export DJANGO_SECRET_KEY='dev'
export DJANGO_DEBUG='1'
export DJANGO_ALLOWED_HOSTS='*'

python manage.py check
python manage.py showmigrations slg
python manage.py runserver 0.0.0.0:8000
```

Hinweis: Das Script stellt auch sicher, dass ein `django_site` mit ID 1 existiert (fix für Admin-Login-500 bei fehlendem Site-Record).

### Schneller Smoke-Test

```bash
./scripts/smoke.sh
# optional:
# VENV_PATH=/home/goffosen/.venvs/eligius_min ./scripts/smoke.sh
```

## 5) SQL-Dump reimport (falls nötig)

```bash
docker exec -i djangoproject-mysql mysql -uroot -prootpass_change_me \
  -e "DROP DATABASE IF EXISTS djangoproject; CREATE DATABASE djangoproject CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

docker exec -i djangoproject-mysql mysql -uroot -prootpass_change_me djangoproject \
  < "/mnt/e/Eligius/djangoproject (4).sql"
```

## 6) Status Upgrade

- Django läuft auf **4.2 LTS**
- `mysqlclient` wurde für Dev durch **PyMySQL** ersetzt (kein System-Compile nötig)
- Alle `slg`-Migrations bis `0097` sind vorhanden
- `python manage.py test` findet aktuell keine Tests (`0 tests`)
