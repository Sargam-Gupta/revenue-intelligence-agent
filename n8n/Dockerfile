# n8n + the project's Python pipeline, so Execute Command nodes can run the real
# scripts (data -> variance -> narrative -> cache -> git push) against the repo
# bind-mounted at /repo.
#
# Base is Alpine (musl libc). numpy / pandas / pydantic-core all ship musllinux
# wheels, so pip installs without a compiler. If a future version bump lacks a
# musl wheel and pip tries to build from source, add build deps:
#   RUN apk add --no-cache build-base python3-dev cargo
#
# Pinned to 1.70.0 deliberately: n8nio/n8n:latest switched to a Docker Hardened
# Image (no apk / no package manager), so `apk add python3` can't run there.
# 1.70.0 is the last-known plain-Alpine tag we verified still ships apk. Don't
# bump to :latest without solving the Python-install problem a different way
# (multi-stage COPY of a venv, or a separate Python sidecar container).
FROM n8nio/n8n:1.70.0

USER root

# Python + git: the pipeline runs on python3; git is used by the publish step.
RUN apk add --no-cache python3 py3-pip git

# Pipeline runtime deps ONLY. Deliberately excludes streamlit/plotly — those are
# dashboard-only and run on Streamlit Cloud, never in this container.
COPY requirements-pipeline.txt /tmp/requirements-pipeline.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements-pipeline.txt

USER node

# /repo is bind-mounted and owned by the host user, so mark it safe for git to
# avoid "detected dubious ownership" failures on commit/push as the node user.
RUN git config --global --add safe.directory /repo
