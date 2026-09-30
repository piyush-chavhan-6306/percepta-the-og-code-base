"""
PERCEPTA PathGuard — Route Integrity & Corridor Deviation Engine.

Provides route integrity monitoring for designated authorized transit paths
(patrol routes, authorized convoy corridors, perimeter transit lanes).
Detects unauthorized route departures, unexpected lateral deviations,
and out-of-corridor excursions with evidence capture and alert propagation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from backend.events.schema import AlertEvent, EventType, SourceType, normalize_severity
from backend.events.store import get_event_store
from backend.incidents.engine import get_incident_engine

if TYPE_CHECKING:
    from backend.tracking.tracker import TrackedObject

logger = logging.getLogger(__name__)


@dataclass
class TransitCorridor:
    """An authorized corridor or expected route for tracked objects."""
    corridor_id: str
    name: str
    camera_id: str
    waypoints: List[Tuple[float, float]]     # Ordered (x, y) centerline vertices
    allowed_width_px: float = 65.0           # Maximum lateral distance allowed from centerline
    allowed_classes: Set[str] = field(default_factory=lambda: {"person", "car", "truck"})
    is_active: bool = True
    min_deviation_seconds: float = 1.5       # Debounce to prevent noisy single-frame deviations


def _point_to_segment_distance(
    pt: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
) -> float:
    """Calculates perpendicular Euclidean distance from point pt to line segment [p1, p2]."""
    px, py = pt
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    # Projection factor t
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


class PathGuardMonitor:
    """
    Evaluates tracking trajectories against defined transit corridors.
    Flags unauthorized path deviations and route integrity breaches.
    """

    def __init__(self, config_path: str = "storage/pathguard_config.json") -> None:
        self.config_path = config_path
        self.corridors: Dict[str, TransitCorridor] = {}
        # Track state: (corridor_id, track_id) -> timestamp first deviated
        self._deviation_start_times: Dict[Tuple[str, str], float] = {}
        self._last_alert_times: Dict[Tuple[str, str], float] = {}
        self._load_config()

    def _load_config(self) -> None:
        p = Path(self.config_path)
        if not p.is_file():
            # Seed default corridor for primary sector
            default_corridor = TransitCorridor(
                corridor_id="CORRIDOR-PATROL-01",
                name="Main Access Road & Patrol Route",
                camera_id="CAM-01",
                waypoints=[(100.0, 500.0), (350.0, 480.0), (650.0, 470.0), (950.0, 490.0)],
                allowed_width_px=75.0,
                allowed_classes={"person", "car", "truck"},
                is_active=True,
            )
            self.corridors[default_corridor.corridor_id] = default_corridor
            self._save_config()
            return

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            for c_data in data.get("corridors", []):
                corr = TransitCorridor(
                    corridor_id=c_data["corridor_id"],
                    name=c_data["name"],
                    camera_id=c_data["camera_id"],
                    waypoints=[tuple(pt) for pt in c_data["waypoints"]],
                    allowed_width_px=float(c_data.get("allowed_width_px", 65.0)),
                    allowed_classes=set(c_data.get("allowed_classes", ["person", "car", "truck"])),
                    is_active=bool(c_data.get("is_active", True)),
                    min_deviation_seconds=float(c_data.get("min_deviation_seconds", 1.5)),
                )
                self.corridors[corr.corridor_id] = corr
        except Exception as err:
            logger.warning(f"Could not load PathGuard corridors: {err}")

    def _save_config(self) -> None:
        p = Path(self.config_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "corridors": [
                    {
                        "corridor_id": c.corridor_id,
                        "name": c.name,
                        "camera_id": c.camera_id,
                        "waypoints": [list(pt) for pt in c.waypoints],
                        "allowed_width_px": c.allowed_width_px,
                        "allowed_classes": list(c.allowed_classes),
                        "is_active": c.is_active,
                        "min_deviation_seconds": c.min_deviation_seconds,
                    }
                    for c in self.corridors.values()
                ]
            }
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as err:
            logger.warning(f"Could not save PathGuard corridors: {err}")

    def add_corridor(self, corridor: TransitCorridor) -> None:
        self.corridors[corridor.corridor_id] = corridor
        self._save_config()

    def remove_corridor(self, corridor_id: str) -> bool:
        if corridor_id in self.corridors:
            del self.corridors[corridor_id]
            self._save_config()
            return True
        return False

    def list_corridors(self, camera_id: Optional[str] = None) -> List[TransitCorridor]:
        res = list(self.corridors.values())
        if camera_id:
            res = [c for c in res if c.camera_id == camera_id]
        return res

    def evaluate_object(
        self,
        camera_id: str,
        tracked_obj: TrackedObject,
        current_time_sec: float,
    ) -> List[AlertEvent]:
        """
        Calculates distance from tracked_obj centroid to all active corridors for this camera.
        If object has entered the corridor vicinity but deviates beyond allowed width,
        generates a PATHGUARD_ROUTE_DEVIATION alert event.
        """
        alerts: List[AlertEvent] = []
        if not tracked_obj.history:
            return alerts

        cx, cy = tracked_obj.centroid
        cls_name = tracked_obj.class_name.lower()

        for corridor in self.corridors.values():
            if not corridor.is_active or corridor.camera_id != camera_id:
                continue
            if corridor.allowed_classes and cls_name not in corridor.allowed_classes:
                continue
            if len(corridor.waypoints) < 2:
                continue

            # Find minimum distance to any segment of corridor centerline
            min_dist = float("inf")
            for i in range(len(corridor.waypoints) - 1):
                p1 = corridor.waypoints[i]
                p2 = corridor.waypoints[i + 1]
                dist = _point_to_segment_distance((cx, cy), p1, p2)
                if dist < min_dist:
                    min_dist = dist

            key = (corridor.corridor_id, str(tracked_obj.track_id))

            # Only monitor deviation if the object is reasonably near the corridor corridor
            # (within 3x allowed width), so random background objects don't trigger alerts
            is_in_corridor_sector = min_dist < (corridor.allowed_width_px * 3.5)

            if is_in_corridor_sector and min_dist > corridor.allowed_width_px:
                # Target is deviating from the corridor
                if key not in self._deviation_start_times:
                    self._deviation_start_times[key] = current_time_sec

                elapsed_deviation = current_time_sec - self._deviation_start_times[key]
                last_alert = self._last_alert_times.get(key, 0.0)

                # Fire alert if deviated for longer than debounce and cooldown elapsed (15s)
                if elapsed_deviation >= corridor.min_deviation_seconds and (current_time_sec - last_alert >= 15.0):
                    self._last_alert_times[key] = current_time_sec
                    sev = "CRITICAL" if min_dist > (corridor.allowed_width_px * 2.0) else "RESTRICTED"

                    alert = AlertEvent(
                        camera_id=camera_id,
                        track_id=str(tracked_obj.track_id),
                        source=SourceType.VIDEO_FILE,
                        event_type=EventType.ALERT,
                        timestamp=datetime.now(timezone.utc),
                        severity=sev,
                        message=f"PATHGUARD ROUTE INTEGRITY VIOLATION: Track #{tracked_obj.track_id} ({cls_name}) deviated {min_dist:.0f}px from authorized corridor '{corridor.name}'.",
                        payload={
                            "rule_type": "pathguard_route_deviation",
                            "corridor_id": corridor.corridor_id,
                            "corridor_name": corridor.name,
                            "deviation_px": round(min_dist, 1),
                            "allowed_width_px": corridor.allowed_width_px,
                            "threat_score": 75.0 if sev == "CRITICAL" else 45.0,
                            "threat_level": sev,
                            "threat_reasons": [
                                f"Deviation from authorized patrol route '{corridor.name}' by {min_dist:.0f}px (threshold: {corridor.allowed_width_px:.0f}px)",
                                "Uncontrolled tactical route departure",
                            ],
                            "causal_chain": [
                                f"Object #{tracked_obj.track_id} entered designated transit sector",
                                f"Lateral trajectory diverged {min_dist:.0f}px from corridor centerline",
                                "PathGuard automated route deviation violation confirmed",
                            ],
                        },
                    )
                    alerts.append(alert)
            else:
                # Cleared back inside corridor or left vicinity
                self._deviation_start_times.pop(key, None)

        return alerts


# Singleton
_pathguard_instance: Optional[PathGuardMonitor] = None


def get_pathguard_monitor() -> PathGuardMonitor:
    global _pathguard_instance
    if _pathguard_instance is None:
        _pathguard_instance = PathGuardMonitor()
    return _pathguard_instance
