from pydantic import BaseModel, Field


class RegisterRasterRequest(BaseModel):
    path: str = Field(min_length=1)


class RasterPoint(BaseModel):
    lon: float
    lat: float


class ProfileRequest(BaseModel):
    path: str = Field(min_length=1)
    line_points: list[RasterPoint] = Field(min_length=2)
    samples: int = Field(default=200, ge=2, le=5000)

