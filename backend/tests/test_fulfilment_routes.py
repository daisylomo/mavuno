from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mavuno.api.v1 import fulfilment as routes
from mavuno.auth.context import AuthenticatedUser
from mavuno.fulfilment.schemas import FulfilmentTransition, FulfilmentUpdate


@pytest.mark.anyio
async def test_fulfilment_routes_delegate_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    actor = AuthenticatedUser(uuid4(), "buyer@example.test", None, frozenset({"buyer"}), 0)
    order_id = uuid4()
    service = MagicMock()
    service.get = AsyncMock(return_value="stored")
    service.update = AsyncMock(return_value="updated")
    service.transition = AsyncMock(return_value="transitioned")
    monkeypatch.setattr(routes, "FulfilmentService", lambda *_args: service)
    session = MagicMock()

    fetched: Any = await routes.get_fulfilment(order_id, actor, session)
    updated: Any = await routes.update_fulfilment(
        order_id, FulfilmentUpdate(coordination_notes="Call first"), actor, session
    )
    transitioned: Any = await routes.transition_fulfilment(
        order_id, FulfilmentTransition(status="scheduled", expected_version=1), actor, session
    )

    assert (fetched, updated, transitioned) == ("stored", "updated", "transitioned")
