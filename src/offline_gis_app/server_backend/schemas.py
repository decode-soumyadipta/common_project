from pydantic import BaseModel, Field, model_validator


class RegisterRasterRequest(BaseModel):
    path: str = Field(min_length=1)


class RasterPoint(BaseModel):
    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)


class ProfileRequest(BaseModel):
    path: str = Field(min_length=1)
    line_points: list[RasterPoint] = Field(min_length=2)
    samples: int = Field(default=200, ge=2, le=5000)


class CoordinateSearchRequest(BaseModel):
    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)


class BBoxSearchRequest(BaseModel):
    west: float = Field(ge=-180.0, le=180.0)
    south: float = Field(ge=-90.0, le=90.0)
    east: float = Field(ge=-180.0, le=180.0)
    north: float = Field(ge=-90.0, le=90.0)

    @model_validator(mode="after")
    def _validate_non_zero_area(self) -> "BBoxSearchRequest":
        if self.west == self.east or self.south == self.north:
            raise ValueError("Bounding box must span a non-zero area.")
        return self


class PolygonSearchRequest(BaseModel):
    points: list[RasterPoint] = Field(min_length=3)
    buffer_meters: float = Field(default=0.0, ge=0.0)


class IngestQueueRequest(BaseModel):
    paths: list[str] = Field(min_length=1)


class IngestJobResponse(BaseModel):
    id: str
    status: str
    total_items: int
    processed_items: int
    failed_items: int
    checkpoint_item_index: int
    progress_percent: int = 0
    current_step: str | None = None
    current_item_path: str | None = None
    elapsed_seconds: float | None = None
    started_at: str | None = None
    completed_at: str | None = None
    last_checkpoint_at: str | None = None
    last_error: str | None = None
