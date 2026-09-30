"""
PERCEPTA SHARED DATA SCHEMAS
Universal Pydantic contracts shared across Online and Offline systems.
"""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class IncidentSyncPacket(BaseModel):
    sync_id: str
    source_device_id: str
    incident_id: str
    camera_id: str
    event_type: str
    severity: Literal["NORMAL", "RESTRICTED", "CRITICAL"]
    threat_score: float
    start_time: str
    end_time: Optional[str] = None
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    status: Literal["ACTIVE", "ACKNOWLEDGED", "RESOLVED", "HISTORICAL"] = "ACTIVE"
    summary: str = ""
    evidence_hashes: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    version: int = 1


class EvidenceSyncPacket(BaseModel):
    evidence_id: str
    incident_id: str
    camera_id: str
    sha256_hash: str
    file_size_bytes: int
    media_type: str = "image/jpeg"
    is_permanent: bool = True
    relative_path: str
    download_url: Optional[str] = None
    timestamp: str


class CameraConfigPacket(BaseModel):
    camera_id: str
    name: str
    source_type: str = "video_file"
    source_path: Optional[str] = None
    source_url: Optional[str] = None
    modality: Literal["RGB", "IR", "THERMAL", "STANDARD"] = "RGB"
    is_running: bool = False
    fps: float = 25.0
    location_label: Optional[str] = None


class UserProfileSchema(BaseModel):
    user_id: str
    email: str
    name: str
    rank: str = "Operator"
    gender: Optional[str] = None
    contact_number: Optional[str] = None
    regiment: str = "Northern Command"
    division: str = "Border Surveillance Unit"
    organization: str = "Border Intelligence Security Force"
    role: str = "SURVEILLANCE_OFFICER"
