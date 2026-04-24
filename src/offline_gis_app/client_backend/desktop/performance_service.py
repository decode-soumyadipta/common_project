from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderPolicyRecommendation:
    tile_cache_size: int
    terrain_cache_size: int
    lod_mode: str
    reason: str


class DesktopPerformanceService:
    """Provide adaptive cache/LOD recommendations for heavy raster scenes."""

    def recommend_policy(
        self, *, asset_count: int, dem_loaded: bool
    ) -> RenderPolicyRecommendation:
        if asset_count >= 50:
            return RenderPolicyRecommendation(
                tile_cache_size=160,
                terrain_cache_size=256,
                lod_mode="aggressive",
                reason="High layer count detected; reduce cache pressure to avoid stalls",
            )
        if asset_count >= 20 or dem_loaded:
            return RenderPolicyRecommendation(
                tile_cache_size=200,
                terrain_cache_size=320,
                lod_mode="balanced",
                reason="Medium load profile; keep balanced caching for smooth pan/zoom",
            )
        return RenderPolicyRecommendation(
            tile_cache_size=240,
            terrain_cache_size=512,
            lod_mode="quality",
            reason="Low load profile; maximize visual quality and cache retention",
        )
