ARG BASE_IMAGE=python:3.12-alpine

# build mysql native python bindings (better performance)
FROM ${BASE_IMAGE} AS builder

RUN python -m venv /venv

RUN apk add --no-cache mariadb-dev g++

RUN /venv/bin/pip install mysqlclient==2.2.8

# install python production environment
FROM ${BASE_IMAGE} AS runner

# UID for application user, will create uploaded files with this UID:GID
ARG WEBAPP_UID=4000

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PIP_DEFAULT_TIMEOUT=100

RUN adduser --uid=$WEBAPP_UID --disabled-password webapp

RUN apk add --no-cache mariadb-client

WORKDIR /app

COPY --from=builder /venv /venv

COPY requirements.txt .

# install production dependencies in python environment
RUN /venv/bin/pip install -r requirements.txt

# install wsgi server
RUN /venv/bin/pip install gunicorn==26.0.0 setproctitle==1.3.7

COPY djangoproject djangoproject
COPY slg slg
COPY manage.py .
COPY docker/entrypoint.sh .

# run as application user
USER webapp:webapp

# run gunicron server with uvicorn worker
ENTRYPOINT [ "/app/entrypoint.sh" ]
