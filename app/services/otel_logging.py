# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Structured logging with OpenTelemetry trace context."""

from __future__ import annotations

import json
import logging
from typing import Any

from opentelemetry import trace


class OTelStructuredFormatter(logging.Formatter):
    """Logging formatter that includes OTel trace_id and span_id in structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format record with OTel trace context as JSON.
        
        Adds:
        - trace_id: current OpenTelemetry trace ID (hex)
        - span_id: current OpenTelemetry span ID (hex)
        - timestamp: ISO 8601 timestamp
        - level: log level
        - logger: logger name
        - message: formatted message
        """
        # Get current span context
        span = trace.get_current_span()
        trace_id = format(span.get_span_context().trace_id, "032x") if span.is_recording() else ""
        span_id = format(span.get_span_context().span_id, "016x") if span.is_recording() else ""

        # Build structured log entry
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add trace context if available
        if trace_id:
            log_entry["trace_id"] = trace_id
        if span_id:
            log_entry["span_id"] = span_id

        # Add exception info if present
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            log_entry["exception"] = record.exc_text

        # Add any extra fields from the record
        # (custom fields passed via logging.info(..., extra={...}))
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "taskName",
            ):
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def configure_structured_logging(log_level: str = "INFO") -> None:
    """Configure root logger with OTel-aware structured logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add stdout handler with OTel formatter
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(OTelStructuredFormatter())
    root_logger.addHandler(stream_handler)
