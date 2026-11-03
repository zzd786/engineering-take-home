"""Safe application log format, levels and per-request correlation."""

import json
import logging
import os
from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
LOG_FIELDS = ("request_id", "method", "route", "status", "duration_ms", "error_kind")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Call sites must use fixed event names, never user input or exception text.
        output = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in LOG_FIELDS:
            if hasattr(record, field):
                output[field] = getattr(record, field)
        # Deliberately omit arbitrary extras, exception tracebacks and stack information.
        return json.dumps(output)


def configured_level() -> int:
    levels = {
        name: getattr(logging, name) for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    }
    return levels.get(os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    logger = logging.getLogger("diary")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(configured_level())
    # Keep propagation for external collectors/test capture; configure their privacy policy too.
    logging.getLogger("uvicorn.access").disabled = True
