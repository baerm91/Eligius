#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

VENV_PATH="${VENV_PATH:-/home/goffosen/.venvs/eligius_min}"
if [[ ! -f "$VENV_PATH/bin/activate" ]]; then
  echo "❌ Venv not found at $VENV_PATH"
  echo "Set VENV_PATH=/path/to/venv and retry."
  exit 1
fi

source "$VENV_PATH/bin/activate"

export DJANGO_DB_CNF_PATH="${DJANGO_DB_CNF_PATH:-$PROJECT_DIR/mysql.cnf}"
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dev}"
export DJANGO_DEBUG="${DJANGO_DEBUG:-1}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-*}"

echo "==> Django check"
python manage.py check

echo "==> Show latest slg migrations"
python manage.py showmigrations slg | tail -n 20

echo "==> URL sanity"
python manage.py shell -c "from django.urls import reverse; print('admin=', reverse('admin:index')); print('index=', reverse('index_slg'))"

echo "✅ Smoke OK"
