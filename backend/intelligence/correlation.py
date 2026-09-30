"""
Border Intelligence Multi-Camera Spatial-Temporal Event Correlation Prototype.
Correlates chronological handoffs between adjacent cameras without claiming biometric facial re-identification.
Explicitly labeled as 'Probable cross-camera event correlation'.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.events.schema import CorrelationEvent

logger = logging.getLogger(__name__)


@dataclass
class CameraTopologyLink:
    """Configured spatial relationship between adjacent cameras."""
    source_cam: str
    target_cam: str
    source_zone: Optional[str] = None
    target_zone: Optional[str] = None
    expected_transit_seconds: float = 10.0
    max_transit_window_seconds: float = 40.0


@dataclass
class TrackExitRecord:
    """Historical exit record stored for correlation."""
    camera_id: str
    zone_name: str
    track_id: str
    object_class: str
    exit_time: datetime
    velocity: Optional[List[float]] = None


class MultiCameraCorrelator:
    """
    Lightweight Spatial-Temporal Multi-Camera Correlator.
    Matches zone exit events on Camera A with subsequent entry events on Camera B.
    """

    def __init__(self, max_history_seconds: float = 60.0) -> None:
        self.max_history_seconds = max_history_seconds
        self._exit_history: List[TrackExitRecord] = []
        # Pre-configured default topology for defense perimeter demo
        self.topology: List[CameraTopologyLink] = [
            CameraTopologyLink(
                source_cam="CAM-01",
                target_cam="CAM-02",
                source_zone="Border Perimeter Buffer Strip",
                target_zone="Gate Approach Corridor",
                expected_transit_seconds=8.0,
                max_transit_window_seconds=30.0,
            ),
            CameraTopologyLink(
                source_cam="CAM-02",
                target_cam="CAM-03",
                source_zone="Gate Approach Corridor",
                target_zone="High-Security Asset Exclusion Box",
                expected_transit_seconds=12.0,
                max_transit_window_seconds=45.0,
            ),
        ]

    def add_topology_link(self, link: CameraTopologyLink) -> None:
        self.topology.append(link)

    def record_exit(
        self,
        camera_id: str,
        zone_name: str,
        track_id: str,
        object_class: str,
        exit_time: Optional[datetime] = None,
    ) -> None:
        """Record when an entity departs a camera sector or restricted zone."""
        now = exit_time or datetime.now(timezone.utc)
        self._exit_history.append(
            TrackExitRecord(
                camera_id=camera_id,
                zone_name=zone_name,
                track_id=track_id,
                object_class=object_class,
                exit_time=now,
            )
        )
        self._prune_stale(now)

    def check_correlation_on_entry(
        self,
        camera_id: str,
        zone_name: str,
        track_id: str,
        object_class: str,
        entry_time: Optional[datetime] = None,
    ) -> Optional[CorrelationEvent]:
        """
        Check if an entry on this camera matches an exit from an adjacent camera within window.
        """
        now = entry_time or datetime.now(timezone.utc)
        self._prune_stale(now)

        for rec in reversed(self._exit_history):
            if rec.camera_id == camera_id:
                continue  # Same camera is intra-camera, not cross-camera
            if rec.object_class != object_class:
                continue

            delta_sec = (now - rec.exit_time).total_seconds()
            if delta_sec < 0.5 or delta_sec > self.max_history_seconds:
                continue

            # Check if this matches a known topological link
            matched_link = None
            for link in self.topology:
                if link.source_cam == rec.camera_id and link.target_cam == camera_id:
                    matched_link = link
                    break

            # Calculate correlation confidence based on temporal proximity
            if matched_link:
                time_diff = abs(delta_sec - matched_link.expected_transit_seconds)
                conf = max(0.55, min(0.92, 1.0 - (time_diff / matched_link.max_transit_window_seconds)))
            else:
                conf = max(0.40, min(0.75, 1.0 - (delta_sec / self.max_history_seconds)))

            narrative = (
                f"Probable cross-camera event correlation: {object_class.title()} exited "
                f"'{rec.camera_id}' ({rec.zone_name}) and entered '{camera_id}' ({zone_name}) "
                f"{delta_sec:.1f}s later (Temporal Match: {int(conf*100)}%)."
            )

            return CorrelationEvent(
                camera_id=camera_id,
                track_id=track_id,
                source_camera=rec.camera_id,
                target_camera=camera_id,
                source_zone=rec.zone_name,
                target_zone=zone_name,
                time_delta_seconds=round(delta_sec, 2),
                correlation_confidence=round(conf, 3),
                correlation_label="Probable cross-camera event correlation",
                narrative=narrative,
                timestamp=now,
            )

        return None

    def _prune_stale(self, reference_time: Optional[datetime] = None) -> None:
        now = reference_time or datetime.now(timezone.utc)
        cutoff = self.max_history_seconds
        self._exit_history = [
            r for r in self._exit_history if 0 <= (now - r.exit_time).total_seconds() <= cutoff
        ]


global_correlator = MultiCameraCorrelator()


def get_correlator() -> MultiCameraCorrelator:
    return global_correlator
