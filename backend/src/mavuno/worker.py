from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from datetime import timedelta
from uuid import UUID

from mavuno.commerce.repository import CommerceRepository
from mavuno.commerce.service import CheckoutService, PaymentService, _now
from mavuno.core.config import Settings, get_settings
from mavuno.core.logging import configure_logging
from mavuno.core.performance import CatalogCache, PerformanceMetrics, RedisBackend
from mavuno.db import Database
from mavuno.messaging.provider import HttpPushProvider, PushProviderError
from mavuno.messaging.repository import MessagingRepository
from mavuno.messaging.service import NotificationDeliveryService
from mavuno.payments.provider import PaymentProviderError
from mavuno.premium.provider import PremiumProviderError
from mavuno.premium.repository import PremiumRepository
from mavuno.premium.service import SubscriptionService
from mavuno.profiles.push_tokens import PushTokenProtector

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("MAVUNO_DATABASE_URL is required for the worker")
    configure_logging(settings.log_config_path, settings.log_level)
    database = Database(settings)
    metrics = PerformanceMetrics()
    redis = RedisBackend(settings, metrics)
    catalog_cache = CatalogCache(redis, settings)
    database.catalog_cache = catalog_cache
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(name, stopping.set)
    try:
        while not stopping.is_set():
            await process_batch(database, settings)
            with suppress(TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=settings.worker_poll_seconds)
    finally:
        await database.dispose()
        await redis.close()


async def process_batch(database: Database, settings: Settings) -> int:
    possible_cache = getattr(database, "catalog_cache", None)
    catalog_cache = possible_cache if isinstance(possible_cache, CatalogCache) else None
    now = _now()
    async with database.session() as session:
        repository = CommerceRepository(session)
        jobs = await repository.claim_jobs(
            now, now + timedelta(seconds=settings.outbox_lease_seconds)
        )
    for job in jobs:
        async with database.session() as session:
            repository = CommerceRepository(session)
            current = await session.get(type(job), job.id)
            if current is None:
                continue
            try:
                if job.job_type == "payment_status_query":
                    await PaymentService(repository, settings).reconcile(
                        UUID(str(job.payload["payment_id"]))
                    )
                elif job.job_type == "order_expire":
                    await CheckoutService(repository, settings, catalog_cache).expire(
                        UUID(str(job.payload["order_id"]))
                    )
                elif job.job_type == "notification_push":
                    if (
                        settings.notification_push_url is None
                        or settings.notification_push_api_key is None
                        or settings.push_token_encryption_key is None
                        or settings.push_token_hash_key is None
                    ):
                        raise PushProviderError("push delivery is not configured")
                    messaging_repository = MessagingRepository(session)
                    provider = HttpPushProvider(
                        str(settings.notification_push_url),
                        settings.notification_push_api_key.get_secret_value(),
                        settings.notification_push_timeout_seconds,
                    )
                    protector = PushTokenProtector(
                        encryption_key=settings.push_token_encryption_key,
                        hash_key=settings.push_token_hash_key,
                    )
                    await NotificationDeliveryService(
                        messaging_repository, provider, protector
                    ).deliver(UUID(str(job.payload["notification_id"])))
                elif job.job_type == "subscription_status_query":
                    await SubscriptionService(PremiumRepository(session), settings).reconcile(
                        UUID(str(job.payload["subscription_id"]))
                    )
                current.status = "completed"
                current.completed_at = _now()
                current.leased_until = None
                await session.commit()
            except (PaymentProviderError, PushProviderError, PremiumProviderError) as exc:
                current.last_error = str(exc)[:255]
                current.leased_until = None
                if current.attempts >= current.max_attempts:
                    current.status = "dead_letter"
                else:
                    current.status = "retry"
                    current.available_at = _now() + timedelta(
                        seconds=min(2**current.attempts, settings.outbox_retry_cap_seconds)
                    )
                await session.commit()
                logger.warning("Outbox provider job failed", extra={"job_id": str(current.id)})
    return len(jobs)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
