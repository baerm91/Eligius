# Laufzeitabhängigkeiten

`requirements.txt` definiert die aktive Laufzeitumgebung für Entwicklung und
Docker. `requirements.legacy.txt` dokumentiert ältere Installationen.

## Bereinigt

- **wikipedia** und **Wikipedia-API**. Der Personen-Dialog ruft
  Wikipedia-Zusammenfassungen über die bestehende HTTP-Integration mit
  requests ab.
- **django-simple-history**. Das Admin-Protokoll nutzt Djangos LogEntry.
- **django-filter**. Die API- und Browse-Filter verwenden Django-QuerySets
  und die projektspezifischen Filterfunktionen.
- **Markdown** wurde aus den Laufzeitanforderungen entfernt.
- **django-bootstrap3** und **django-crispy-forms**. Aktive Formulare nutzen
  Django, `django-bootstrap-modal-forms` und `django-widget-tweaks`.
  Die öffentliche Oberfläche bezieht Bootstrap über Staticfiles.

Die Datenexporte nutzen Tablib mit openpyxl, odfpy, xlrd und xlwt. Diese Pakete
bleiben für ihre jeweiligen Dateiformate Teil der Laufzeitumgebung. PyMySQL
ermöglicht das Entwicklungssetup ohne native Clientbibliothek. Das
Produktionsimage installiert mysqlclient separat.

## Optional

pandas und numpy bleiben in den aktiven Anforderungen auskommentiert.
