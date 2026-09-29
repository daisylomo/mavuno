from __future__ import annotations

import logging
import re
import secrets
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mavuno.core.logging import request_id_context, trace_id_context
from mavuno.core.performance import (
    PerformanceMetrics,
    begin_query_budget,
    end_query_budget,
    query_count,
)

REQUEST_ID_HEADER = "X-Request-ID"
TRACEPARENT_HEADER = "traceparent"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_VALID_TRACEPARENT = re.compile(
    r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-([\da-f]{2})$", re.IGNORECASE
)
logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, metrics: PerformanceMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied_request_id = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = (
            supplied_request_id
            if supplied_request_id and _VALID_REQUEST_ID.fullmatch(supplied_request_id)
            else str(uuid4())
        )
        scope.setdefault("state", {})["request_id"] = request_id
        traceparent = Headers(scope=scope).get(TRACEPARENT_HEADER, "")
        trace_match = _VALID_TRACEPARENT.fullmatch(traceparent)
        trace_id = trace_match.group(1).lower() if trace_match else uuid4().hex
        span_id = secrets.token_hex(8)
        response_traceparent = f"00-{trace_id}-{span_id}-01"
        scope["state"]["trace_id"] = trace_id
        request_token = request_id_context.set(request_id)
        trace_token = trace_id_context.set(trace_id)
        started_at = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
                MutableHeaders(scope=message).append(TRACEPARENT_HEADER, response_traceparent)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            self.metrics.increment("http_requests_total")
            self.metrics.increment(f"http_responses_{status_code // 100}xx_total")
            for boundary in (100, 250, 500, 1000, 2500, 5000):
                if duration_ms <= boundary:
                    self.metrics.increment(f"http_request_duration_le_{boundary}ms_total")
            self.metrics.increment("http_request_duration_le_inf_total")
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_context.reset(request_token)
            trace_id_context.reset(trace_token)


class QueryBudgetMiddleware:
    """Observe per-request SQL counts without turning telemetry into an outage source."""

    def __init__(self, app: ASGIApp, budget: int, metrics: PerformanceMetrics) -> None:
        self.app = app
        self.budget = budget
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = begin_query_budget()

        async def send_with_query_count(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("X-DB-Query-Count", str(query_count.get()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_query_count)
        finally:
            count = query_count.get()
            self.metrics.increment("database_queries_total", count)
            if count > self.budget:
                self.metrics.increment("database_query_budget_exceeded_total")
                logger.warning(
                    "Request exceeded database query budget",
                    extra={
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "query_count": count,
                        "query_budget": self.budget,
                    },
                )
            end_query_budget(token)
