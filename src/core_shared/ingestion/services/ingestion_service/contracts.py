from __future__ import annotations

from typing import Protocol

from core_shared.ingestion.services.ingestion_service.context import (
    IngestionContext,
)


class IngestionStage(Protocol):
    """Single stage contract for ingestion pipelines."""

    name: str
    message: str

    def run(self, context: IngestionContext) -> None: ...
