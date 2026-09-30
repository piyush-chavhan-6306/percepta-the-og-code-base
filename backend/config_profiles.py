"""
Border Intelligence Surveillance Operation Sensitivity Profiles Module.
Provides dynamic environmental profiles (Day, Night, Storm, Convoy) without restarting the server.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.config import get_settings


class OperationalProfile(BaseModel):
    profile_id: str
    name: str
    description: str
    confidence_threshold: float
    iou_threshold: float
    frame_stride: int
    loitering_threshold_seconds: float
    optical_mode: str  # "DAY_COLOR" | "NIGHT_ENHANCED" | "STORM_FILTERED"


SURVEILLANCE_PROFILES: Dict[str, OperationalProfile] = {
    "STANDARD_DAY": OperationalProfile(
        profile_id="STANDARD_DAY",
        name="Standard Day Baseline",
        description="Optimized for clear daytime optical surveillance with standard stride.",
        confidence_threshold=0.25,
        iou_threshold=0.45,
        frame_stride=2,
        loitering_threshold_seconds=2.0,
        optical_mode="DAY_COLOR",
    ),
    "HIGH_SENSITIVITY_NIGHT": OperationalProfile(
        profile_id="HIGH_SENSITIVITY_NIGHT",
        name="High-Sensitivity Night Mode",
        description="Lower detection threshold and single-stride processing for low-light perimeter security.",
        confidence_threshold=0.15,
        iou_threshold=0.35,
        frame_stride=1,
        loitering_threshold_seconds=1.0,
        optical_mode="NIGHT_ENHANCED",
    ),
    "ADVERSE_WEATHER_STORM": OperationalProfile(
        profile_id="ADVERSE_WEATHER_STORM",
        name="Adverse Weather & Storm Filter",
        description="Heightened confidence threshold to suppress rain, snow, and dust storm false triggers.",
        confidence_threshold=0.32,
        iou_threshold=0.50,
        frame_stride=2,
        loitering_threshold_seconds=3.0,
        optical_mode="STORM_FILTERED",
    ),
    "HIGH_TRAFFIC_CONVOY": OperationalProfile(
        profile_id="HIGH_TRAFFIC_CONVOY",
        name="High-Density Convoy & Checkpoint",
        description="Optimized multi-object tracker parameters for high-volume vehicle corridors.",
        confidence_threshold=0.25,
        iou_threshold=0.50,
        frame_stride=3,
        loitering_threshold_seconds=4.0,
        optical_mode="DAY_COLOR",
    ),
}

_CURRENT_ACTIVE_PROFILE_ID: str = "STANDARD_DAY"


def list_operational_profiles() -> List[OperationalProfile]:
    """List all available environmental surveillance profiles."""
    return list(SURVEILLANCE_PROFILES.values())


def get_active_profile() -> OperationalProfile:
    """Retrieve the currently active surveillance sensitivity profile."""
    return SURVEILLANCE_PROFILES.get(_CURRENT_ACTIVE_PROFILE_ID, SURVEILLANCE_PROFILES["STANDARD_DAY"])


def set_active_profile(profile_id: str) -> OperationalProfile:
    """Activate a surveillance sensitivity profile dynamically at runtime."""
    global _CURRENT_ACTIVE_PROFILE_ID
    if profile_id not in SURVEILLANCE_PROFILES:
        raise ValueError(f"Operational profile '{profile_id}' is invalid")

    _CURRENT_ACTIVE_PROFILE_ID = profile_id
    prof = SURVEILLANCE_PROFILES[profile_id]

    # Dynamically update settings runtime defaults
    settings = get_settings()
    settings.CONFIDENCE_THRESHOLD = prof.confidence_threshold
    settings.IOU_THRESHOLD = prof.iou_threshold
    settings.DEFAULT_FRAME_STRIDE = prof.frame_stride

    return prof
