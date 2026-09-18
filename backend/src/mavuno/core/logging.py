from __future__ import annotations

import json
import logging
import logging.config
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_STANDARD_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "color_message",
}
_SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|cookie|password|secret|token|api_key|private_key)($|_)", re.I
)
_BEARER_VALUE = re.compile(r"(?i)bearer\s+[^\s,;]+")

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_context: ContextVar[str | None] = ContextVar("trace_id", default=None)


def redact(value: Any, key: str = "") -> Any:
    """Recursively redact credentials before structured data reaches stdout."""
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _BEARER_VALUE.sub("Bearer [REDACTED]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        trace_id = trace_id_context.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if trace_id is not None:
            payload["trace_id"] = trace_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(redact(payload), default=str, separators=(",", ":"))


def configure_logging(config_path: Path, level: str) -> None:
    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    config["root"]["level"] = level
    logging.config.dictConfig(config)
