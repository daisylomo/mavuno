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
uv run uvicorn mavuno.main:app --app-dir src --reload
```

The API listens at `http://127.0.0.1:8000`. Its initial operational endpoints are:

- `GET /health/live`: the process is alive.
- `GET /health/ready`: the process has completed startup and can receive traffic.

## Browser administration

Open `/admin` on the API host (for the hosted environment,
`https://mavuno-api.onrender.com/admin`). Sign in with an existing account whose
backend role is `administrator`. Public registration cannot grant this role.
The portal uses the same authenticated API as the app to add categories and
produce types, inspect outstanding refunds, and record a refund already paid
outside the app with its provider reference. It never initiates a money transfer.
Tokens remain in memory; closing or reloading the page requires signing in again.
The app's admin dashboard links to this portal.

Backend CI runs on `main`, backend branches, pull requests and manual dispatch.
It checks formatting, lint, types, migrations, all backend tests, Python client
journeys, the OpenAPI contract and the runtime image. Android publication also
requires these checks to pass. See `../RELEASE.md` for environment limitations.

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
paid only when that query reports success for the exact STK request Mavuno created. Daraja's
status query does not return the amount or the M-PESA receipt number, so those are taken from the
success callback when it arrives, and checked: a reported amount, payer phone or shortcode that
does not match is a discrepancy and never pays the order. A success confirmed by the query alone is
recorded as `matched_query_only` (the STK amount is fixed by the merchant); the receipt is filled in
when the callback lands. Callback payloads are reduced to a safe allowlist (the phone number is
masked) before storage.

While a prompt is open the worker checks the payment at 30, 75 and 150 seconds, and the app can ask
for a check with `POST /payments/{id}/refresh`, so a lost callback or a sleeping free host does
not strand a paid order.

Stock rules around payment:

* A failed or dismissed prompt shortens the reservation to `MAVUNO_PAYMENT_RETRY_GRACE_MINUTES`
  (default 5), so a buyer can retry without farmers' stock being held for the full window.
* A reservation is not released while a prompt sent in the last
  `MAVUNO_PAYMENT_INFLIGHT_GRACE_SECONDS` (default 180) might still be answered.
* A payment that is confirmed after the order expired takes the stock back only if every line is
  still available; otherwise the buyer is refunded. It never oversells.
* A payment for a cancelled order, or a second payment for a paid order, is refunded.
* Order totals are charged in whole shillings. Listing prices must be whole shillings; fractional
  quantities can still produce cents, so the charged `total_amount` is the subtotal rounded down.

Refunds are recorded in `payment_refunds` in the same transaction as the event that makes them
owed. A full refund of an M-PESA payment with a known receipt is sent to Daraja's Transaction
Reversal API by the worker when these are set:

```text
MAVUNO_DARAJA_INITIATOR_NAME=<API operator username>
MAVUNO_DARAJA_SECURITY_CREDENTIAL=<initiator password encrypted with Safaricom's certificate>
```

Without them, and for partial refunds (one farmer in a mixed order cancelling), the refund is
marked `manual_required`. Administrators list open refunds with `GET /admin/refunds` and record a
manually sent refund with `POST /admin/refunds/{id}/complete`. Reversal results arrive at the
tokenized `/webhooks/payments/daraja-reversal/{token}` endpoint.

Enable the rail only after sandbox credentials and a random callback-path token have been
injected:

```text
MAVUNO_PAYMENTS_ENABLED=true
MAVUNO_DARAJA_ENVIRONMENT=sandbox
MAVUNO_DARAJA_CALLBACK_BASE_URL=https://your-api.example
```

The bank adapter is intentionally fail-closed until a regulated Kenyan bank/payment provider is
selected. The generic bank configuration keys reserve that integration boundary; they do not
pretend that a transfer has been validated.

Commerce endpoints live under `/api/v1`: cart item management, checkout, order retrieval and
cancellation (`POST /orders/{id}/cancel`), payment initiation/retrieval/refresh, and the tokenized
Daraja callback endpoints. Every retryable client operation requires an `Idempotency-Key` header.

Farmers see their orders at `GET /farmers/me/orders`, including orders still awaiting payment
(with the reservation deadline, but without the buyer's phone or address until payment is
verified) and their own hand-over status.

## Fulfilment coordination

An order can contain produce from several farmers, so each farmer has their own fulfilment record
covering only their items. The buyer's first `PATCH /api/v1/fulfilments/{order_id}` creates one
record per farmer with the same method, location, window and notes. After that:

* a farmer sees and advances only their own record (`scheduled`, `ready_for_handover`,
  `in_transit` for deliveries) and may withdraw it while it is still `pending` or `scheduled`;
* the buyer confirms completion, or cancels, per farmer — pass `?farmer_id=` when the order has
  more than one farmer (`GET /fulfilments/{order_id}/parts` lists them);
* cancelling a farmer's part returns that farmer's stock and records a refund for their items;
* the order is `completed` once every farmer's part has finished and at least one was handed
  over, and `cancelled` if every part was cancelled.

Each transition is audited and updates use a version number plus database row locks to reject
stale concurrent writes. The scope ends at coordination and hand-over status: the backend
deliberately does not assign drivers, vehicles, routes, or fleets.

## Farmers behind listings

Every listing response carries a `farmer` summary: display name, farm name, county and locality,
verification status, member-since date, number of active listings and completed orders, pickup and
delivery options, and the farmer's own description of their farming practices (never presented as
a certification). `GET /farmers/{farmer_id}` adds the bio, farm size, year started, delivery
radius, produce categories and cancelled hand-overs. Farmers edit these details with
`GET`/`PATCH /users/me/farmer`.

Farmers upload their own photos with `POST /listings/{id}/photos` (base64 JPEG, PNG or WebP, up to
`MAVUNO_LISTING_IMAGE_MAX_BYTES`, default 1.5 MB). The bytes are stored in MySQL so a stateless host
without object storage can serve them from `GET /listing-images/{image_id}`; image responses carry
that path as `url`. Keys under `preset/` name illustrations bundled with the app.

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

## Premium services

Feature 10 adds provider-neutral plans and subscriptions, verified entitlements, prebooking, and
permissioned farmer insights. Subscription initiation is idempotent and produces a pending record;
neither a client response nor a webhook grants access. The callback is authenticated with a secret
path token and HMAC signature, persisted in redacted form, and converted to an outbox status-query
job. Only a matching server-to-server provider result—account reference, plan, amount, currency,
and valid billing period—activates an entitlement.

Prebooking is available to buyers with the verified `prebooking` entitlement. The selected farmer
can accept, reject, or fulfil the request without buying a subscription of their own. Farmer
insights require the verified `insights` entitlement and are calculated from transactional data;
they do not duplicate order or inventory records. Produce suggestions remain deferred until there
is a measurable product requirement.

The generic HTTPS billing adapter is disabled by default. Configure all `MAVUNO_PREMIUM_*`
settings together; partial or production-placeholder configuration fails closed.

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

## Release operations

Feature 11 adds W3C trace correlation, credential-redacted JSON logs, a generated OpenAPI contract,
and CI gates for tests, migrations, dependency review, and container scanning. Operational SLOs,
alerts, deployment/rollback steps, backup restoration, and secret rotation are documented in
[`docs/operations.md`](docs/operations.md) and [`docs/slo.md`](docs/slo.md). Run the deployment
smoke test with `uv run python scripts/smoke.py --base-url http://127.0.0.1:8000`.
