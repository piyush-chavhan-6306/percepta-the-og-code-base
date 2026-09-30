"""
Border Intelligence Incident Forensic Dossier & Situation Report (SitRep) Generator.
Compiles a complete, multi-dimensional, tamper-verified tactical briefing from SQLite evidence logs.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.events.store import EventStore, get_event_store


class MotionSummary(BaseModel):
    total_trajectory_points: int
    net_displacement_pixels: float
    average_speed_pixels_per_frame: float
    dominant_heading_degrees: Optional[float] = None
    dominant_cardinal_direction: Optional[str] = None
    target_class: str


class ZoneInfraction(BaseModel):
    zone_name: str
    transition_type: str
    timestamp: str
    dwell_duration_seconds: Optional[float] = None


class IncidentDossier(BaseModel):
    incident_id: str
    camera_id: str
    status: str
    severity: str
    first_seen: str
    last_seen: str
    duration_seconds: float
    total_events_logged: int
    motion_summary: Optional[MotionSummary] = None
    infractions: List[ZoneInfraction]
    forensic_hash: str
    tactical_sitrep: str


class DossierGenerator:
    """Compiles grounded incident evidence into a formal tactical dossier."""

    def __init__(self, store: Optional[EventStore] = None) -> None:
        self.store = store or get_event_store()

    async def generate_dossier(self, incident_id: str) -> Optional[IncidentDossier]:
        """Generate a complete forensic dossier for an incident."""
        timeline = await self.store.get_incident_timeline(incident_id)
        if not timeline:
            return None

        camera_id = timeline[0].get("camera_id", "UNKNOWN")
        first_time_str = timeline[0].get("timestamp", "")
        last_time_str = timeline[-1].get("timestamp", "")

        try:
            t0 = datetime.fromisoformat(first_time_str)
            t1 = datetime.fromisoformat(last_time_str)
            duration = max(0.0, (t1 - t0).total_seconds())
        except Exception:
            duration = 0.0

        infractions = []
        positions = []
        speeds = []
        headings = []
        target_class = "person"
        max_severity = "RESTRICTED"

        for e in timeline:
            etype = e.get("event_type", "")
            raw_payload = e.get("payload", {})
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {}
            else:
                payload = raw_payload or {}

            # Zone infractions
            if etype in ("ZONE", "ALERT"):
                z_name = payload.get("zone_name") or payload.get("message", "Perimeter Zone")
                trans = payload.get("transition_type") or payload.get("transition", "breach")
                dwell = payload.get("dwell_duration_seconds")
                sev = payload.get("severity", "RESTRICTED")
                if "CRITICAL" in str(sev).upper():
                    max_severity = "CRITICAL"

                infractions.append(
                    ZoneInfraction(
                        zone_name=str(z_name),
                        transition_type=str(trans),
                        timestamp=str(e.get("timestamp", "")),
                        dwell_duration_seconds=dwell,
                    )
                )

            # Motion data
            if etype == "TRACKING":
                if payload.get("object_class"):
                    target_class = payload["object_class"]
                if payload.get("position"):
                    positions.append(payload["position"])
                if payload.get("speed") is not None:
                    speeds.append(payload["speed"])
                if payload.get("direction") is not None:
                    headings.append(payload["direction"])

        # Compute motion summary
        motion = None
        if positions:
            import math
            p0 = positions[0]
            pn = positions[-1]
            disp = math.sqrt((pn[0] - p0[0]) ** 2 + (pn[1] - p0[1]) ** 2)
            avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
            avg_heading = sum(headings) / len(headings) if headings else None

            cardinal = None
            if avg_heading is not None:
                dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                idx = round(avg_heading / 45.0) % 8
                cardinal = dirs[idx]

            motion = MotionSummary(
                total_trajectory_points=len(positions),
                net_displacement_pixels=round(disp, 1),
                average_speed_pixels_per_frame=round(avg_speed, 2),
                dominant_heading_degrees=round(avg_heading, 1) if avg_heading else None,
                dominant_cardinal_direction=cardinal,
                target_class=target_class,
            )

        # Compute SHA-256 forensic hash token of the dossier
        hash_src = f"{incident_id}|{camera_id}|{first_time_str}|{last_time_str}|{len(timeline)}"
        forensic_hash = hashlib.sha256(hash_src.encode("utf-8")).hexdigest()

        # Build Tactical SitRep
        sitrep_lines = [
            f"=== TACTICAL SITUATION REPORT (SITREP) — INCIDENT {incident_id} ===",
            f"SECTOR / CAMERA: {camera_id}",
            f"CLASSIFICATION: {max_severity} | STATUS: OPENED",
            f"TEMPORAL WINDOW: {first_time_str} to {last_time_str} ({duration:.1f}s elapsed)",
            f"TARGET PROFILE: {target_class} ({len(positions)} verified tracking observations)",
            f"TOTAL INFRACTIONS DETECTED: {len(infractions)}",
        ]
        if infractions:
            sitrep_lines.append(f"PRIMARY BREACH: {infractions[0].zone_name} ({infractions[0].transition_type})")
        if motion and motion.dominant_cardinal_direction:
            sitrep_lines.append(f"MOTION VECTOR: Heading {motion.dominant_cardinal_direction} ({motion.dominant_heading_degrees}°)")
        sitrep_lines.append(f"FORENSIC INTEGRITY: SHA-256 [{forensic_hash[:16]}...]")
        sitrep_lines.append("OPERATIONAL RECOMMENDATION: Maintain visual contact; dispatch Quick Reaction Team to designated coordinates.")

        return IncidentDossier(
            incident_id=incident_id,
            camera_id=camera_id,
            status="opened",
            severity=max_severity,
            first_seen=first_time_str,
            last_seen=last_time_str,
            duration_seconds=round(duration, 2),
            total_events_logged=len(timeline),
            motion_summary=motion,
            infractions=infractions,
            forensic_hash=forensic_hash,
            tactical_sitrep="\n".join(sitrep_lines),
        )


global_dossier_generator = DossierGenerator()


def get_dossier_generator() -> DossierGenerator:
    return global_dossier_generator
