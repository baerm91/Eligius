#!/usr/bin/env bash
set -euo pipefail

mode=${1:-}
revision=${2:-}
digest=${3:-}
previous=${4:-}
repository=dwb-gitlab.donau-uni.ac.at/zms/eligius
web=eligius-webapp-1
db=eligius-db-1
backup_dir=$HOME/eligius-backups
health_url=https://eligius.donau-uni.ac.at/health

compose() { docker compose -f /srv/docker/eligius/compose.yml "$@"; }
running_image() { docker inspect "$web" --format '{{.Image}}'; }
running_revision() { docker inspect "$web" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'; }
health_ok() {
    wget -q --timeout=4 -O- "$health_url" |
        python3 -c 'import json, sys; sys.exit(json.load(sys.stdin).get("status") != "ok")' 2>/dev/null
}

if [[ $mode == status ]]; then
    [[ $(docker info --format '{{.Architecture}}') == x86_64 ]]
    [[ $(docker inspect "$db" --format '{{.State.Health.Status}}') == healthy ]]
    compose config --images | grep -Fxq "$repository:latest"
    health_ok
    current=$(running_image)
    printf '%s\n' "$current"
    running_revision
    docker image inspect "$current" --format '{{range .RepoDigests}}{{println .}}{{end}}' |
        awk -F @ -v repository="$repository" '$1 == repository {print $2}'
    exit
fi

[[ $revision =~ ^[0-9a-f]{40}$ && $digest =~ ^sha256:[0-9a-f]{64}$ ]]
ref=$repository@$digest
if [[ $mode == verify ]]; then
    [[ $(running_image) == "$(docker image inspect "$ref" --format '{{.Id}}')" ]]
    [[ $(running_revision) == "$revision" ]]
    health_ok
    printf 'Healthcheck OK. GitLab-Revision %s läuft.\n' "$revision"
    exit
fi

[[ $mode == deploy && $previous =~ ^sha256:[0-9a-f]{64}$ ]]
umask 077
mkdir -p "$backup_dir"
exec 9>"$backup_dir/deployment.lock"
flock -n 9 || { echo 'Another deployment is already in progress.' >&2; exit 1; }
[[ $(running_image) == "$previous" ]] || { echo 'Production changed during the build.' >&2; exit 1; }
database_id=$(docker inspect "$db" --format '{{.Id}}')
[[ $(docker inspect "$db" --format '{{.State.Health.Status}}') == healthy ]]

docker pull "$ref"
expected=$(docker image inspect "$ref" --format '{{.Id}}')
[[ $(docker image inspect "$ref" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}') == "$revision" ]]
printf 'services:\n  webapp:\n    image: "%s"\n' "$ref" |
    docker compose -f /srv/docker/eligius/compose.yml -f - run --rm -T --no-deps --pull never \
        --entrypoint /venv/bin/python webapp manage.py migrate --plan

backup=$(mktemp "$backup_dir/pre-${revision:0:7}-XXXXXXXX.sql.gz")
if ! docker exec "$db" sh -c 'MYSQL_PWD="$(cat /run/secrets/db_root_password)" exec mariadb-dump -uroot --all-databases --single-transaction --quick --routines --events' |
        gzip > "$backup" || ! gzip -t "$backup"; then
    rm -f -- "$backup"
    echo 'Database backup failed.' >&2
    exit 1
fi
printf 'Database backup: %s\n' "$backup"
docker tag "$previous" "eligius-rollback:pre-${revision:0:12}"

ready() {
    for ((attempt = 0; attempt < 30; attempt++)); do
        if [[ $(running_image 2>/dev/null) == "$1" ]] && health_ok; then return 0; fi
        sleep 2
    done
    return 1
}

docker tag "$ref" "$repository:latest"
if compose up -d --no-deps --pull never webapp && ready "$expected" &&
    docker exec "$web" /venv/bin/python manage.py migrate --check &&
    [[ $(docker inspect "$db" --format '{{.Id}}') == "$database_id" ]]; then
    printf 'New web container passed the health and migration checks.\n'
else
    docker logs --tail 25 "$web" >&2 || true
    docker tag "$previous" "$repository:latest"
    if compose up -d --no-deps --pull never webapp && ready "$previous"; then
        echo 'Previous web container restored.' >&2
    else
        echo 'Previous web container did not pass the health check.' >&2
    fi
    printf 'Deployment failed. Review migration status before restoring any database backup. Backup: %s\n' "$backup" >&2
    exit 1
fi
