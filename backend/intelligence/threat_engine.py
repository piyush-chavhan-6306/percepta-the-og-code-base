"""
Border Intelligence Real-Time Threat Assessment & Sector Threat Index Engine.
Computes deterministic, explainable DEFCON threat levels from active surveillance events.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.events.store import EventStore, get_event_store


class ThreatLevel(str, Enum):
    NORMAL = "NORMAL"          # Routine / Low Risk (0 - 24)
    RESTRICTED = "RESTRICTED"  # Meaningful Security Violation (25 - 59)
    CRITICAL = "CRITICAL"      # High-Priority Security Breach (60 - 100)
    # Backward compatibility aliases
    DEFCON_GREEN = "NORMAL"
    DEFCON_YELLOW = "RESTRICTED"
    DEFCON_ORANGE = "RESTRICTED"
    DEFCON_RED = "CRITICAL"


class ThreatAssessment(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    camera_id: Optional[str] = None
    threat_level: ThreatLevel
    threat_score: float = Field(..., ge=0.0, le=100.0, description="Normalized score 0-100")
    active_breaches: int
    active_loiterers: int
    active_tracks: int
    contributing_factors: List[str]
    recommended_action: str


def compute_threat_score(
    has_restricted_intrusion: bool = False,
    has_tripwire_breach: bool = False,
    has_loitering: bool = False,
    has_night_movement: bool = False,
    has_multiple_unauthorized: bool = False,
    has_movement_towards_protected: bool = False,
) -> Tuple[float, str, List[str]]:
    """
    Deterministic rule-based threat assessment algorithm.
    Explicitly rule-based (zero LLM involved).
    Returns (normalized_score, threat_level_str, reasons_list).
    Strictly conforms to conceptual levels: NORMAL, RESTRICTED, CRITICAL.
    """
    raw_score = 0.0
    reasons = []

    if has_restricted_intrusion:
        raw_score += 35.0
        reasons.append("+35 Restricted Zone Intrusion")

    if has_tripwire_breach:
        raw_score += 30.0
        reasons.append("+30 Directional Tripwire Breach")

    if has_loitering:
        raw_score += 20.0
        reasons.append("+20 Loitering Beyond Threshold")

    if has_night_movement:
        raw_score += 15.0
        reasons.append("+15 Night Movement (22:00–05:00 / Low Light)")

    if has_movement_towards_protected:
        raw_score += 15.0
        reasons.append("+15 Movement Vector Toward Protected Area")

    if has_multiple_unauthorized:
        raw_score += 10.0
        reasons.append("+10 Multiple Unauthorized Tracks in Sector")

    score = min(100.0, max(0.0, raw_score))

    if score >= 60.0:
        level = "CRITICAL"
    elif score >= 25.0:
        level = "RESTRICTED"
    else:
        level = "NORMAL"

    if not reasons:
        reasons.append("Standard autonomous perimeter surveillance (Nominal)")

    return round(score, 1), level, reasons


class ThreatEngine:
    """Evaluates multi-factor surveillance events to compute an objective Sector Threat Index."""

    def __init__(self, store: Optional[EventStore] = None) -> None:
        self.store = store or get_event_store()

    async def evaluate_threat(
        self,
        camera_id: Optional[str] = None,
        lookback_seconds: int = 60,
    ) -> ThreatAssessment:
        """Calculate the real-time threat index over the lookback window."""
        now = datetime.now(timezone.utc)
        since_time = now - timedelta(seconds=lookback_seconds)

        # 1. Fetch recent alerts from SQLite WAL store
        alerts = await self.store.get_alerts(camera_id=camera_id, limit=50)

        recent_alerts = []
        for a in alerts:
            try:
                t = datetime.fromisoformat(a["timestamp"])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t >= since_time:
                    recent_alerts.append(a)
            except Exception:
                recent_alerts.append(a)

        # 2. Fetch recent tracking and zone events
        recent_events = await self.store.get_events(
            since=since_time,
            camera_id=camera_id,
            limit=200,
            newest_first=True,
        )

        has_tripwire = False
        has_restricted = False
        has_loiter = False
        has_night = False
        has_protected = False
        active_track_ids = set()

        # Check hour of day (Night is 22:00 to 05:00)
        hour = now.hour
        if hour >= 22 or hour < 5:
            has_night = True

        critical_count = 0
        restricted_count = 0
        loiter_count = 0

        for a in recent_alerts:
            msg = str(a.get("payload", "")).lower()
            sev = str(a.get("severity", "")).upper()
            if "crossed" in msg or "breach" in msg or "tripwire" in msg or "CRITICAL" in sev:
                has_tripwire = True
                critical_count += 1
            if "restricted" in msg or "RESTRICTED" in sev:
                has_restricted = True
                restricted_count += 1
            if "loiter" in msg or "dwelling" in msg:
                has_loiter = True
                loiter_count += 1
            if "night" in msg:
                has_night = True
            if "protected" in msg or "checkpoint" in msg:
                has_protected = True

        # Ingest active incidents from IncidentEngine
        max_incident_score = 0.0
        try:
            from backend.incidents.engine import get_incident_engine
            active_incidents = get_incident_engine().get_active_incidents()
            if camera_id:
                active_incidents = [inc for inc in active_incidents if inc.camera_id == camera_id]
            for inc in active_incidents:
                if inc.severity in ("CRITICAL", "HIGH") or inc.rule_type in ("boundary_crossed", "tripwire_breach"):
                    has_tripwire = True
                    critical_count += 1
                if inc.severity in ("RESTRICTED", "WARNING") or inc.rule_type == "zone_intrusion":
                    has_restricted = True
                    restricted_count += 1
                if inc.rule_type == "loitering":
                    has_loiter = True
                    loiter_count += 1
                for tid in (inc.associated_track_ids or [inc.primary_track_id]):
                    if tid:
                        active_track_ids.add(str(tid))
                if inc.threat_score:
                    max_incident_score = max(max_incident_score, float(inc.threat_score))
        except Exception:
            pass

        # Ingest live tracks directly from perception workers
        try:
            from backend.tracking.live_worker import get_worker_registry
            registry = get_worker_registry()
            if camera_id:
                w = registry.get_worker(camera_id)
                if w and hasattr(w, "pipeline") and hasattr(w.pipeline, "_last_tracks"):
                    for t in w.pipeline._last_tracks:
                        active_track_ids.add(str(t.track_id))
            else:
                for w in registry.list_workers():
                    if w and hasattr(w, "pipeline") and hasattr(w.pipeline, "_last_tracks"):
                        for t in w.pipeline._last_tracks:
                            active_track_ids.add(f"{w.camera_id}:{t.track_id}")
        except Exception:
            pass

        for e in recent_events:
            tid = e.get("track_id")
            if tid:
                active_track_ids.add(tid)
            ev_type = e.get("event_type")
            payload = str(e.get("payload", "")).lower()
            if ev_type == "ZONE":
                if "entered" in payload and ("restricted" in payload or "critical" in payload):
                    has_restricted = True
                if "crossed" in payload:
                    has_tripwire = True
                if "loiter" in payload:
                    has_loiter = True
                if "protected" in payload:
                    has_protected = True
            if "night" in payload:
                has_night = True

        has_multiple = len(active_track_ids) > 1 and (has_restricted or has_tripwire)

        computed_score = (
            (critical_count * 30.0)
            + (restricted_count * 35.0)
            + (loiter_count * 20.0)
            + (15.0 if has_night and (has_restricted or has_tripwire) else 0.0)
            + (15.0 if has_protected else 0.0)
            + (10.0 if has_multiple else 0.0)
        )
        raw_score = max(computed_score, max_incident_score)
        score = min(100.0, max(0.0, raw_score))

        if score >= 60.0:
            level = ThreatLevel.CRITICAL
        elif score >= 25.0:
            level = ThreatLevel.RESTRICTED
        else:
            level = ThreatLevel.NORMAL

        reasons = []
        if critical_count > 0:
            reasons.append(f"+{critical_count * 30} Directional Tripwire / Boundary Breaches ({critical_count})")
        if restricted_count > 0:
            reasons.append(f"+{restricted_count * 35} Restricted Zone Intrusions ({restricted_count})")
        if loiter_count > 0:
            reasons.append(f"+{loiter_count * 20} Loitering Beyond Threshold ({loiter_count})")
        if has_night:
            reasons.append("+15 Night Movement (22:00–05:00 / Low Light)")
        if has_protected:
            reasons.append("+15 Movement Vector Toward Protected Area")
        if has_multiple:
            reasons.append(f"+10 Multiple Unauthorized Tracks in Sector ({len(active_track_ids)})")
        if not reasons:
            reasons.append("Standard autonomous perimeter surveillance (Nominal)")

        action_map = {
            ThreatLevel.CRITICAL: "CRITICAL: Immediate Quick Reaction Force (QRF) dispatch and sector lockdown.",
            ThreatLevel.RESTRICTED: "RESTRICTED: Alert sector commander, verify zone boundary, ready patrol units.",
            ThreatLevel.NORMAL: "NORMAL: Standard autonomous perimeter monitoring active.",
        }

        return ThreatAssessment(
            timestamp=now,
            camera_id=camera_id,
            threat_level=level,
            threat_score=score,
            active_breaches=(1 if has_tripwire else 0) + (1 if has_restricted else 0),
            active_loiterers=1 if has_loiter else 0,
            active_tracks=len(active_track_ids),
            contributing_factors=reasons,
            recommended_action=action_map.get(level, "Standard monitoring"),
        )


global_threat_engine = ThreatEngine()


def get_threat_engine() -> ThreatEngine:
    return global_threat_engine
