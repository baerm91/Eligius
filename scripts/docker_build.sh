#!/bin/sh

REGISTRY="${REGISTRY:-dwb-gitlab.donau-uni.ac.at}"
CONTAINER="${CONTAINER:-${REGISTRY}/zms/eligius}"

docker login "${REGISTRY}"
docker build -t "${CONTAINER}:$(date +%Y%m%d)" -t "${CONTAINER}:latest" . && \
docker push --all-tags "${CONTAINER}"
