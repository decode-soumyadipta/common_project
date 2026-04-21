from __future__ import annotations

from typing import Protocol


class IngestionStage(Protocol):
    """Single stage contract for ingestion pipelines."""

    name: str

    def run(self, source_path: str) -> None:
        ...
