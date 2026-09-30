"""
Border Intelligence Base Tracker Module.
Defines abstract contracts and data models for multi-object tracking.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np

from backend.detection.detector import DetectionResult
from backend.ingestion.adapter import FrameData


@dataclass
class TrackedObject:
    """
    Standardized tracked object representation across all frames.
    Exposes persistent track IDs, spatial coordinates, velocity, and trajectory.
    """
    track_id: str
    object_class: str
    confidence: float
    bounding_box: List[float]  # [x1, y1, x2, y2]
    normalized_box: List[float]  # [nx1, ny1, nx2, ny2] in range [0.0, 1.0]
    frame_number: int
    timestamp: datetime
    center_x: float
    center_y: float
    prev_center_x: float = 0.0
    prev_center_y: float = 0.0
    velocity: tuple[float, float] = (0.0, 0.0)  # (dx, dy) in pixels/frame
    speed_px_per_frame: float = 0.0
    direction_deg: float = 0.0  # [0, 360) where 0 = East, 90 = South (image coords)
    cardinal_heading: str = "STATIONARY"  # "N", "NE", "E", "SE", "S", "SW", "W", "NW", "STATIONARY"
    speed_description: str = "Stationary"  # e.g., "Moving (Estimated)", "Stationary"
    lifecycle: str = "updated"  # "created", "updated", "lost", "recovered", "terminated"
    trajectory: List[tuple[float, float]] = field(default_factory=list)  # Recent [(cx, cy), ...]
    current_zone: Optional[str] = None
    previous_zone: Optional[str] = None
    zone_entry_time: Optional[datetime] = None
    zone_dwell_seconds: float = 0.0
    movement_state: str = "STATIONARY"  # "STATIONARY", "MOVING", "APPROACHING_RESTRICTED", "LOITERING"
    heading_towards_protected: bool = False
    is_night_movement: bool = False
    threat_score: float = 0.0
    hits: int = 1
    age: int = 1
    time_since_update: int = 0
    provenance: str = "detection"  # "detection" or "prediction"
    global_id: Optional[str] = None  # Persistent Cross-Camera Identity
    global_confidence: Optional[float] = None  # Re-identification confidence [0.0 - 1.0]

    @property
    def center(self) -> tuple[float, float]:
        return (self.center_x, self.center_y)

    @property
    def previous_center(self) -> tuple[float, float]:
        return (self.prev_center_x, self.prev_center_y)


class BaseTracker(ABC):
    """Abstract interface for all multi-object trackers."""

    @abstractmethod
    def initialize(self) -> None:
        """Initialize tracker models and data structures."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset internal state, track registers, and trajectories."""
        pass

    @abstractmethod
    def update(
        self,
        detections: Optional[List[DetectionResult]],
        frame: FrameData,
    ) -> List[TrackedObject]:
        pass

    @abstractmethod
    def get_active_tracks(self) -> List[TrackedObject]:
        """Return the current active tracked objects."""
        pass

    def predict_step(self, frame: FrameData) -> List[TrackedObject]:
        """
        Advance tracker motion state on intermediate frames without fresh detections.
        Returns predicted tracks tagged with provenance='prediction'.
        """
        return []
