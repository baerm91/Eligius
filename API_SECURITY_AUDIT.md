# API Security Audit (2026-03-24)

## Ziel
Öffentliche Endpunkte für Website-Funktion belassen, aber sensible Daten-/Export-Endpunkte auf **Login + Token** umstellen.

## Umgestellt auf Login + Token
Diese Endpunkte erfordern jetzt `IsAuthenticated` mit:
- SessionAuth (eingeloggt im Browser)
- TokenAuth (Authorization Header)
- QueryParamTokenAuth (`?auth_token=...` oder `?token=...`)

1. `GET /export_xlsx/`
2. `GET /export-obj-lsno/`
3. `GET /ajax/get-konkordanzen/`

## Öffentlich belassen (für Website/Browse nötig)
- `GET /api/collections/`
- `GET /api/stats/`
- `GET /api/sammlungen/`
- `GET /api/facet/`
- `GET /api/ereignisse/`
- `GET /api/adjacent-invnrs/`
- `GET /api/muenzen/<id>/kontext/`
- `GET /api/cycle-coin/`
- `GET /api/area-chart-data/`

## Token-Ausgabe
- `POST /api/api-token-auth/` bleibt bewusst `AllowAny` (Login mit Username/Password zur Token-Ausgabe).

## Empfehlungen (nächster Schritt)
1. Für `api-token-auth` Rate-Limit (z. B. Nginx/Traefik fail2ban oder DRF throttling).
2. Optional: interne API-Prefixe (`/internal-api/...`) für plugin-only Endpunkte.
3. Optional: API-Key/Scope-Modell, falls mehrere externe Tools unterschiedliche Rechte brauchen.
