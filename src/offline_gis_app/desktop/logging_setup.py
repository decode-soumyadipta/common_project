from __future__ import annotations

import logging
import os


def configure_desktop_logging() -> None:
    level_name = os.getenv("DESKTOP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Keep app logs detailed, but suppress low-level HTTP internals.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("desktop.web").setLevel(logging.INFO)
