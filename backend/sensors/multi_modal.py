"""
Border Intelligence Multi-Modal Sensor Ingestion & Extension Module.
Provides typed defense schemas for Radar, Ground Seismic, Thermal IR, and RF spectrum sensors.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from backend.events.schema import BaseEvent, EventType, SourceType
from backend.events.store import EventStore, get_event_store


class SensorType(str, Enum):
    RADAR = "RADAR"
    SEISMIC = "SEISMIC"
    THERMAL_IR = "THERMAL_IR"
    RF_DETECTOR = "RF_DETECTOR"


class RadarSensorPayload(BaseModel):
    range_meters: float
    azimuth_degrees: float
    velocity_mps: float
    radar_cross_section: Optional[float] = None  # dBsm


class SeismicSensorPayload(BaseModel):
    vibration_amplitude: float
    footstep_cadence_hz: Optional[float] = None
    estimated_mass_kg: Optional[float] = None


class ThermalIRPayload(BaseModel):
    temperature_delta_celsius: float
    hotspot_area_pixels: int


class MultiModalSensorIngestRequest(BaseModel):
    sensor_id: str
    sensor_type: SensorType
    sector_id: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MultiModalSensorManager:
    """Manages ingestion and normalization of secondary multi-modal defense sensors."""

    def __init__(self, store: Optional[EventStore] = None) -> None:
        self.store = store or get_event_store()
        self._active_sensors: Dict[str, Dict[str, Any]] = {
            "RADAR_ALPHA_01": {"type": "RADAR", "sector": "Sector Alpha", "status": "active"},
            "SEISMIC_BRAVO_01": {"type": "SEISMIC", "sector": "Sector Bravo", "status": "active"},
            "THERMAL_CHARLIE_01": {"type": "THERMAL_IR", "sector": "Sector Charlie", "status": "active"},
        }

    async def ingest_sensor_telemetry(self, request: MultiModalSensorIngestRequest) -> Dict[str, Any]:
        """Ingest and record multi-modal sensor telemetry to SQLite WAL store."""
        source_map = {
            SensorType.RADAR: SourceType.RADAR_SIM,
            SensorType.SEISMIC: SourceType.SIMULATION,
            SensorType.THERMAL_IR: SourceType.THERMAL_SIM,
            SensorType.RF_DETECTOR: SourceType.RF_SIM,
        }

        src = source_map.get(request.sensor_type, SourceType.SIMULATION)

        event = BaseEvent(
            event_type=EventType.DETECTION,
            camera_id=f"SENSOR_{request.sensor_id}",
            confidence=request.confidence,
            source=src,
            timestamp=request.timestamp,
        )

        payload_dict = {
            "sensor_id": request.sensor_id,
            "sensor_type": request.sensor_type.value,
            "sector_id": request.sector_id,
            "sensor_data": request.data,
        }

        # Update active sensor registry
        self._active_sensors[request.sensor_id] = {
            "type": request.sensor_type.value,
            "sector": request.sector_id,
            "last_seen": request.timestamp.isoformat(),
            "status": "active",
        }

        # Persist event
        from backend.incidents.models import EventLogModel
        from backend.database import get_session_factory
        import json

        factory = get_session_factory()
        async with factory() as session:
            row = EventLogModel(
                event_id=str(event.event_id),
                event_type="DETECTION",
                timestamp=event.timestamp,
                camera_id=f"SENSOR_{request.sensor_id}",
                confidence=request.confidence,
                source=src.value,
                payload=json.dumps(payload_dict),
            )
            session.add(row)
            await session.commit()

        return {
            "status": "ingested",
            "event_id": str(event.event_id),
            "sensor_id": request.sensor_id,
            "timestamp": request.timestamp.isoformat(),
        }

    def get_sensors_status(self) -> Dict[str, Any]:
        """Return status of all registered multi-modal sensor channels."""
        return {
            "total_sensors": len(self._active_sensors),
            "sensors": self._active_sensors,
        }


global_sensor_manager = MultiModalSensorManager()


def get_sensor_manager() -> MultiModalSensorManager:
    return global_sensor_manager
