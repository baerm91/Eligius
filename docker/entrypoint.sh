#!/bin/sh

/venv/bin/python manage.py check && \
/venv/bin/python manage.py migrate --noinput && \
/venv/bin/python manage.py collectstatic --noinput && \
if [ -n "$SERVER_START_CMD" ]; then
    exec $SERVER_START_CMD "$@"
elif [ "$APP_SERVER" = "wsgi" ]; then
    exec /venv/bin/gunicorn "$@" \
        --worker-tmp-dir=/dev/shm \
        --control-socket=/tmp/gunicorn.ctl \
        --workers="${WEB_CONCURRENCY:-2}" \
        --bind="${GUNICORN_BIND:-0.0.0.0:8080}" \
        --name="${PROJECT_NAME:-webapp}" \
        djangoproject.wsgi:application
else
    # Default: Gunicorn with Uvicorn worker for ASGI (supports HTTP, Remote MCP, and WebMCP)
    exec /venv/bin/gunicorn "$@" \
        --worker-tmp-dir=/dev/shm \
        --control-socket=/tmp/gunicorn.ctl \
        --workers="${WEB_CONCURRENCY:-2}" \
        --worker-class="${GUNICORN_WORKER_CLASS:-uvicorn.workers.UvicornWorker}" \
        --bind="${GUNICORN_BIND:-0.0.0.0:8080}" \
        --name="${PROJECT_NAME:-webapp}" \
        djangoproject.asgi:application
fi
