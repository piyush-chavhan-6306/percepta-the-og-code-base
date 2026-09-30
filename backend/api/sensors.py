"""
Border Intelligence Multi-Modal Defense Sensor REST API.
Provides endpoints for secondary sensor ingestion (Radar, Seismic, Thermal IR, RF) and status queries.
"""
from typing import Any, Dict
from fastapi import APIRouter

from backend.sensors.multi_modal import (
    MultiModalSensorIngestRequest,
    get_sensor_manager,
)

router = APIRouter(prefix="/api/sensors", tags=["Multi-Modal Sensors"])


@router.post("/ingest")
async def ingest_sensor_event(request: MultiModalSensorIngestRequest) -> Dict[str, Any]:
    """
    Ingest external sensor telemetry (Radar track, Ground Seismic vibration, Thermal IR signature, RF trigger).
    Validates payload against typed defense schemas and persists to SQLite WAL store.
    """
    manager = get_sensor_manager()
    return await manager.ingest_sensor_telemetry(request)


@router.get("/status")
async def get_sensors_status() -> Dict[str, Any]:
    """Retrieve status and connectivity for all registered multi-modal sensor channels."""
    manager = get_sensor_manager()
    return manager.get_sensors_status()
