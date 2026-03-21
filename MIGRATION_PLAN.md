# Eligius – Migration/Upgrade Plan

## Was bereits erledigt wurde

1. **GitHub-Backup vorbereitet (safe by default):**
   - `.gitignore` hinzugefügt (SQL-Dumps, `.env`, `.cnf`, Keys, lokale DBs, Caches etc.)
   - `.env.example` angelegt
   - `settings.py` auf Umgebungsvariablen umgestellt (Secret, Debug, Allowed Hosts, DB-CNF-Pfad)
2. **Django-Upgrade-Vorbereitung:**
   - `requirements.txt` auf Django 4.2 LTS + moderne Versionen aktualisiert
   - altes `requirements.txt` als `requirements.legacy.txt` gesichert
   - `django.utils.six`-Import in `slg/views.py` entfernt (nicht kompatibel mit Django>=3)

## Nächste technische Schritte (automatisch testbar)

### 1) Lokale Testumgebung bauen

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
```

Falls einzelne Pakete (z. B. `django-adminactions`) bei Django 4.2 zicken:
- temporär aus `INSTALLED_APPS` + `requirements.txt` entfernen
- Alternativen nutzen (custom Admin Action / django-object-actions)

### 2) SQL-Dump in MySQL (Docker Desktop) importieren

Dump liegt laut dir hier:
- `E:\Eligius\djangoproject (4).sql`

Beispiel (anpassen auf deinen MySQL-Containernamen):

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
docker exec -i <mysql-container> mysql -u <user> -p<password> <database> < "/mnt/e/Eligius/djangoproject (4).sql"
```

### 3) Migrations + Checks

```bash
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py test
```

### 4) Django 5 Status
- Django 5.0.14, 5.1.8 und 5.2.2 wurden in separaten Test-venvs erfolgreich installiert
- `python manage.py check` unter Django 5.2.2: **ohne Fehler**
- `./scripts/smoke.sh` unter Django 5.2.2: **OK**
- Requirements wurden auf `Django==5.2.2` angehoben

## Kandidaten für Cleanup/Entfernung

Aus dem alten Setup wirken einige Pakete potenziell entbehrlich oder veraltet:
- `mod-wsgi` (nur nötig, wenn Deployment exakt so läuft)
- `mysql==0.0.3` (nicht nötig, wenn `mysqlclient` genutzt wird)
- `pip-tools`, `pipdeptree` (nur Build-Tooling)
- `django-static-jquery-ui`, `django-tabbed-admin`, `python-monkey-business`, `conditional` (prüfen, ob irgendwo wirklich genutzt)

Empfehlung: nach erfolgreichem Start via Imports + Laufzeittests endgültig aussortieren.
