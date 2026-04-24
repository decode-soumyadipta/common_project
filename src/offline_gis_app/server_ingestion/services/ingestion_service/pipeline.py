from __future__ import annotations

from typing import Iterable
from collections.abc import Callable

from offline_gis_app.server_ingestion.services.ingestion_service.context import (
    IngestionContext,
)
from offline_gis_app.server_ingestion.services.ingestion_service.contracts import (
    IngestionStage,
)


class IngestionPipeline:
    """Executes deterministic ingestion stages for one source raster."""

    def __init__(self, stages: Iterable[IngestionStage]):
        self._stages = list(stages)

    def run(
        self,
        context: IngestionContext,
        *,
        on_stage_completed: Callable[[str], None] | None = None,
    ) -> IngestionContext:
        skip_until = context.resume_from_stage
        skipping = bool(skip_until)
        for stage in self._stages:
            if skipping:
                context.stages_completed.append(stage.name)
                if stage.name == skip_until:
                    skipping = False
                continue
            context.report(stage.message)
            stage.run(context)
            context.stages_completed.append(stage.name)
            context.last_stage_completed = stage.name
            if on_stage_completed is not None:
                on_stage_completed(stage.name)
        return context
