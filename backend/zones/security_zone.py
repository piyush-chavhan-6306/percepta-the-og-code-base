from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from backend.events.schema import AlertEvent, EventType, SourceType, ZoneEvent, normalize_severity
from backend.events.store import EventStore, get_event_store
from backend.incidents.engine import IncidentEngine, get_incident_engine

if TYPE_CHECKING:
    from backend.tracking.tracker import TrackedObject

logger = logging.getLogger(__name__)


class ZoneSeverity(str, Enum):
    NORMAL = "normal"
    RESTRICTED = "restricted"
    CRITICAL = "critical"

    # Backward compatibility aliases
    INFO = "normal"
    WARNING = "restricted"

    @classmethod
    def from_str(cls, val: Any) -> "ZoneSeverity":
        if isinstance(val, cls):
            return val
        s = str(val or "").strip().lower()
        if s in ("critical", "high"):
            return cls.CRITICAL
        elif s in ("restricted", "warning", "medium"):
            return cls.RESTRICTED
        else:
            return cls.NORMAL


def _diff_seconds(t1: Any, t2: Any) -> float:
    """Safely calculate time difference in seconds between two timestamps (datetime, float, or int)."""
    if t1 is None or t2 is None:
        return 0.0
    if isinstance(t1, (int, float)) and isinstance(t2, (int, float)):
        return float(t1 - t2)
    if hasattr(t1, "timestamp") and isinstance(t2, (int, float)):
        return float(t1.timestamp() - t2)
    if isinstance(t1, (int, float)) and hasattr(t2, "timestamp"):
        return float(t1 - t2.timestamp())
    if hasattr(t1, "timestamp") and hasattr(t2, "timestamp"):
        return float(t1.timestamp() - t2.timestamp())
    try:
        diff = t1 - t2
        if hasattr(diff, "total_seconds"):
            return float(diff.total_seconds())
        return float(diff)
    except Exception:
        return 0.0


@dataclass
class SecurityZone:
    """
    Polygon or rectangular restricted zone.
    Coordinates are defined as a list of (x, y) vertices forming a closed polygon.
    """
    zone_id: str
    name: str
    polygon: List[Tuple[float, float]]  # [(x0, y0), (x1, y1), ...]
    severity: ZoneSeverity = ZoneSeverity.RESTRICTED
    is_active: bool = True
    target_classes: Optional[Set[str]] = None  # None means all classes
    loitering_threshold_seconds: Optional[float] = None  # None = no loitering check
    loitering_debounce_seconds: float = 30.0  # Cooldown between repeat loitering alerts
    camera_id: Optional[str] = None  # If set, this zone applies only to the specific camera

    def contains_point(self, point: Tuple[float, float]) -> bool:
        """
        Ray-casting algorithm to test if a 2D point (x, y) is inside the polygon.
        Supports both pixel space and normalized [0.0, 1.0] coordinate spaces seamlessly.
        """
        if not self.polygon or len(self.polygon) < 3:
            return False

        poly = self.polygon
        x, y = point

        # Auto-detect coordinate space: normalized [0..1] vs pixel space [0..1280]
        is_poly_norm = all(0.0 <= pt[0] <= 1.0 and 0.0 <= pt[1] <= 1.0 for pt in poly)
        is_pt_norm = (x <= 1.0 and y <= 1.0)

        if is_poly_norm and not is_pt_norm:
            poly = [(pt[0] * 1280.0, pt[1] * 720.0) for pt in poly]
        elif not is_poly_norm and is_pt_norm:
            x, y = (x * 1280.0, y * 720.0)

        n = len(poly)
        inside = False

        p1x, p1y = poly[0]
        for i in range(1, n + 1):
            p2x, p2y = poly[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        else:
                            xinters = p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside


@dataclass
class VirtualBoundary:
    """
    Virtual fence or border tripwire defined by a directed 2D line segment (pt1 -> pt2).
    Tracks traversing from one side of the line to another generate crossing events.
    """
    boundary_id: str
    name: str
    pt1: Tuple[float, float]  # (x1, y1)
    pt2: Tuple[float, float]  # (x2, y2)
    severity: ZoneSeverity = ZoneSeverity.CRITICAL
    direction: str = "BIDIRECTIONAL"  # "NORTH", "SOUTH", "EAST", "WEST", "BIDIRECTIONAL"
    debounce_seconds: float = 3.0
    is_active: bool = True
    target_classes: Optional[Set[str]] = None
    camera_id: Optional[str] = None  # If set, this boundary applies only to the specific camera

    def check_crossing(
        self,
        prev_point: Tuple[float, float],
        curr_point: Tuple[float, float],
    ) -> Optional[str]:
        """
        Check if the movement segment (prev_point -> curr_point) crosses this boundary.
        Returns crossing direction ('inbound', 'outbound', 'crossed', 'NORTH', 'SOUTH', etc.) or None.
        Supports both pixel and normalized coordinates.
        """
        if prev_point is None or curr_point is None:
            return None

        q0 = self.pt1
        q1 = self.pt2
        p0 = prev_point
        p1 = curr_point

        is_boundary_norm = (0.0 <= q0[0] <= 1.0 and 0.0 <= q0[1] <= 1.0 and 0.0 <= q1[0] <= 1.0 and 0.0 <= q1[1] <= 1.0)
        is_pts_norm = (curr_point[0] <= 1.0 and curr_point[1] <= 1.0)

        if is_boundary_norm and not is_pts_norm:
            q0 = (q0[0] * 1280.0, q0[1] * 720.0)
            q1 = (q1[0] * 1280.0, q1[1] * 720.0)
        elif not is_boundary_norm and is_pts_norm:
            p0 = (p0[0] * 1280.0, p0[1] * 720.0)
            p1 = (p1[0] * 1280.0, p1[1] * 720.0)

        p0_x, p0_y = p0
        p1_x, p1_y = p1
        q0_x, q0_y = q0
        q1_x, q1_y = q1

        # Check line segment intersection between (P0 -> P1) and (Q0 -> Q1)
        def _ccw(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
            return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])

        # Check orientations
        d1 = _ccw(q0, q1, p0)
        d2 = _ccw(q0, q1, p1)
        d3 = _ccw(p0, p1, q0)
        d4 = _ccw(p0, p1, q1)

        # Proper intersection
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            req_dir = (self.direction or "BIDIRECTIONAL").upper().strip()
            dx = p1_x - p0_x
            dy = p1_y - p0_y

            # In image space, dy < 0 is NORTH (upward), dy > 0 is SOUTH (downward),
            # dx > 0 is EAST (rightward), dx < 0 is WEST (leftward).
            if req_dir == "NORTH" and dy >= 0:
                return None
            elif req_dir == "SOUTH" and dy <= 0:
                return None
            elif req_dir == "EAST" and dx <= 0:
                return None
            elif req_dir == "WEST" and dx >= 0:
                return None

            if req_dir in ("NORTH", "SOUTH", "EAST", "WEST"):
                return req_dir

            # Default / BIDIRECTIONAL: determine direction relative to line segment orientation
            if d1 > 0 and d2 < 0:
                return "inbound"
            else:
                return "outbound"

        return None


@dataclass
class ZoneTransition:
    """Represents a state change for a tracked object in relation to a zone/boundary."""
    track_id: str
    zone_id: str
    zone_name: str
    severity: str
    transition_type: str  # "entered", "exited", "crossed", "dwelling", "loitering"
    frame_number: int
    timestamp: datetime
    camera_id: str
    position: Tuple[float, float]
    object_class: str
    dwell_duration_seconds: Optional[float] = None


class ZoneMonitor:
    """
    Monitors tracked objects across configured security zones and virtual boundaries.
    Maintains track-zone occupancy states, dwell durations, and enforces the rules:
    - Normal presence alone is NOT an intrusion alert spam.
    - Security alerts fire on state transitions (entry, boundary crossing).
    - Loitering alerts fire ONLY when dwell duration exceeds configured threshold (debounced).
    """

    def __init__(
        self,
        zones: Optional[List[SecurityZone]] = None,
        boundaries: Optional[List[VirtualBoundary]] = None,
        event_store: Optional[EventStore] = None,
        incident_engine: Optional[IncidentEngine] = None,
        load_persistence: bool = True,
    ) -> None:
        self.zones: Dict[str, SecurityZone] = {z.zone_id: z for z in (zones or [])}
        self.boundaries: Dict[str, VirtualBoundary] = {b.boundary_id: b for b in (boundaries or [])}
        self.event_store = event_store or get_event_store()
        self.incident_engine = incident_engine or get_incident_engine()

        # Track state tracking: {track_id: {zone_id: is_inside}}
        self._track_zone_state: Dict[str, Dict[str, bool]] = {}
        # Track entry timestamps: {track_id: {zone_id: entry_datetime}}
        self._track_zone_entry_time: Dict[str, Dict[str, datetime]] = {}
        # Track last loitering alert timestamps: {track_id: {zone_id: last_alert_datetime}}
        self._track_zone_loiter_alert_time: Dict[str, Dict[str, datetime]] = {}
        # Track previous positions for boundary crossings: {track_id: (x, y)}
        self._track_prev_positions: Dict[str, Tuple[float, float]] = {}
        # Track last boundary crossing alert timestamps: {track_id: {boundary_id: last_alert_datetime}}
        self._track_boundary_alert_time: Dict[str, Dict[str, datetime]] = {}
        # Zone-entry cooldown: {(track_id, zone_id): last_alert_datetime}
        # Prevents repeated entry alerts when ByteTrack briefly drops a track.
        # The incident engine handles deeper continuity; this is a fast gate.
        self._zone_entry_last_alert: Dict[Tuple[str, str], datetime] = {}
        self._zone_entry_cooldown_secs: float = 120.0  # configurable per monitor

        if load_persistence and not zones and not boundaries:
            self.load_persistent_definitions()

    @classmethod
    def with_shared_definitions(cls, source: "ZoneMonitor") -> "ZoneMonitor":
        """
        Build a monitor that shares `source`'s zone/boundary definitions by
        reference but keeps its own per-track state.
        """
        monitor = cls(event_store=source.event_store, load_persistence=False)
        monitor.zones = source.zones
        monitor.boundaries = source.boundaries
        return monitor

    def load_persistent_definitions(self, filepath: Optional[str] = None) -> None:
        """Load persistent zones and boundaries from JSON storage."""
        import json
        from pathlib import Path
        fp = filepath or getattr(self, "persistence_filepath", "storage/zones_config.json")
        self.persistence_filepath = fp
        p = Path(fp)
        if not p.exists():
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            for zd in data.get("zones", []):
                z = SecurityZone(
                    zone_id=zd["zone_id"],
                    name=zd["name"],
                    polygon=[tuple(pt) for pt in zd["polygon"]],
                    severity=ZoneSeverity.from_str(zd.get("severity", "restricted")),
                    is_active=zd.get("is_active", True),
                    loitering_threshold_seconds=zd.get("loitering_threshold_seconds"),
                    loitering_debounce_seconds=zd.get("loitering_debounce_seconds", 30.0),
                    camera_id=zd.get("camera_id"),
                )
                self.zones[z.zone_id] = z
            for bd in data.get("boundaries", []):
                b = VirtualBoundary(
                    boundary_id=bd["boundary_id"],
                    name=bd["name"],
                    pt1=tuple(bd["pt1"]),
                    pt2=tuple(bd["pt2"]),
                    severity=ZoneSeverity.from_str(bd.get("severity", "critical")),
                    direction=bd.get("direction", "BIDIRECTIONAL"),
                    debounce_seconds=bd.get("debounce_seconds", 3.0),
                    is_active=bd.get("is_active", True),
                    camera_id=bd.get("camera_id"),
                )
                self.boundaries[b.boundary_id] = b
            logger.info(f"Loaded {len(self.zones)} zones and {len(self.boundaries)} boundaries from {fp}")
        except Exception as err:
            logger.warning(f"Failed to load zones from {fp}: {err}")

    def save_persistent_definitions(self, filepath: Optional[str] = None) -> None:
        """Save active zones and boundaries to JSON storage."""
        import json
        from pathlib import Path
        fp = filepath or getattr(self, "persistence_filepath", "storage/zones_config.json")
        self.persistence_filepath = fp
        p = Path(fp)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "zones": [
                    {
                        "zone_id": z.zone_id,
                        "name": z.name,
                        "polygon": [list(pt) for pt in z.polygon],
                        "severity": z.severity.value,
                        "is_active": z.is_active,
                        "loitering_threshold_seconds": z.loitering_threshold_seconds,
                        "loitering_debounce_seconds": z.loitering_debounce_seconds,
                        "camera_id": z.camera_id,
                    }
                    for z in self.zones.values()
                ],
                "boundaries": [
                    {
                        "boundary_id": b.boundary_id,
                        "name": b.name,
                        "pt1": list(b.pt1),
                        "pt2": list(b.pt2),
                        "severity": b.severity.value,
                        "direction": getattr(b, "direction", "BIDIRECTIONAL"),
                        "debounce_seconds": b.debounce_seconds,
                        "is_active": b.is_active,
                        "camera_id": b.camera_id,
                    }
                    for b in self.boundaries.values()
                ],
            }
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.zones)} zones and {len(self.boundaries)} boundaries to {filepath}")
        except Exception as err:
            logger.warning(f"Failed to save zones to {filepath}: {err}")

    def add_zone(self, zone: SecurityZone) -> None:
        self.zones[zone.zone_id] = zone
        self.save_persistent_definitions()

    def remove_zone(self, zone_id: str) -> bool:
        if zone_id in self.zones:
            del self.zones[zone_id]
            for t_id in list(self._track_zone_state.keys()):
                self._track_zone_state[t_id].pop(zone_id, None)
                self._track_zone_entry_time[t_id].pop(zone_id, None)
                self._track_zone_loiter_alert_time[t_id].pop(zone_id, None)
            self.save_persistent_definitions()
            return True
        return False

    def add_boundary(self, boundary: VirtualBoundary) -> None:
        self.boundaries[boundary.boundary_id] = boundary
        self.save_persistent_definitions()

    def remove_boundary(self, boundary_id: str) -> bool:
        if boundary_id in self.boundaries:
            del self.boundaries[boundary_id]
            for t_id in list(self._track_boundary_alert_time.keys()):
                self._track_boundary_alert_time[t_id].pop(boundary_id, None)
            self.save_persistent_definitions()
            return True
        return False

    def reset(self) -> None:
        """Reset internal occupancy states and dwell clocks."""
        self._track_zone_state.clear()
        self._track_zone_entry_time.clear()
        self._track_zone_loiter_alert_time.clear()
        self._track_prev_positions.clear()
        self._track_boundary_alert_time.clear()
        self._zone_entry_last_alert.clear()

    def clear_tracks(self) -> None:
        """Clear all per-track state. Used when a camera is removed/replaced."""
        self.reset()

    def evaluate_tracks(
        self,
        tracks: List[TrackedObject],
        camera_id: str,
        source: SourceType = SourceType.VIDEO_FILE,
    ) -> Tuple[List[ZoneEvent], List[AlertEvent]]:
        """
        Evaluate current frame tracks against all zones and boundaries.
        Generates structured narrative events, causal chains, and deterministic threat scores.
        """
        from backend.intelligence.threat_engine import compute_threat_score
        from backend.tracking.movement import is_moving_towards

        zone_events: List[ZoneEvent] = []
        alert_events: List[AlertEvent] = []

        active_track_ids = {t.track_id for t in tracks}
        now_dt = datetime.now(timezone.utc)
        is_night = (now_dt.hour >= 22 or now_dt.hour < 5)

        # Precompute centroids of critical/restricted zones for approach detection
        protected_centroids: List[Tuple[float, float]] = []
        for zone in self.zones.values():
            if zone.camera_id is not None and zone.camera_id != camera_id:
                continue
            if zone.is_active and zone.severity in (ZoneSeverity.RESTRICTED, ZoneSeverity.CRITICAL):
                if zone.polygon and len(zone.polygon) >= 3:
                    cx = sum(p[0] for p in zone.polygon) / len(zone.polygon)
                    cy = sum(p[1] for p in zone.polygon) / len(zone.polygon)
                    protected_centroids.append((cx, cy))

        for track in tracks:
            t_id = track.track_id
            curr_pos = (track.center_x, track.center_y)
            prev_pos = self._track_prev_positions.get(t_id)

            if t_id not in self._track_zone_state:
                self._track_zone_state[t_id] = {}
            if t_id not in self._track_zone_entry_time:
                self._track_zone_entry_time[t_id] = {}
            if t_id not in self._track_zone_loiter_alert_time:
                self._track_zone_loiter_alert_time[t_id] = {}

            heading = getattr(track, "cardinal_heading", "STATIONARY")
            dir_deg = getattr(track, "direction_deg", 0.0)
            heading_protected = False

            if heading != "STATIONARY" and protected_centroids:
                for pc in protected_centroids:
                    if is_moving_towards(curr_pos, dir_deg, pc, tolerance_deg=50.0):
                        heading_protected = True
                        break

            track.heading_towards_protected = heading_protected
            track.is_night_movement = is_night

            # 1. Evaluate Polygon Zones & Loitering
            for z_id, zone in self.zones.items():
                if not zone.is_active:
                    continue
                if zone.camera_id is not None and zone.camera_id != camera_id:
                    continue
                if zone.target_classes and track.object_class not in zone.target_classes:
                    continue

                is_inside = zone.contains_point(curr_pos) or (
                    hasattr(track, "bounding_box") and track.bounding_box and len(track.bounding_box) >= 4 and zone.contains_point((track.center_x, float(track.bounding_box[3])))
                )
                was_inside = self._track_zone_state[t_id].get(z_id, False)

                if is_inside and not was_inside:
                    # STATE TRANSITION: ENTERED
                    self._track_zone_state[t_id][z_id] = True
                    self._track_zone_entry_time[t_id][z_id] = track.timestamp
                    track.previous_zone = track.current_zone
                    track.current_zone = zone.name
                    track.zone_entry_time = track.timestamp
                    track.zone_dwell_seconds = 0.0

                    narrative = f"{track.object_class.upper()} #{t_id} entered {zone.name} moving {heading}."
                    is_restricted = zone.severity in (ZoneSeverity.RESTRICTED, ZoneSeverity.CRITICAL)

                    t_score, t_level, t_reasons = compute_threat_score(
                        has_restricted_intrusion=is_restricted,
                        has_tripwire_breach=False,
                        has_loitering=False,
                        has_night_movement=is_night,
                        has_multiple_unauthorized=len(active_track_ids) > 1 and is_restricted,
                        has_movement_towards_protected=heading_protected,
                    )
                    track.threat_score = t_score

                    ze = ZoneEvent(
                        camera_id=camera_id,
                        track_id=t_id,
                        confidence=track.confidence,
                        source=source,
                        timestamp=track.timestamp,
                        zone_id=zone.zone_id,
                        zone_name=zone.name,
                        zone_severity=zone.severity.value,
                        transition="entered",
                        dwell_duration_seconds=0.0,
                        narrative=narrative,
                        threat_score=t_score,
                        threat_reasons=t_reasons,
                    )
                    zone_events.append(ze)

                    # Generate Security Alert for intrusion into restricted/critical zone
                    if is_restricted:
                        # -- Zone-entry deduplication cooldown --
                        entry_key = (str(t_id), z_id)
                        last_entry_alert = self._zone_entry_last_alert.get(entry_key)
                        _now_ts = track.timestamp
                        if last_entry_alert is not None:
                            elapsed_entry = _diff_seconds(_now_ts, last_entry_alert)
                            if elapsed_entry < self._zone_entry_cooldown_secs:
                                # Same target re-entering within cooldown — do NOT open a new alert/incident.
                                # Just update the existing incident via the engine without emitting an alert.
                                continue

                        self._zone_entry_last_alert[entry_key] = _now_ts

                        causal_chain = [
                            f"1. {track.object_class.title()} detected (Conf: {int(track.confidence * 100)}%)",
                            f"2. Track #{t_id} established by ByteTrack",
                            f"3. Target entered Restricted Zone '{zone.name}'",
                            f"4. Movement vector: Heading {heading} ({track.speed_description})",
                        ]
                        if is_night:
                            causal_chain.append("5. Night movement detected (22:00\u201305:00 / Low Light)")
                        if heading_protected:
                            causal_chain.append("6. Directional trajectory heading toward protected assets")
                        causal_chain.append(f"7. Explainable Threat Score evaluated: {t_score} / {t_level}")

                        # Check cross-camera spatial-temporal correlation
                        try:
                            from backend.intelligence.correlation import get_correlator
                            correlator = get_correlator()
                            corr_event = correlator.check_correlation_on_entry(camera_id, zone.name, str(t_id), track.object_class, track.timestamp)
                            if corr_event and corr_event.correlation_confidence >= 0.60:
                                track.global_id = f"GLB-{corr_event.source_camera}-{corr_event.track_id}"
                                track.global_confidence = corr_event.correlation_confidence
                                causal_chain.append(f"Cross-Camera Handover: Matched Track #{corr_event.track_id} on {corr_event.source_camera} ({int(corr_event.correlation_confidence*100)}% conf)")
                        except Exception:
                            pass

                        f_num = getattr(track, "frame_number", None)
                        off_s = round(float(f_num) / 30.0, 2) if f_num is not None else None
                        alert = AlertEvent(
                            camera_id=camera_id,
                            track_id=t_id,
                            confidence=track.confidence,
                            source=source,
                            timestamp=track.timestamp,
                            severity=t_level,
                            zone_id=zone.zone_id,
                            zone_name=zone.name,
                            object_class=track.object_class,
                            message=f"SECURITY ALERT: Track {t_id} ({track.object_class}) entered restricted zone '{zone.name}' (Heading {heading})",
                            threat_score=t_score,
                            threat_level=t_level,
                            threat_reasons=t_reasons,
                            causal_chain=causal_chain,
                            heading=heading,
                            speed_description=track.speed_description,
                            best_frame_number=f_num,
                            timeline_offset_sec=off_s,
                        )
                        # Route through IncidentEngine: assigns stable incident_id
                        self.incident_engine.process_alert(alert, current_position=curr_pos)
                        alert_events.append(alert)

                elif not is_inside and was_inside:
                    # STATE TRANSITION: EXITED
                    self._track_zone_state[t_id][z_id] = False
                    entry_time = self._track_zone_entry_time[t_id].pop(z_id, None)
                    dwell_secs = None
                    if entry_time is not None:
                        dwell_secs = max(0.0, _diff_seconds(track.timestamp, entry_time))

                    self._track_zone_loiter_alert_time[t_id].pop(z_id, None)
                    track.previous_zone = zone.name
                    track.current_zone = None
                    track.zone_dwell_seconds = 0.0

                    narrative = f"{track.object_class.upper()} #{t_id} exited {zone.name} after {dwell_secs or 0.0:.1f}s."

                    # Record exit for cross-camera correlation
                    try:
                        from backend.intelligence.correlation import get_correlator
                        get_correlator().record_exit(camera_id, zone.name, str(t_id), track.object_class, track.timestamp)
                    except Exception:
                        pass

                    # Notify IncidentEngine so it can start the grace timer
                    if zone.severity in (ZoneSeverity.RESTRICTED, ZoneSeverity.CRITICAL):
                        self.incident_engine.process_exit(
                            camera_id=camera_id,
                            rule_type="zone_intrusion",
                            zone_id=zone.zone_id,
                            track_id=str(t_id),
                        )

                    ze = ZoneEvent(
                        camera_id=camera_id,
                        track_id=t_id,
                        confidence=track.confidence,
                        source=source,
                        timestamp=track.timestamp,
                        zone_id=zone.zone_id,
                        zone_name=zone.name,
                        zone_severity=zone.severity.value,
                        transition="exited",
                        dwell_duration_seconds=round(dwell_secs, 2) if dwell_secs is not None else None,
                        narrative=narrative,
                        threat_score=track.threat_score,
                    )
                    zone_events.append(ze)

                elif is_inside and was_inside:
                    # DWELLING: Update dwell clock & evaluate Loitering threshold
                    entry_time = self._track_zone_entry_time[t_id].get(z_id, track.timestamp)
                    dwell_secs = max(0.0, _diff_seconds(track.timestamp, entry_time))
                    track.zone_dwell_seconds = dwell_secs
                    track.current_zone = zone.name

                    if zone.loitering_threshold_seconds is not None and zone.loitering_threshold_seconds > 0:
                        if dwell_secs >= zone.loitering_threshold_seconds:
                            last_alert = self._track_zone_loiter_alert_time[t_id].get(z_id)
                            should_alert = False
                            if last_alert is None:
                                should_alert = True
                            elif _diff_seconds(track.timestamp, last_alert) >= zone.loitering_debounce_seconds:
                                should_alert = True

                            if should_alert:
                                self._track_zone_loiter_alert_time[t_id][z_id] = track.timestamp
                                narrative = f"{track.object_class.upper()} #{t_id} loitering in {zone.name} for {dwell_secs:.1f}s."

                                t_score, t_level, t_reasons = compute_threat_score(
                                    has_restricted_intrusion=zone.severity in (ZoneSeverity.RESTRICTED, ZoneSeverity.CRITICAL),
                                    has_tripwire_breach=False,
                                    has_loitering=True,
                                    has_night_movement=is_night,
                                    has_multiple_unauthorized=len(active_track_ids) > 1,
                                    has_movement_towards_protected=heading_protected,
                                )
                                track.threat_score = t_score

                                ze = ZoneEvent(
                                    camera_id=camera_id,
                                    track_id=t_id,
                                    confidence=track.confidence,
                                    source=source,
                                    timestamp=track.timestamp,
                                    zone_id=zone.zone_id,
                                    zone_name=zone.name,
                                    zone_severity=zone.severity.value,
                                    transition="loitering",
                                    dwell_duration_seconds=round(dwell_secs, 2),
                                    narrative=narrative,
                                    threat_score=t_score,
                                    threat_reasons=t_reasons,
                                )
                                zone_events.append(ze)

                                causal_chain = [
                                    f"1. {track.object_class.title()} detected in sector",
                                    f"2. Track #{t_id} continuously observed in '{zone.name}'",
                                    f"3. Dwell duration exceeded security limit ({dwell_secs:.1f}s >= {zone.loitering_threshold_seconds}s)",
                                ]
                                if is_night:
                                    causal_chain.append("4. Night surveillance period active")
                                causal_chain.append(f"5. Loitering Threat Score evaluated: {t_score} / {t_level}")

                                f_num = getattr(track, "frame_number", None)
                                off_s = round(float(f_num) / 30.0, 2) if f_num is not None else None
                                alert = AlertEvent(
                                    camera_id=camera_id,
                                    track_id=t_id,
                                    confidence=track.confidence,
                                    source=source,
                                    timestamp=track.timestamp,
                                    severity=t_level,
                                    zone_id=zone.zone_id,
                                    zone_name=zone.name,
                                    object_class=track.object_class,
                                    message=(
                                        f"LOITERING ALERT: Track {t_id} ({track.object_class}) dwelling in zone "
                                        f"'{zone.name}' for {dwell_secs:.1f}s (threshold: {zone.loitering_threshold_seconds}s)"
                                    ),
                                    threat_score=t_score,
                                    threat_level=t_level,
                                    threat_reasons=t_reasons,
                                    causal_chain=causal_chain,
                                    heading=heading,
                                    speed_description=track.speed_description,
                                    best_frame_number=f_num,
                                    timeline_offset_sec=off_s,
                                )
                                # Route through IncidentEngine: escalates existing incident; does NOT open a new one
                                self.incident_engine.process_alert(alert, current_position=curr_pos)
                                alert_events.append(alert)

            # 2. Evaluate Virtual Boundaries (Directional Line crossing)
            if prev_pos is not None:
                for b_id, boundary in self.boundaries.items():
                    if not boundary.is_active:
                        continue
                    if boundary.camera_id is not None and boundary.camera_id != camera_id:
                        continue
                    if boundary.target_classes and track.object_class not in boundary.target_classes:
                        continue

                    crossing_dir = boundary.check_crossing(prev_pos, curr_pos)
                    if crossing_dir is None and hasattr(track, "bounding_box") and track.bounding_box and len(track.bounding_box) >= 4:
                        h_offset = float(track.bounding_box[3]) - curr_pos[1]
                        bottom_prev = (prev_pos[0], prev_pos[1] + h_offset)
                        bottom_curr = (curr_pos[0], float(track.bounding_box[3]))
                        crossing_dir = boundary.check_crossing(bottom_prev, bottom_curr)
                    if crossing_dir is not None:
                        # Debounce check per track and boundary
                        if t_id not in self._track_boundary_alert_time:
                            self._track_boundary_alert_time[t_id] = {}
                        last_alert_time = self._track_boundary_alert_time[t_id].get(b_id)
                        if last_alert_time is not None:
                            elapsed = _diff_seconds(track.timestamp, last_alert_time)
                            if elapsed < boundary.debounce_seconds:
                                continue
                        self._track_boundary_alert_time[t_id][b_id] = track.timestamp

                        crossing_label = crossing_dir if crossing_dir in ("NORTH", "SOUTH", "EAST", "WEST") else ("A -> B" if crossing_dir == "inbound" else "B -> A")
                        narrative = f"{track.object_class.upper()} #{t_id} breached tripwire '{boundary.name}' in direction {crossing_label}."

                        t_score, t_level, t_reasons = compute_threat_score(
                            has_restricted_intrusion=False,
                            has_tripwire_breach=True,
                            has_loitering=False,
                            has_night_movement=is_night,
                            has_multiple_unauthorized=len(active_track_ids) > 1,
                            has_movement_towards_protected=heading_protected,
                        )
                        track.threat_score = t_score

                        ze = ZoneEvent(
                            camera_id=camera_id,
                            track_id=t_id,
                            confidence=track.confidence,
                            source=source,
                            timestamp=track.timestamp,
                            zone_id=boundary.boundary_id,
                            zone_name=boundary.name,
                            zone_severity=boundary.severity.value,
                            transition="crossed",
                            crossing_direction=crossing_label,
                            narrative=narrative,
                            threat_score=t_score,
                            threat_reasons=t_reasons,
                        )
                        zone_events.append(ze)

                        causal_chain = [
                            f"1. {track.object_class.title()} detected on perimeter",
                            f"2. Persistent Track #{t_id} movement tracked across frames",
                            f"3. Virtual tripwire '{boundary.name}' breached ({crossing_label})",
                            f"4. Movement vector: Heading {heading} ({track.speed_description})",
                        ]
                        if is_night:
                            causal_chain.append("5. Night intrusion condition triggered")
                        if heading_protected:
                            causal_chain.append("6. Directional vector aimed at internal defense perimeter")
                        causal_chain.append(f"7. Border Breach Threat Score evaluated: {t_score} / {t_level}")

                        f_num = getattr(track, "frame_number", None)
                        off_s = round(float(f_num) / 30.0, 2) if f_num is not None else None
                        alert = AlertEvent(
                            camera_id=camera_id,
                            track_id=t_id,
                            confidence=track.confidence,
                            source=source,
                            timestamp=track.timestamp,
                            severity=t_level,
                            zone_id=boundary.boundary_id,
                            zone_name=boundary.name,
                            object_class=track.object_class,
                            message=f"BORDER BREACH: Track {t_id} ({track.object_class}) crossed virtual boundary '{boundary.name}' ({crossing_label})",
                            threat_score=t_score,
                            threat_level=t_level,
                            threat_reasons=t_reasons,
                            causal_chain=causal_chain,
                            heading=heading,
                            speed_description=track.speed_description,
                            best_frame_number=f_num,
                            timeline_offset_sec=off_s,
                        )
                        # Route through IncidentEngine: deduplicates boundary crossing incidents
                        self.incident_engine.process_alert(alert, current_position=curr_pos)
                        alert_events.append(alert)

            # Evaluate PathGuard Route Integrity & Corridor Deviation
            try:
                from backend.zones.pathguard import get_pathguard_monitor
                pg_alerts = get_pathguard_monitor().evaluate_object(
                    camera_id=camera_id,
                    tracked_obj=track,
                    current_time_sec=now_dt.timestamp(),
                )
                for pg_a in pg_alerts:
                    self.incident_engine.process_alert(pg_a, current_position=curr_pos)
                    alert_events.append(pg_a)
            except Exception as pg_err:
                logger.debug(f"PathGuard evaluation error on track {t_id}: {pg_err}")

            # Update previous position
            self._track_prev_positions[t_id] = curr_pos

        # Cleanup tracks that are no longer active
        dormant_ids = [tid for tid in list(self._track_prev_positions.keys()) if tid not in active_track_ids]
        for tid in dormant_ids:
            if tid in self._track_zone_state:
                for z_id, was_in in self._track_zone_state[tid].items():
                    if was_in and z_id in self.zones:
                        z = self.zones[z_id]
                        entry_time = self._track_zone_entry_time.get(tid, {}).pop(z_id, None)
                        ze = ZoneEvent(
                            camera_id=camera_id,
                            track_id=tid,
                            source=source,
                            zone_id=z.zone_id,
                            zone_name=z.name,
                            zone_severity=z.severity.value,
                            transition="exited",
                            dwell_duration_seconds=0.0,
                            narrative=f"Track #{tid} disappeared/exited {z.name}.",
                        )
                        zone_events.append(ze)
                del self._track_zone_state[tid]
            if tid in self._track_zone_entry_time:
                del self._track_zone_entry_time[tid]
            if tid in self._track_zone_loiter_alert_time:
                del self._track_zone_loiter_alert_time[tid]
            if tid in self._track_boundary_alert_time:
                del self._track_boundary_alert_time[tid]
            del self._track_prev_positions[tid]

        # Tick the incident engine each frame to expire grace timers
        self.incident_engine.tick()

        return zone_events, alert_events


global_zone_monitor = ZoneMonitor()


def get_zone_monitor() -> ZoneMonitor:
    return global_zone_monitor
