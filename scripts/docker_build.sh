#!/bin/sh

REGISTRY=dwb-gitlab.donau-uni.ac.at
CONTAINER=${REGISTRY}/zwb/eligius

docker login ${REGISTRY}
docker build -t ${CONTAINER}:${date} -t ${CONTAINER}:latest . && \
docker push --all-tags ${CONTAINER}
