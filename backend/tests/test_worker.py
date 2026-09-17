from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from mavuno import worker
from mavuno.commerce.service import _now
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import OutboxJob
from mavuno.payments.provider import PaymentProviderError


class SessionContext:
    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeDatabase:
    def __init__(self, sessions: list[MagicMock]) -> None:
        self.sessions = iter(sessions)

    def session(self) -> SessionContext:
        return SessionContext(next(self.sessions))


class StopAfterOneIteration:
    def __init__(self) -> None:
        self.checks = 0

    def is_set(self) -> bool:
        self.checks += 1
        return self.checks > 1

    async def wait(self) -> None:
        return None

    def set(self) -> None:
        self.checks = 2


def job(job_type: str, attempts: int = 1, max_attempts: int = 3) -> OutboxJob:
    key = "payment_id" if job_type == "payment_status_query" else "order_id"
    value = OutboxJob(
        id=uuid4(),
        job_type=job_type,
        dedupe_key=str(uuid4()),
        payload={key: str(uuid4())},
        status="processing",
        attempts=attempts,
        max_attempts=max_attempts,
        available_at=_now(),
        leased_until=_now() + timedelta(seconds=60),
    )
    return value


@pytest.mark.anyio
async def test_worker_processes_payment_and_expiration_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = [job("payment_status_query"), job("order_expire")]
    claim_repository = SimpleNamespace(claim_jobs=AsyncMock(return_value=jobs))
    repositories = iter([claim_repository, MagicMock(), MagicMock()])
    monkeypatch.setattr(worker, "CommerceRepository", lambda _session: next(repositories))

    payment_service = MagicMock()
    payment_service.reconcile = AsyncMock()
    checkout_service = MagicMock()
    checkout_service.expire = AsyncMock()
    monkeypatch.setattr(worker, "PaymentService", lambda *_args: payment_service)
    monkeypatch.setattr(worker, "CheckoutService", lambda *_args: checkout_service)

    claim_session = MagicMock()
    sessions: list[MagicMock] = [claim_session]
    for current in jobs:
        session = MagicMock()
        session.get = AsyncMock(return_value=current)
        session.commit = AsyncMock()
        sessions.append(session)
    count = await worker.process_batch(
        cast(Database, FakeDatabase(sessions)), Settings(environment="test")
    )
    assert count == 2
    payment_service.reconcile.assert_awaited_once()
    checkout_service.expire.assert_awaited_once()
    assert all(value.status == "completed" for value in jobs)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("attempts", "max_attempts", "expected"), [(1, 3, "retry"), (3, 3, "dead_letter")]
)
async def test_worker_retries_then_dead_letters_provider_failures(
    monkeypatch: pytest.MonkeyPatch, attempts: int, max_attempts: int, expected: str
) -> None:
    current = job("payment_status_query", attempts, max_attempts)
    claim_repository = SimpleNamespace(claim_jobs=AsyncMock(return_value=[current]))
    repositories = iter([claim_repository, MagicMock()])
    monkeypatch.setattr(worker, "CommerceRepository", lambda _session: next(repositories))
    payment_service = MagicMock()
    payment_service.reconcile = AsyncMock(side_effect=PaymentProviderError("temporarily offline"))
    monkeypatch.setattr(worker, "PaymentService", lambda *_args: payment_service)

    claim_session = MagicMock()
    work_session = MagicMock()
    work_session.get = AsyncMock(return_value=current)
    work_session.commit = AsyncMock()
    count = await worker.process_batch(
        cast(Database, FakeDatabase([claim_session, work_session])),
        Settings(environment="test"),
    )
    assert count == 1
    assert current.status == expected
    assert current.last_error == "temporarily offline"
    assert current.leased_until is None


@pytest.mark.anyio
async def test_run_worker_configures_processes_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        environment="test",
        database_url=SecretStr("mysql+aiomysql://user:password@database/mavuno"),
        worker_poll_seconds=1,
    )
    database = MagicMock()
    database.dispose = AsyncMock()
    loop = MagicMock()
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "configure_logging", MagicMock())
    monkeypatch.setattr(worker, "Database", lambda _settings: database)
    monkeypatch.setattr(asyncio, "Event", StopAfterOneIteration)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)
    process = AsyncMock(return_value=0)
    monkeypatch.setattr(worker, "process_batch", process)

    await worker.run_worker()
    process.assert_awaited_once_with(database, settings)
    database.dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_run_worker_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "get_settings", lambda: Settings(environment="test"))
    with pytest.raises(RuntimeError, match="MAVUNO_DATABASE_URL"):
        await worker.run_worker()
