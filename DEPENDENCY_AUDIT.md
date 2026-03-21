# Dependency Audit (Django 4.2 phase)

## Direkt bestätigt in Code genutzt

- Django
- djangorestframework
- django-filter
- django-cors-headers
- django-debug-toolbar
- django-import-export
- django-select2
- django-simple-history
- django-adminactions
- django-admin-list-filter-dropdown
- django-bootstrap3
- django-bootstrap-modal-forms
- django-widget-tweaks
- django-nested-admin
- django-clone
- django-crispy-forms
- PyMySQL
- requests
- beautifulsoup4
- rdflib
- wikipedia
- Wikipedia-API
- Markdown
- openpyxl
- tablib
- odfpy/xlrd/xlwt (Export/Tablib-Ökosystem)

## Entfernt bzw. ersetzt

- `mysqlclient` -> durch `PyMySQL` (für einfaches Dev-Setup)
- alte Legacy-Pins aus `requirements.legacy.txt` bleiben nur als Referenz

## Optional / aktuell nicht im Runtime-Code importiert

- pandas
- numpy

Diese sind in `requirements.txt` aktuell auskommentiert.
Wenn ihr Analyse-/Notebook-Funktionen braucht, können sie wieder aktiviert werden.

## Nächster Cleanup Schritt

- echte Testabdeckung aufbauen (derzeit 0 Tests)
- danach aggressive Bereinigung weiterer optionaler Libraries
