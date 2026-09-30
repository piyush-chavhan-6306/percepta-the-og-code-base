"""
PERCEPTA PathGuard REST API.
Provides endpoints to configure and inspect authorized transit corridors and route integrity alerts.
"""
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from backend.zones.pathguard import TransitCorridor, get_pathguard_monitor

router = APIRouter(prefix="/api/pathguard", tags=["PathGuard"])


class CorridorModel(BaseModel):
    corridor_id: str
    name: str
    camera_id: str
    waypoints: List[Tuple[float, float]]
    allowed_width_px: float = 65.0
    allowed_classes: List[str] = ["person", "car", "truck"]
    is_active: bool = True
    min_deviation_seconds: float = 1.5


@router.get("/corridors", response_model=List[CorridorModel])
async def list_corridors(camera_id: Optional[str] = Query(None)):
    """List all configured authorized transit corridors."""
    monitor = get_pathguard_monitor()
    corridors = monitor.list_corridors(camera_id=camera_id)
    return [
        CorridorModel(
            corridor_id=c.corridor_id,
            name=c.name,
            camera_id=c.camera_id,
            waypoints=c.waypoints,
            allowed_width_px=c.allowed_width_px,
            allowed_classes=list(c.allowed_classes),
            is_active=c.is_active,
            min_deviation_seconds=c.min_deviation_seconds,
        )
        for c in corridors
    ]


@router.post("/corridors", response_model=CorridorModel)
async def create_or_update_corridor(model: CorridorModel):
    """Register or update an authorized patrol / transit corridor."""
    monitor = get_pathguard_monitor()
    corridor = TransitCorridor(
        corridor_id=model.corridor_id,
        name=model.name,
        camera_id=model.camera_id,
        waypoints=model.waypoints,
        allowed_width_px=model.allowed_width_px,
        allowed_classes=set(model.allowed_classes),
        is_active=model.is_active,
        min_deviation_seconds=model.min_deviation_seconds,
    )
    monitor.add_corridor(corridor)
    return model


@router.delete("/corridors/{corridor_id}")
async def delete_corridor(corridor_id: str):
    """Remove a transit corridor."""
    monitor = get_pathguard_monitor()
    if not monitor.remove_corridor(corridor_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Corridor '{corridor_id}' not found",
        )
    return {"status": "deleted", "corridor_id": corridor_id}


@router.get("/status")
async def get_pathguard_status():
    """Retrieve current route integrity system status."""
    monitor = get_pathguard_monitor()
    corrs = monitor.list_corridors()
    return {
        "status": "active",
        "total_corridors": len(corrs),
        "monitored_cameras": list(set(c.camera_id for c in corrs)),
        "active_deviations": len(monitor._deviation_start_times),
    }
