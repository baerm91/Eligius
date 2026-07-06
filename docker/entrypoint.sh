#!/bin/sh

/venv/bin/python manage.py check &&\
/venv/bin/python manage.py migrate --noinput &&\
/venv/bin/python manage.py collectstatic --noinput &&\
exec /venv/bin/gunicorn $@ \
    --worker-tmp-dir=/dev/shm \
    --control-socket=/tmp/gunicorn.ctl \
    --workers="${WEB_CONCURRENCY:-2}" \
    --bind="${GUNICORN_BIND:-0.0.0.0:8080}" \
    --name="${PROJECT_NAME:-webapp}" \
    djangoproject.wsgi:application
