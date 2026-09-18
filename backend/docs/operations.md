# Production operations

This runbook is provider-neutral. The deployment platform supplies MySQL, Redis, TLS termination,
secrets, and at least two application instances; the image runs the API and outbox worker under
Supervisor.

## Deploy and migrate

1. Build the immutable image and record its digest and source commit.
2. Back up MySQL and complete the restore check below before a destructive migration.
3. Run `alembic upgrade head` once using the new image. Never run Alembic in every API replica.
4. Start one canary, wait for `/health/ready`, and run `scripts/smoke.py` against its private URL.
5. Roll out remaining instances gradually with alerting enabled.
6. Confirm error rate, p95 latency, outbox backlog, payment reconciliation, and subscription
   reconciliation before declaring the release complete.

The API enters readiness after startup and leaves it before closing database and Redis connections.
Supervisor sends `TERM` to each process group and permits 30 seconds for graceful shutdown. The
load balancer drain interval must be at least 30 seconds.

## Roll forward and rollback

Prefer roll-forward migrations. Before release, rehearse both `alembic downgrade <previous>` and
`alembic upgrade head` against a restored staging backup. If the schema remains backward compatible,
stop rollout and redeploy the previous image digest. If schema rollback is required, stop writers,
capture another backup, downgrade exactly one revision, deploy the prior image, and smoke-test it.
Never downgrade while mixed application versions are writing.

## Backup and restore rehearsal

Use a restricted backup account and inject its password through `MYSQL_PWD`; never place it on the
command line or in a log.

```sh
mysqldump --single-transaction --routines --triggers --set-gtid-purged=OFF \
  --host="$MYSQL_HOST" --user="$MYSQL_BACKUP_USER" "$MYSQL_DATABASE" > mavuno.sql
mysql --host="$MYSQL_RESTORE_HOST" --user="$MYSQL_RESTORE_USER" \
  "$MYSQL_RESTORE_DATABASE" < mavuno.sql
alembic current
python scripts/smoke.py --base-url "$STAGING_URL"
```

Quarterly, restore the latest encrypted backup into an isolated database, compare table counts for
users, orders, payments, outbox jobs, and audit events, run migrations and smoke tests, then destroy
the isolated database. Record backup timestamp, restore duration, row-count differences, operator,
and evidence link. Production credentials and customer data must not enter CI artifacts.

## Secret and key rotation

Use overlapping keys where the protocol permits it. Add the new key, deploy readers/verifiers,
switch writers, verify provider callbacks and one reconciliation, then remove the old key after the
maximum token or callback retry lifetime. Rehearse this for JWT signing keys, profile encryption
keys, Daraja credentials, bank webhook secrets, push credentials, and premium-provider credentials.
A callback-token change requires coordinating the provider URL before retiring the old deployment.

## Incident checklist

- Correlate reports using `X-Request-ID` and `traceparent`; never request passwords, OTPs, access
  tokens, bank payloads, or M-Pesa credentials.
- Treat callbacks as untrusted until server-to-server reconciliation succeeds.
- Pause affected mutations at the ingress when correctness is uncertain.
- Capture image digest, migration revision, dashboards, and redacted logs in the incident record.
- Reconcile payments, subscriptions, outbox jobs, and order state before reopening.

## Audit retention

Audit events are append-only. Restrict reads to authorized support and security roles, retain
production audit records for 24 months unless Kenyan legal or contractual requirements mandate
longer, and archive them encrypted with deletion holds for open incidents. Operational request logs
should normally expire after 30 days. Document every export and deletion; never log authentication
secrets or raw provider payloads.
