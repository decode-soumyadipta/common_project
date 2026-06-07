"""Centralized logging configuration for all services and clients.

Adapted from src/client_desktop/backend/logging_setup.py and extended
with structured JSON logging, file output, and log rotation support.

Usage:
    from src_new.shared.utils.logging_config import configure_logging
    configure_logging()  # Call once at service startup

Environment variables (read via src_new.shared.config):
    LOG_LEVEL       - Logging level (default: INFO)
    LOG_FORMAT      - "text" or "json" (default: text)
    LOG_OUTPUT_PATH - Path to log file; empty = stdout only (default: "")
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from typing import Optional


# --------------------------------------------------------------------------- JSON formatter for structured logging ---------------------------------------------------------------------------


class _JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects.

    Each record includes: timestamp, level, logger, message, and any
    extra fields attached to the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Include any extra fields attached via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                try:
                    json.dumps(value)  # Only include JSON-serializable extras
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        return json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------- Text formatter (human-readable) ---------------------------------------------------------------------------

_TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# --------------------------------------------------------------------------- Public API ---------------------------------------------------------------------------


def configure_logging(
    level: Optional[str] = None,
    log_format: Optional[str] = None,
    output_path: Optional[str] = None,
    max_bytes: int = 50 * 1024 * 1024,  # 50 MB per file
    backup_count: int = 5,
) -> None:
    """Configure the root logger for the entire process.

    Parameters are read from environment variables if not provided explicitly.
    This function is idempotent — calling it multiple times is safe.

    Args:
        level: Logging level string (DEBUG/INFO/WARNING/ERROR/CRITICAL).
               Falls back to LOG_LEVEL env var, then "INFO".
        log_format: "text" or "json". Falls back to LOG_FORMAT env var, then "text".
        output_path: Path to a log file. Falls back to LOG_OUTPUT_PATH env var.
                     Empty string or None means stdout only.
        max_bytes: Maximum size of each log file before rotation.
        backup_count: Number of rotated log files to keep.
    """
    # Resolve parameters from env vars if not explicitly provided
    level = level or os.getenv("LOG_LEVEL", "INFO")
    log_format = log_format or os.getenv("LOG_FORMAT", "text")
    output_path = output_path if output_path is not None else os.getenv("LOG_OUTPUT_PATH", "")

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Choose formatter
    if log_format.lower() == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(fmt=_TEXT_FORMAT, datefmt=_DATE_FORMAT)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicate output on re-configuration
    root_logger.handlers.clear()

    # Always add a stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(numeric_level)
    root_logger.addHandler(stdout_handler)

    # Optionally add a rotating file handler
    if output_path:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                output_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(numeric_level)
            root_logger.addHandler(file_handler)
        except OSError as exc:
            root_logger.warning("Could not open log file %r: %s", output_path, exc)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    root_logger.debug(
        "Logging configured: level=%s format=%s output=%r",
        level.upper(),
        log_format,
        output_path or "stdout",
    )


def configure_desktop_logging() -> None:
    """Convenience wrapper for desktop client logging setup.

    Reads DESKTOP_LOG_LEVEL (falls back to LOG_LEVEL, then INFO).
    Preserved for backward compatibility with the original logging_setup.py.
    """
    level = os.getenv("DESKTOP_LOG_LEVEL") or os.getenv("LOG_LEVEL", "INFO")
    configure_logging(level=level, log_format="text", output_path="")


def get_service_logger(service_name: str) -> logging.Logger:
    """Return a named logger for a service.

    Args:
        service_name: Short name, e.g. "ingestion", "query", "tile_serving".

    Returns:
        A Logger instance under the "src_new.<service_name>" namespace.
    """
    return logging.getLogger(f"src_new.{service_name}")


__all__ = [
    "configure_logging",
    "configure_desktop_logging",
    "get_service_logger",
]
