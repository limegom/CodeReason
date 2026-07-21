# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/codereason

RUN groupadd --system --gid 10001 codereason \
    && useradd --system --uid 10001 --gid codereason --home-dir /nonexistent codereason

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN python -m pip install ".[postgres]"

FROM base AS api

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker

# Only the trusted worker image contains the Docker client. Compose mounts the
# Engine socket into this service; it is never mounted into API or web.
USER root
RUN apt-get update \
    && apt-get install --yes --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*

CMD ["python", "-m", "app.worker"]
