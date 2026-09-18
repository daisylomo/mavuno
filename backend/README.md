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

## Authentication

The versioned authentication API is available under `/api/v1/auth` and supports registration,
login, refresh-token rotation, logout, and the authenticated `/me` endpoint. Register with either
an email address, a Kenyan/local or international phone number, a password, and the `buyer` or
`farmer` role. Phone numbers are stored in E.164 form (for example, `0712345678` becomes
`+254712345678`).

Access tokens are short-lived signed bearer tokens. Refresh tokens are opaque, stored only as
SHA-256 hashes, rotated on every use, and protected by token-family reuse detection. Clients must
replace the stored refresh token atomically after a successful refresh. A reuse response requires
the user to sign in again.

Configure signing secrets through `MAVUNO_AUTH_SIGNING_KEYS`, a JSON object keyed by key ID, and
select the signing key with `MAVUNO_AUTH_ACTIVE_KEY_ID`. Rotate keys by adding a new entry, making
it active, and retaining the previous entry for at least the maximum access-token lifetime. Never
commit real signing keys. Staging and production refuse to start without explicitly configured
keys.

Registration, login, and refresh endpoints have atomic Redis-backed fixed-window rate limits.
Keys are HMAC digests of the client address and submitted identifier or token; raw credentials and
identifiers are never retained by the limiter. If Redis is absent or times out, the API keeps the
bounded in-process limiter as a defense-in-depth fallback, so authentication remains available;
that fallback is intentionally per-process and therefore weaker across replicas. Configure the
window, route limits, and fallback memory bound with the
`MAVUNO_AUTH_RATE_LIMIT_*` variables. The API returns `429`, the stable
`auth_rate_limit_exceeded` code, and a `Retry-After` header when a limit is reached. Client address
resolution intentionally ignores forwarding headers until trusted-proxy handling is configured.

## Profiles and devices

Authenticated users manage their own profile and Kenyan delivery addresses below
`/api/v1/users/me`.
Avatar values are object-storage keys, never uploaded files or public URLs. Farmer and buyer
extensions require the corresponding assigned role. Address lookups always include the current
user ID, so another user's UUID is indistinguishable from a missing address.

Device registration accepts a platform push token only when both `MAVUNO_PUSH_TOKEN_HASH_KEY` and
`MAVUNO_PUSH_TOKEN_ENCRYPTION_KEY` are configured. The server stores Fernet authenticated
ciphertext for later notification delivery and a separate keyed SHA-256 digest for uniqueness.
Plaintext tokens never appear in logs, audit events, or API responses. Generate the encryption key
with:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Use an unrelated random HMAC secret of at least 32 characters; do not reuse JWT, database, or
encryption credentials. Both values are mandatory in production. Rotating the Fernet key makes
existing ciphertext unreadable, so retain the old key during a controlled re-encryption migration
or revoke installations and require clients to register their tokens again. Rotating the HMAC key
requires recomputing digests from decrypted tokens in the same controlled migration.

## Catalog and inventory

Feature 05 adds produce categories, products, farmer-owned listings, object-storage image keys,
and an append-only inventory movement history. Catalog reads support filters, search, stable cursor
pagination, sorting, ETags, and bounded cache headers. Listing and inventory mutations verify the
farmer owner, lock inventory rows, and increment a version so concurrent changes cannot silently
overwrite one another.

Feature 09 caches only the hot listing-detail representation. Redis keys are
`mavuno:v1:catalog:listing:{listing_uuid}` with a 15-second default TTL. Listing, image, inventory,
checkout-reservation, and reservation-release mutations own invalidation after their database
commit. A companion `mavuno:v1:catalog:listing-generation:{listing_uuid}` counter makes cache fill
conditional on the generation observed before the database read; this prevents a concurrent old
read from repopulating the key after stock invalidation. Generation counters expire after a
bounded guard interval so archived listings do not leave permanent Redis keys. Browser/shared HTTP caches must
revalidate, which prevents a longer client cache from outliving stock changes. Redis failures
bypass cache reads and writes for a short circuit-breaker cooldown; the database remains
authoritative. A failed invalidation can leave an entry only until the bounded TTL, and Redis being
unavailable never blocks a catalog response.

Redis is an external optional dependency configured with `MAVUNO_REDIS_URL`; it is not supervised
inside the API image. No separate load balancer or Docker Compose service is introduced.

## Orders and Kenyan payments

Feature 06 adds one active cart per buyer, idempotent checkout, immutable order-item snapshots,
row-locked inventory reservations, reservation expiry/release, payment events, reconciliation,
and a durable database outbox. The API and worker are separate Supervisor programs in the same
lightweight image; MySQL remains an external service and no Docker Compose file is used.

The payment boundary supports `mpesa` and `bank` rails. M-PESA uses Safaricom Daraja STK Push.
Callbacks are treated only as notifications: the worker queries Daraja directly and marks an order
paid only after amount, currency, payer phone, merchant shortcode, and transaction reference
checks pass. Callback payloads are reduced to a safe allowlist before storage. Enable the rail only
after sandbox credentials and a random callback-path token have been injected:

```text
MAVUNO_PAYMENTS_ENABLED=true
MAVUNO_DARAJA_ENVIRONMENT=sandbox
MAVUNO_DARAJA_CALLBACK_BASE_URL=https://your-api.example
```

The bank adapter is intentionally fail-closed until a regulated Kenyan bank/payment provider is
selected. The generic bank configuration keys reserve that integration boundary; they do not
pretend that a transfer has been validated.

Commerce endpoints live under `/api/v1`: cart item management, checkout, order retrieval, payment
initiation/retrieval, and the tokenized Daraja callback endpoint. Every retryable client operation
requires an `Idempotency-Key` header.

## Fulfilment coordination

Feature 07 adds one order-level fulfilment record for pickup or delivery coordination. Buyers
choose the method, location snapshot, time window, and notes after verified payment. Farmers who
own an item in that order can view the coordination and advance preparation states; buyers confirm
completion, while administrators can resolve exceptional transitions. Each transition is audited
and updates use a version number plus database row locks to reject stale concurrent writes.

Use `GET` and `PATCH /api/v1/fulfilments/{order_id}` to read or establish coordination, and
`POST /api/v1/fulfilments/{order_id}/status` for state transitions. The scope ends at coordination
and handover status: the backend deliberately does not assign drivers, vehicles, routes, or fleets.

## Messaging and notifications

Feature 08 adds HTTP-polled conversations scoped to an order or listing. A conversation contains
exactly one buyer and one farmer; order membership is derived from immutable order items and
listing ownership is derived from the listing. All reads and mutations include the authenticated
member in their query so foreign UUIDs are returned as not found. Client-generated message UUIDs
make sends idempotent, and per-member read markers never move backwards.

Each message transaction also inserts notification history and a deduplicated `notification_push`
outbox job. The existing worker claims jobs with `SKIP LOCKED`, a bounded lease, capped exponential
backoff, and dead-letter state. Delivery is idempotent per notification/device pair. Push tokens
remain encrypted at rest and are decrypted only at the provider boundary; they are never returned
by the API or written to logs. Configure the HTTPS push gateway with
`MAVUNO_NOTIFICATION_PUSH_URL` and `MAVUNO_NOTIFICATION_PUSH_API_KEY`. If it is absent, delivery
fails closed and follows the normal retry/dead-letter policy while notification history remains
available through polling.

Messaging endpoints under `/api/v1` cover conversation creation/listing, message send/polling,
read markers, notification history/read state, and push preferences. WebSockets are intentionally
not required for this release.

## Verification

```bash
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Every response includes `X-DB-Query-Count`. Queries slower than
`MAVUNO_DATABASE_SLOW_QUERY_MS` and requests exceeding `MAVUNO_DATABASE_QUERY_BUDGET` emit
structured warnings without exposing SQL parameters. Low-cardinality cache, Redis, rate-limit,
query, and budget counters are available at `GET /health/metrics`; production deployments should
restrict that operational endpoint at the ingress. A representative k6 workload is provided at
`tests/load/catalog_hot_get.js` and can be run against seeded data:

```bash
k6 run -e BASE_URL=http://127.0.0.1:8000 -e LISTING_ID=<uuid> tests/load/catalog_hot_get.js
```

## Container

No Docker Compose file is used. The production container runs Supervisor as PID 1; Supervisor
runs both the API and the outbox/payment worker. MySQL and provider APIs are external services
supplied through environment configuration.

```bash
docker build -t mavuno-backend .
docker run --rm --env-file .env -p 8000:8000 mavuno-backend
```

The image runs as the unprivileged `mavuno` user. Runtime logs go to stdout/stderr and the image
health check calls `/health/live`.
