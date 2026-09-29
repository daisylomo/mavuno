from __future__ import annotations

import json
import logging

from mavuno.core.logging import JsonFormatter, request_id_context, trace_id_context


def test_json_logs_include_correlation_and_redact_nested_credentials() -> None:
    request_token = request_id_context.set("request-1")
    trace_token = trace_id_context.set("a" * 32)
    try:
        record = logging.makeLogRecord(
            {
                "name": "mavuno.test",
                "levelno": logging.INFO,
                "levelname": "INFO",
                "msg": "Authorization: Bearer visible-token",
                "args": (),
                "payload": {
                    "password": "visible-password",
                    "profile": {"phone": "+254700000000"},
                },
            }
        )
        output = json.loads(JsonFormatter().format(record))
    finally:
        request_id_context.reset(request_token)
        trace_id_context.reset(trace_token)

    assert output["request_id"] == "request-1"
    assert output["trace_id"] == "a" * 32
    assert output["message"] == "Authorization: Bearer [REDACTED]"
    assert output["payload"]["password"] == "[REDACTED]"
    assert output["payload"]["profile"]["phone"] == "+254700000000"
