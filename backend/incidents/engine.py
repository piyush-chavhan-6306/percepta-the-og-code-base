"""
PERCEPTA Incident Aggregation Engine.

Converts raw AlertEvents from ZoneMonitor into stable, deduplicated,
operator-facing Incidents with proper lifecycle management.

Fundamental invariant:
    ONE UNDERLYING SECURITY SITUATION == ONE OPERATOR-FACING INCIDENT

Design principles:
  - Spatial continuity: a new ByteTrack ID that is spatially close to the
    previous track of the same class is associated with the existing incident
    rather than opening a new one.
  - Zone intrusion deduplication: a re-entry cooldown window prevents the same
    target from opening a second incident while the first is still active.
  - Dwell escalation: loitering updates the existing incident; it does not
    create a second one.
  - Tripwire: the existing 3 s boundary debounce propagates upward so the
    incident layer never sees a duplicate crossing from a single physical event.
  - Incident lifecycle: ACTIVE -> ACKNOWLEDGED -> RESOLVED.
    Re-entry creates a new incident only AFTER the previous one is RESOLVED.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from backend.events.schema import AlertEvent, normalize_severity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tuneable constants
# ---------------------------------------------------------------------------
INCIDENT_ZONE_REENTRY_COOLDOWN_SECS: float = 60.0   # Resolved incident kept this long to block re-open
INCIDENT_GRACE_PERIOD_SECS: float = 10.0             # Seconds before closing incident after target exits
INCIDENT_MAX_AGE_SECS: float = 25.0                  # Auto-resolve dormant incidents after object disappears from scene
EVIDENCE_CAPTURE_COOLDOWN_SECS: float = 8.0          # Min secs between evidence frames per incident
SPATIAL_CONTINUITY_RADIUS_PX: float = 85.0           # Spatial window to recover fragmented track IDs


def _spatial_distance(p1: Optional[Tuple[float, float]], p2: Optional[Tuple[float, float]]) -> float:
    if p1 is None or p2 is None:
        return float("inf")
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return (dx * dx + dy * dy) ** 0.5


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
class IncidentStatus:
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class IncidentRecord:
    """In-memory representation of one security incident."""
    incident_id: str
    camera_id: str
    rule_type: str              # "zone_intrusion" | "loitering" | "boundary_crossed"
    zone_id: Optional[str]
    zone_name: Optional[str]
    primary_track_id: str       # Latest ByteTrack ID; updated on continuity association
    object_class: str
    severity: str               # "CRITICAL" | "RESTRICTED" | "WARNING" | "NORMAL"
    status: str                 # IncidentStatus.*
    first_seen: datetime
    last_updated: datetime
    dwell_seconds: float
    threat_score: float
    threat_level: str
    threat_reasons: List[str]
    causal_chain: List[str]
    evidence_count: int
    last_position: Optional[Tuple[float, float]]    # (cx, cy) last known centroid
    last_evidence_time: float                        # perf_counter timestamp
    associated_track_ids: List[str]                  # All ByteTrack IDs ever linked
    alert_id: str                                    # event_id of the opening AlertEvent
    last_alert_time: float                           # perf_counter timestamp
    best_frame_number: Optional[int] = None
    timeline_offset_sec: Optional[float] = None
    replay_url: Optional[str] = None
    replay_available: bool = True

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.last_updated).total_seconds()

    def is_dormant(self) -> bool:
        return self.age_seconds() > INCIDENT_MAX_AGE_SECS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_key(camera_id: str, rule_type: str, zone_id: Optional[str], track_id: str) -> str:
    """
    Stable string key.  Uses track_id for the primary match so that separate
    targets in the same zone produce separate incidents.  The spatial-continuity
    search handles cases where ByteTrack issues a new ID for the same target.
    """
    z = zone_id or "NONE"
    return f"{camera_id}::{rule_type}::{z}::{track_id}"


def _sev_rank(sev: str) -> int:
    return {"NORMAL": 0, "RESTRICTED": 1, "CRITICAL": 2}.get(normalize_severity(sev), 0)


def _extract_dwell_secs(message: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*s", message)
    return float(m.group(1)) if m else None


def _spatial_distance(
    pos_a: Optional[Tuple[float, float]],
    pos_b: Optional[Tuple[float, float]],
) -> float:
    if pos_a is None or pos_b is None:
        return float("inf")
    return ((pos_a[0] - pos_b[0]) ** 2 + (pos_a[1] - pos_b[1]) ** 2) ** 0.5


def _classify_rule(message: str) -> str:
    msg_upper = message.upper()
    if "LOITERING" in msg_upper or "DWELLING" in msg_upper:
        return "loitering"
    if (
        "BORDER BREACH" in msg_upper
        or "TRIPWIRE" in msg_upper
        or "BOUNDARY" in msg_upper
        or "CROSSED" in msg_upper
    ):
        return "boundary_crossed"
    return "zone_intrusion"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class IncidentEngine:
    """
    Stateful, in-process incident aggregation engine.

    Call ``process_alert()`` for every AlertEvent produced by ZoneMonitor.
    The engine mutates ``alert.incident_id`` to the stable incident UUID so
    all downstream persistence (EventStore, EvidenceEvent) is automatically
    linked to the correct incident.
    """

    def __init__(self) -> None:
        # Primary lookup: key -> IncidentRecord (ACTIVE or ACKNOWLEDGED)
        self._active: Dict[str, IncidentRecord] = {}
        # Recently resolved records: key -> IncidentRecord
        self._resolved: Dict[str, IncidentRecord] = {}
        # Grace period: key -> perf_counter time when timer started
        self._grace_timers: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process_alert(
        self,
        alert: AlertEvent,
        current_position: Optional[Tuple[float, float]] = None,
    ) -> Tuple[IncidentRecord, bool]:
        """
        Classify an AlertEvent into an existing or new incident.

        Mutates ``alert.incident_id`` in place.
        Returns ``(record, is_new_incident)``.
        """
        rule_type = _classify_rule(alert.message or "")
        zone_id: Optional[str] = getattr(alert, "zone_id", None)
        zone_name: Optional[str] = getattr(alert, "zone_name", None)
        tid = str(alert.track_id) if alert.track_id is not None else "UNKNOWN"
        key = _make_key(alert.camera_id, rule_type, zone_id, tid)
        norm_sev = normalize_severity(alert.threat_level or alert.severity)

        # 1. Exact key match
        existing = self._active.get(key)

        # 2. Check if this target already has an active incident in this zone (e.g. zone_intrusion escalating to loitering)
        if existing is None and zone_id is not None:
            for act_key, rec in list(self._active.items()):
                if (
                    rec.camera_id == alert.camera_id
                    and rec.zone_id == zone_id
                    and (tid in rec.associated_track_ids or rec.primary_track_id == tid)
                    and rec.status != IncidentStatus.RESOLVED
                ):
                    existing = rec
                    self._active[key] = existing
                    break

        # 3. Spatial continuity (ByteTrack ID fragmentation recovery)
        if existing is None and current_position is not None:
            existing = self._find_by_spatial_continuity(
                alert.camera_id, rule_type, zone_id, current_position
            )

        now_dt = datetime.now(timezone.utc)

        if existing is not None and existing.status != IncidentStatus.RESOLVED:
            # ── UPDATE existing incident ────────────────────────────────
            # Absorb new ByteTrack ID
            if tid not in existing.associated_track_ids:
                existing.associated_track_ids.append(tid)
                existing.primary_track_id = tid
                # Register under new key so future exact lookups hit immediately
                new_key = _make_key(alert.camera_id, rule_type, zone_id, tid)
                self._active[new_key] = existing

            existing.last_updated = now_dt
            if current_position is not None:
                existing.last_position = current_position

            # Dwell / Loitering escalation
            if rule_type == "loitering":
                existing.rule_type = "loitering"

            # Severity only escalates
            if _sev_rank(norm_sev) > _sev_rank(existing.severity):
                existing.severity = norm_sev

            # Threat score only escalates (clamped 0-100)
            if alert.threat_score is not None:
                new_score = min(100.0, max(0.0, float(alert.threat_score)))
                if new_score > existing.threat_score:
                    existing.threat_score = new_score
                    existing.threat_level = str(alert.threat_level or existing.threat_level)
                    existing.threat_reasons = list(alert.threat_reasons or existing.threat_reasons)

            # Dwell escalation from loitering messages
            dwell = _extract_dwell_secs(alert.message or "")
            if dwell is not None and dwell > existing.dwell_seconds:
                existing.dwell_seconds = dwell

            frame_num = getattr(alert, "best_frame_number", None) or getattr(alert, "frame_number", None)
            offset_sec = getattr(alert, "timeline_offset_sec", None) or (round(float(frame_num) / 30.0, 2) if frame_num is not None else None)
            if existing.best_frame_number is None and frame_num is not None:
                existing.best_frame_number = frame_num
                existing.timeline_offset_sec = offset_sec

            # Cancel any pending grace timer (target still active)
            self._grace_timers.pop(key, None)

            alert.incident_id = existing.incident_id
            return existing, False

        else:
            # ── OPEN new incident ───────────────────────────────────────
            incident_id = f"INC-{uuid4().hex[:10].upper()}"
            obj_class = str(getattr(alert, "object_class", None) or "person")
            frame_num = getattr(alert, "best_frame_number", None) or getattr(alert, "frame_number", None)
            offset_sec = getattr(alert, "timeline_offset_sec", None) or (round(float(frame_num) / 30.0, 2) if frame_num is not None else None)
            norm_score = min(100.0, max(0.0, float(alert.threat_score or 0.0)))

            rec = IncidentRecord(
                incident_id=incident_id,
                camera_id=alert.camera_id,
                rule_type=rule_type,
                zone_id=zone_id,
                zone_name=zone_name,
                primary_track_id=tid,
                object_class=obj_class,
                severity=norm_sev,
                status=IncidentStatus.ACTIVE,
                first_seen=now_dt,
                last_updated=now_dt,
                dwell_seconds=_extract_dwell_secs(alert.message or "") or 0.0,
                threat_score=norm_score,
                threat_level=norm_sev,
                threat_reasons=list(alert.threat_reasons or []),
                causal_chain=list(alert.causal_chain or []),
                evidence_count=0,
                last_position=current_position,
                last_evidence_time=0.0,
                associated_track_ids=[tid],
                alert_id=str(alert.event_id),
                last_alert_time=time.perf_counter(),
                best_frame_number=frame_num,
                timeline_offset_sec=offset_sec,
                replay_url=f"/api/cameras/{alert.camera_id}/replay",
                replay_available=True,
            )
            self._active[key] = rec
            alert.incident_id = incident_id
            logger.info(
                f"[IncidentEngine] OPENED {incident_id} | {alert.camera_id} | "
                f"rule={rule_type} zone={zone_id} track={tid}"
            )
            return rec, True

    def process_exit(
        self,
        camera_id: str,
        rule_type: str,
        zone_id: Optional[str],
        track_id: str,
    ) -> None:
        """Start the grace period timer when a track exits a zone."""
        key = _make_key(camera_id, rule_type, zone_id, track_id)
        if key in self._active and key not in self._grace_timers:
            self._grace_timers[key] = time.perf_counter()
            logger.debug(f"[IncidentEngine] Grace timer started: {key}")

    def tick(self) -> List[IncidentRecord]:
        """
        Call once per frame to expire grace timers and auto-resolve dormant incidents.
        Returns list of newly-resolved IncidentRecords for database persistence.
        """
        now = time.perf_counter()
        resolved: List[IncidentRecord] = []

        # Grace period expiry
        for key, started_at in list(self._grace_timers.items()):
            if (now - started_at) >= INCIDENT_GRACE_PERIOD_SECS:
                rec = self._active.pop(key, None)
                if rec is not None:
                    rec.status = IncidentStatus.RESOLVED
                    rec.last_updated = datetime.now(timezone.utc)
                    self._resolved[key] = rec
                    resolved.append(rec)
                    logger.info(f"[IncidentEngine] RESOLVED {rec.incident_id} (grace expired)")
                del self._grace_timers[key]

        # Auto-resolve dormant incidents
        for key, rec in list(self._active.items()):
            if rec.is_dormant():
                rec.status = IncidentStatus.RESOLVED
                rec.last_updated = datetime.now(timezone.utc)
                self._resolved[key] = rec
                resolved.append(rec)
                del self._active[key]
                self._grace_timers.pop(key, None)
                logger.info(f"[IncidentEngine] AUTO-RESOLVED dormant {rec.incident_id}")

        # Purge old resolved records
        dt_now = datetime.now(timezone.utc)
        for key, rec in list(self._resolved.items()):
            if (dt_now - rec.last_updated).total_seconds() > INCIDENT_ZONE_REENTRY_COOLDOWN_SECS:
                del self._resolved[key]

        return resolved

    def acknowledge_incident(self, incident_id: str) -> bool:
        found = False
        for rec in self._active.values():
            if rec.incident_id == incident_id:
                rec.status = IncidentStatus.ACKNOWLEDGED
                found = True
        for rec in self._resolved.values():
            if rec.incident_id == incident_id:
                rec.status = IncidentStatus.ACKNOWLEDGED
                found = True
        return found

    def resolve_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        for key, rec in list(self._active.items()):
            if rec.incident_id == incident_id:
                rec.status = IncidentStatus.RESOLVED
                rec.last_updated = datetime.now(timezone.utc)
                self._resolved[key] = rec
                del self._active[key]
                self._grace_timers.pop(key, None)
                logger.info(f"[IncidentEngine] MANUALLY RESOLVED {incident_id}")
                return rec
        return None

    def get_active_incidents(self) -> List[IncidentRecord]:
        """Return all active/acknowledged incident records."""
        seen_ids: set = set()
        result: List[IncidentRecord] = []
        for rec in self._active.values():
            if rec.incident_id not in seen_ids:
                seen_ids.add(rec.incident_id)
                result.append(rec)
        result.sort(key=lambda r: r.last_updated, reverse=True)
        return result

    def get_incident_by_id(self, incident_id: str) -> Optional[IncidentRecord]:
        for rec in list(self._active.values()) + list(self._resolved.values()):
            if rec.incident_id == incident_id:
                return rec
        return None

    def can_capture_evidence(self, incident_id: str) -> bool:
        """Rate-limit evidence capture per incident."""
        rec = self.get_incident_by_id(incident_id)
        if rec is None:
            return True
        return (time.perf_counter() - rec.last_evidence_time) >= EVIDENCE_CAPTURE_COOLDOWN_SECS

    def record_evidence_captured(self, incident_id: str) -> None:
        rec = self.get_incident_by_id(incident_id)
        if rec is not None:
            rec.evidence_count += 1
            rec.last_evidence_time = time.perf_counter()

    def clear(self) -> None:
        """Clear all active in-memory incidents and grace timers."""
        self._active.clear()
        self._grace_timers.clear()

    def clear_camera(self, camera_id: str) -> None:
        """Clear incidents and grace timers belonging to a specific camera."""
        keys_to_remove = [k for k, rec in self._active.items() if rec.camera_id == camera_id]
        for k in keys_to_remove:
            del self._active[k]
            self._grace_timers.pop(k, None)
        resolved_to_remove = [k for k, rec in self._resolved.items() if rec.camera_id == camera_id]
        for k in resolved_to_remove:
            del self._resolved[k]
        logger.info(f"[IncidentEngine] Cleared {len(keys_to_remove)} active + {len(resolved_to_remove)} resolved incidents for camera '{camera_id}'")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _find_by_spatial_continuity(
        self,
        camera_id: str,
        rule_type: str,
        zone_id: Optional[str],
        position: Tuple[float, float],
    ) -> Optional[IncidentRecord]:
        best_dist = SPATIAL_CONTINUITY_RADIUS_PX
        best_rec: Optional[IncidentRecord] = None
        for rec in self._active.values():
            if rec.camera_id != camera_id:
                continue
            if rec.rule_type != rule_type:
                continue
            if rec.zone_id != zone_id:
                continue
            if rec.status == IncidentStatus.RESOLVED:
                continue
            dist = _spatial_distance(rec.last_position, position)
            if dist < best_dist:
                best_dist = dist
                best_rec = rec
        return best_rec


# Singleton
_engine_instance: Optional[IncidentEngine] = None


def get_incident_engine() -> IncidentEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = IncidentEngine()
    return _engine_instance
