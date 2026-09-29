# Release status

The current hosted environment uses sandbox M-Pesa and test APK signing.
Release it as an Android **prerelease**, not as a production payment application.
No real payment is collected. The browser admin portal is served by the API at
`/admin`, and requires an existing `administrator` account.

## Included workflows

- Buyer and farmer registration, login, profile editing and role routing.
- Farmer listings, camera/gallery photos, public farm profiles and inventory.
- Buyer browsing, cart, addresses, checkout, order history and cancellation.
- Sandbox payment reconciliation, stock reservations and refund tracking.
- Farmer-specific order confirmation and handover for mixed-farmer orders.
- Backend conversations, notifications, premium entitlements and prebookings.
  Provider-dependent features require their configured providers; the app does
  not offer a complete messaging or premium-management interface.
- Browser administration for category/product creation and outstanding refunds.
  Account provisioning and broader moderation remain operator tasks.

## Validation

Local validation on 29 September 2026 passed 200 backend tests (91.77% coverage),
14 Python API-client journeys, 48 frontend tests, TypeScript, Ruff and mypy.
MySQL 8.4 and Redis 7 were disposable local containers; all nine migrations
applied successfully. Expo web export succeeded. Android APK installation and
startup are verified on an API 35 emulator; release-specific evidence belongs
in the GitHub release notes.

## CI and release publication

Backend CI runs on `main` and relevant pull requests. Android CI runs backend
validation and frontend tests before compiling the APK. Tags beginning with
`v` publish an APK and `SHA256SUMS.txt` as a sandbox prerelease. A failed check
prevents the build and publication. Download the APK from GitHub Releases and
verify it against the checksum before installing.

Render should deploy `main` after CI passes, using `backend/Dockerfile`,
`backend` as build context, `/app/entrypoint.sh`, and `/health/ready`.
The entrypoint applies migrations before starting the API and worker.

## Production gates

Before a stable production release, configure production Daraja credentials
and verify actual successful, failed, expired and refunded transactions with
the provider. Use a durable private Android release key or EAS-managed signing,
configure production provider integrations for enabled premium/push features,
and validate backup/restore, monitoring and expected hosting capacity.
Do not enable a provider-dependent feature without its provider credentials.
These gates cannot be inferred from passing automated tests or sandbox payments.
