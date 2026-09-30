"""
Border Intelligence Spatial Breach Heatmap Density Matrix Module.
Generates normalized 2D density matrices of target movement trajectories and perimeter breach hotspots.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.events.store import EventStore, get_event_store


class HeatmapResponse(BaseModel):
    camera_id: str
    grid_size: int = 16
    total_points: int
    max_density: int
    density_matrix: List[List[float]] = Field(..., description="Normalized 2D density grid (0.0 - 1.0)")
    hotspots_identified: int
    summary: str


class SpatialHeatmapEngine:
    """Computes spatial density grids from persistent trajectory coordinates."""

    def __init__(self, store: Optional[EventStore] = None) -> None:
        self.store = store or get_event_store()

    async def generate_heatmap(
        self,
        camera_id: str,
        grid_size: int = 16,
        frame_width: float = 1280.0,
        frame_height: float = 720.0,
        limit: int = 500,
    ) -> HeatmapResponse:
        """Compute normalized 2D density grid for camera coordinates."""
        events = await self.store.get_events(camera_id=camera_id, limit=limit, newest_first=True)

        points = []
        for e in events:
            raw_payload = e.get("payload", {})
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {}
            else:
                payload = raw_payload or {}

            # Extract position
            pos = payload.get("position")
            if pos and len(pos) >= 2:
                points.append((float(pos[0]), float(pos[1])))
            elif payload.get("bounding_box") and len(payload["bounding_box"]) >= 4:
                bb = payload["bounding_box"]
                cx = (bb[0] + bb[2]) / 2.0
                cy = (bb[1] + bb[3]) / 2.0
                points.append((cx, cy))

        # Build raw count grid
        grid = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
        for x, y in points:
            col = int(min(max(0.0, x / frame_width), 0.999) * grid_size)
            row = int(min(max(0.0, y / frame_height), 0.999) * grid_size)
            grid[row][col] += 1

        max_val = max((max(row) for row in grid), default=0)
        norm_grid = [
            [round(val / max_val, 3) if max_val > 0 else 0.0 for val in row]
            for row in grid
        ]

        hotspots = sum(1 for row in norm_grid for val in row if val >= 0.6)

        return HeatmapResponse(
            camera_id=camera_id,
            grid_size=grid_size,
            total_points=len(points),
            max_density=max_val,
            density_matrix=norm_grid,
            hotspots_identified=hotspots,
            summary=(
                f"Generated {grid_size}x{grid_size} spatial density map from {len(points)} persistent track points. "
                f"Identified {hotspots} high-density corridor hotspots."
            ),
        )


global_heatmap_engine = SpatialHeatmapEngine()


def get_heatmap_engine() -> SpatialHeatmapEngine:
    return global_heatmap_engine
