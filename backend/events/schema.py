"""
Border Intelligence Event Schema Module.
Defines all typed Pydantic event models with validated serialization and deserialization.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    DETECTION = "DETECTION"
    TRACKING = "TRACKING"
    ZONE = "ZONE"
    RISK = "RISK"
    EVIDENCE = "EVIDENCE"
    ALERT = "ALERT"
    INCIDENT = "INCIDENT"
    HANDOFF = "HANDOFF"   # P1 Cross-camera
    SYSTEM = "SYSTEM"     # Failure, recovery, degradation
    ANPR = "ANPR"         # Modular License Plate Prototype
    FACE = "FACE"         # Face Detection Analytics (Non-biometric)
    CORRELATION = "CORRELATION" # Multi-Camera Spatial-Temporal Correlation


class SourceType(str, Enum):
    VIDEO_FILE = "video_file"
    SIMULATION = "simulation"
    RADAR_SIM = "radar_sim"
    RF_SIM = "rf_sim"
    THERMAL_SIM = "thermal_sim"
    UNAVAILABLE = "unavailable"


class BaseEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    camera_id: str
    track_id: Optional[Union[str, int]] = None
    incident_id: Optional[str] = None
    confidence: Optional[float] = None
    source: SourceType = SourceType.VIDEO_FILE


class DetectionEvent(BaseEvent):
    event_type: EventType = EventType.DETECTION
    object_class: str  # e.g., "person", "vehicle", "drone"
    bounding_box: List[float]  # [x1, y1, x2, y2]
    frame_number: int


class TrackingEvent(BaseEvent):
    event_type: EventType = EventType.TRACKING
    lifecycle: str  # "created", "updated", "lost", "recovered", "terminated"
    position: List[float]  # [cx, cy]
    velocity: List[float]  # [dx, dy]
    object_class: Optional[str] = None
    bounding_box: Optional[List[float]] = None  # [x1, y1, x2, y2]
    frame_number: Optional[int] = None
    speed: Optional[float] = None  # pixels/frame
    direction: Optional[float] = None  # degrees (0-360)
    cardinal_heading: Optional[str] = None  # e.g. "NE", "S", "STATIONARY"
    speed_description: Optional[str] = None  # e.g. "Moving (~2.4 m/s est)" or "Stationary"
    current_zone: Optional[str] = None
    previous_zone: Optional[str] = None
    zone_dwell_seconds: Optional[float] = None
    movement_state: Optional[str] = None  # "APPROACHING_RESTRICTED", "RECEDING", "CROSSING", "LOITERING"
    heading_towards_protected: Optional[bool] = False
    is_night_movement: Optional[bool] = False
    threat_score: Optional[float] = None


class ZoneEvent(BaseEvent):
    event_type: EventType = EventType.ZONE
    zone_id: str
    zone_name: str
    zone_severity: str  # "warning", "restricted", "critical"
    transition: str  # "entered", "exited", "dwelling", "crossed", "loitering"
    dwell_duration_seconds: Optional[float] = None
    crossing_direction: Optional[str] = None  # "inbound", "outbound", "A_TO_B", "B_TO_A"
    narrative: Optional[str] = None  # e.g., "PERSON #27 entered Restricted Zone A and moved NE toward Checkpoint B."
    threat_score: Optional[float] = None
    threat_reasons: Optional[List[str]] = None


class RiskEvent(BaseEvent):
    event_type: EventType = EventType.RISK
    risk_level: str  # "low", "medium", "high", "critical"
    threat_score: float = 0.0
    reasons: List[str] = Field(default_factory=list)  # Explainable human-readable rule list


class EvidenceType(str, Enum):
    PERSON = "PERSON"
    FACE = "FACE"
    VEHICLE = "VEHICLE"
    ANPR = "ANPR"
    ZONE_VIOLATION = "ZONE_VIOLATION"
    TRIPWIRE_VIOLATION = "TRIPWIRE_VIOLATION"
    LOITERING = "LOITERING"
    THREAT = "THREAT"
    INCIDENT_CONTEXT = "INCIDENT_CONTEXT"


class EvidenceEvent(BaseEvent):
    event_type: EventType = EventType.EVIDENCE
    evidence_id: str = Field(default_factory=lambda: f"EVID_{uuid4().hex[:12]}")
    evidence_type: str = EvidenceType.INCIDENT_CONTEXT.value
    frame_path: Optional[str] = None
    file_path: Optional[str] = None
    file_uri: Optional[str] = None
    sha256_hash: Optional[str] = None
    frame_number: int = 0
    trigger_reason: str = "INCIDENT_CONTEXT"
    frame_type: str = "trigger"  # "pre_event", "trigger", "post_event"
    bounding_box: Optional[List[float]] = None
    object_class: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    tripwire_id: Optional[str] = None
    tripwire_name: Optional[str] = None
    severity: Optional[str] = None
    alert_id: Optional[str] = None
    anpr_result: Optional[Dict[str, Any]] = None
    face_metadata: Optional[Dict[str, Any]] = None
    sharpness_score: Optional[float] = None
    target_crop_uri: Optional[str] = None
    target_sha256_hash: Optional[str] = None


class AlertEvent(BaseEvent):
    event_type: EventType = EventType.ALERT
    alert_id: UUID = Field(default_factory=uuid4)
    severity: str  # "NORMAL", "RESTRICTED", "CRITICAL"
    message: str
    is_acknowledged: bool = False
    threat_score: Optional[float] = None
    threat_level: Optional[str] = None  # "NORMAL", "RESTRICTED", "CRITICAL"
    threat_reasons: Optional[List[str]] = None
    causal_chain: Optional[List[str]] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    object_class: Optional[str] = None
    evidence_snapshot_uri: Optional[str] = None
    target_crop_uri: Optional[str] = None
    face_snapshot_uri: Optional[str] = None
    anpr_snapshot_uri: Optional[str] = None
    evidence_id: Optional[str] = None
    sha256_hash: Optional[str] = None
    best_frame_number: Optional[int] = None
    modality: str = "STANDARD"
    timeline_offset_sec: Optional[float] = None
    heading: Optional[str] = None
    speed_description: Optional[str] = None


class IncidentEvent(BaseEvent):
    event_type: EventType = EventType.INCIDENT
    lifecycle: str  # "opened", "updated", "closed"
    event_ids: List[UUID] = Field(default_factory=list)
    severity: Optional[str] = None
    message: Optional[str] = None


class SystemEvent(BaseEvent):
    event_type: EventType = EventType.SYSTEM
    subtype: str  # "camera_unavailable", "camera_recovered", "model_error",
                  # "pipeline_degraded", "pipeline_recovered", "evidence_unavailable", "database_error", "camera_health_warning"
    details: str


class CameraHandoffEvent(BaseEvent):  # P1
    event_type: EventType = EventType.HANDOFF
    from_camera_id: str
    to_camera_id: str
    association_score: float
    association_status: str  # "likely", "ambiguous", "rejected"


class ANPREvent(BaseEvent):
    event_type: EventType = EventType.ANPR
    plate_number: str
    vehicle_class: str
    detection_confidence: float
    is_verified_format: bool = True
    evidence_snapshot_uri: Optional[str] = None
    notes: Optional[str] = "Modular ANPR Prototype (SIH26187 Alignment)"


class FaceAnalyticsEvent(BaseEvent):
    event_type: EventType = EventType.FACE
    face_detected: bool = True
    face_bounding_box: List[float]  # [x1, y1, x2, y2]
    identity_claim: str = "UNIDENTIFIED (Detection Only — Non-Biometric)"
    evidence_snapshot_uri: Optional[str] = None


class CorrelationEvent(BaseEvent):
    event_type: EventType = EventType.CORRELATION
    source_camera: str
    target_camera: str
    source_zone: Optional[str] = None
    target_zone: Optional[str] = None
    time_delta_seconds: float
    correlation_confidence: float
    correlation_label: str = "Probable cross-camera event correlation"
    narrative: str


def normalize_severity(val: Any) -> str:
    """
    Authoritative severity normalization.
    Returns strictly 'CRITICAL', 'RESTRICTED', or 'NORMAL'.
    Missing or unrecognized values safely default to 'NORMAL' (never escalated).
    """
    if not val:
        return "NORMAL"
    val_name = getattr(val, "name", None)
    if val_name in ("CRITICAL", "RESTRICTED", "NORMAL"):
        return val_name
    s = str(getattr(val, "value", val)).strip().lower()
    if s in ("critical", "high", "defcon_red", "red"):
        return "CRITICAL"
    elif s in ("restricted", "warning", "medium", "defcon_yellow", "defcon_orange", "yellow", "orange"):
        return "RESTRICTED"
    elif s in ("normal", "low", "info", "green", "defcon_green"):
        return "NORMAL"
    return "NORMAL"
