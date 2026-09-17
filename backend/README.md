# Mavuno backend

The backend is a modular FastAPI application. Feature branches are integrated into the
`backend` branch and released to `main` at tested milestones.

## Requirements

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- Docker (only required for the image workflow)

## Local development

From this directory:

```bash
uv sync --frozen
uv run uvicorn mavuno.main:app --reload
```

The API listens at `http://127.0.0.1:8000`. Its initial operational endpoints are:

- `GET /health/live`: the process is alive.
- `GET /health/ready`: the process has completed startup and can receive traffic.

Copy `.env.example` to `.env` for local overrides. Variables use the `MAVUNO_` prefix. Never
commit `.env` or production secrets.

## Database

MySQL 8.4 LTS is an external dependency; it is not embedded in this image and there is no Docker
Compose file. Set `MAVUNO_DATABASE_URL` to an async `mysql+aiomysql://` URL. When configured,
`/health/ready` performs a lightweight database check and returns `503` while MySQL is unavailable.

Apply migrations before starting a new application revision:

```bash
uv run alembic -c conf/alembic.ini upgrade head
```

[`db/schema.sql`](db/schema.sql) is the authoritative empty-database baseline. The first Alembic
revision executes that same file, avoiding duplicate DDL. If the SQL file is applied manually,
stamp the database immediately afterwards:

```bash
uv run alembic -c conf/alembic.ini stamp 0001_identity_baseline
```

Application startup never calls `metadata.create_all()`. All later schema changes require a new
numbered migration.

## Verification

```bash
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

## Container

No Docker Compose file is used. The production container runs Supervisor as PID 1 and Supervisor
runs the API. External services will be supplied with environment variables as their features are
introduced.

```bash
docker build -t mavuno-backend .
docker run --rm --env-file .env -p 8000:8000 mavuno-backend
```

The image runs as the unprivileged `mavuno` user. Runtime logs go to stdout/stderr and the image
health check calls `/health/live`.
