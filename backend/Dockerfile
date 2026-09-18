# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.7.3@sha256:87a04222b228501907f487b338ca6fc1514a93369bfce6930eb06c8d576e58a4

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --only-upgrade -y --no-install-recommends libpcre2-8-0 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system --gid 10001 mavuno \
    && adduser --system --uid 10001 --ingroup mavuno --home /nonexistent --no-create-home mavuno

COPY --from=builder /opt/venv /opt/venv
COPY --chown=mavuno:mavuno src ./src
COPY --chown=mavuno:mavuno conf ./conf
COPY --chown=mavuno:mavuno db ./db
COPY --chown=mavuno:mavuno migrations ./migrations

USER mavuno

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

CMD ["supervisord", "-n", "-c", "/app/conf/supervisord.conf"]
