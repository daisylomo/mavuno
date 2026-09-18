from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx2 as httpx


class PushProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PushPayload:
    title: str
    body: str
    data: dict[str, object]


class PushProvider(Protocol):
    async def send(self, token: str, payload: PushPayload, idempotency_key: str) -> str: ...


class UnconfiguredPushProvider:
    async def send(self, token: str, payload: PushPayload, idempotency_key: str) -> str:
        del token, payload, idempotency_key
        raise PushProviderError("push provider is not configured")


class HttpPushProvider:
    def __init__(self, endpoint: str, api_key: str, timeout: float = 10.0) -> None:
        self.endpoint, self.api_key, self.timeout = endpoint, api_key, timeout

    async def send(self, token: str, payload: PushPayload, idempotency_key: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Idempotency-Key": idempotency_key,
                    },
                    json={
                        "token": token,
                        "title": payload.title,
                        "body": payload.body,
                        "data": payload.data,
                    },
                )
            response.raise_for_status()
            value = response.json()
            return str(value["message_id"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise PushProviderError("push provider request failed") from exc
