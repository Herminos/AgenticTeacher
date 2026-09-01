"""Structured, redacted operational logs for API and model pipeline stages."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


_LOGGER_NAME = "agentic_teacher"
_ALLOWED_FIELDS = {
    "request_id",
    "agent_run_id",
    "stage",
    "status",
    "duration_ms",
    "first_token_ms",
    "generation_ms",
    "total_ms",
    "rewrite_ms",
    "assessment_ms",
    "retrieval_ms",
    "reranker_ms",
    "retrieval_attempts",
    "provider",
    "model",
    "subject",
    "attempt",
    "candidate_count",
    "result_count",
    "reranker_used",
    "sufficient",
    "rag_exhausted",
    "http_method",
    "http_path",
    "http_status",
    "input_chars",
    "output_chars",
    "error_type",
    "upstream_status",
    "validation_fields",
}


def _safe_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:512]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "event_fields", {})
        if isinstance(fields, dict):
            payload.update(
                {key: _safe_value(value) for key, value in fields.items() if key in _ALLOWED_FIELDS}
            )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    logging.getLogger(_LOGGER_NAME).log(level, event, extra={"event_fields": fields})
