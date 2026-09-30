"""
Border Intelligence Incident & Alert Description Generator.
Generates concise, human-readable, non-generic descriptions based on real event metadata:
- rule type (zone intrusion, tripwire crossing, persistent loitering/dwell)
- target class (person, vehicle, car, truck, etc.)
- camera ID
- zone name / tripwire name
- dwell duration
- movement direction
"""
from typing import Any, Dict, Optional


def generate_incident_description(
    rule_type: str,
    object_class: str = "person",
    zone_name: Optional[str] = None,
    tripwire_name: Optional[str] = None,
    dwell_seconds: float = 0.0,
    direction: Optional[str] = None,
    camera_id: str = "CAM-01",
) -> str:
    """
    Generate a short, concise, human-readable incident description (approx 1 sentence).
    Example:
    - "Person entered the restricted security zone."
    - "Person entered restricted zone Sector North Gate Approach."
    - "Vehicle crossed the configured tripwire."
    - "Vehicle crossed Tripwire Alpha from the configured entry direction."
    - "Person remained inside the restricted zone beyond the configured dwell threshold."
    """
    cls = (object_class or "target").strip().lower()
    cls_title = cls.capitalize()

    rule = (rule_type or "").lower()

    # 1. Tripwire / Boundary Crossed
    if "tripwire" in rule or "boundary" in rule or "crossed" in rule:
        target_name = tripwire_name or zone_name
        if target_name and direction:
            return f"{cls_title} crossed {target_name} from the configured {direction} direction."
        elif target_name:
            return f"{cls_title} crossed configured tripwire '{target_name}'."
        elif direction:
            return f"{cls_title} crossed the configured tripwire from the {direction} direction."
        else:
            return f"{cls_title} crossed the configured tripwire boundary."

    # 2. Loitering / Persistent Dwell
    if "loiter" in rule or "dwell" in rule or dwell_seconds >= 3.0:
        dwell_int = int(round(dwell_seconds)) if dwell_seconds > 0 else 0
        target_name = zone_name or "restricted zone"
        if dwell_int > 0:
            return f"{cls_title} remained inside {target_name} for {dwell_int} seconds, exceeding configured dwell threshold."
        else:
            return f"{cls_title} remained inside the restricted zone beyond the configured dwell threshold."

    # 3. Zone Intrusion / Perimeter Breach
    if zone_name:
        return f"{cls_title} entered restricted zone '{zone_name}'."
    return f"{cls_title} entered the restricted security zone."


def generate_alert_explanation(
    rule_type: str,
    object_class: str = "person",
    zone_name: Optional[str] = None,
    tripwire_name: Optional[str] = None,
    dwell_seconds: float = 0.0,
    direction: Optional[str] = None,
    camera_id: str = "CAM-01",
    track_id: Optional[str] = None,
) -> str:
    """
    Generate a short, clear explanation of WHY the alert was generated.
    Example:
    - Restricted Zone Intrusion: "Person detected inside Restricted Zone A after crossing the zone boundary."
    - Tripwire Crossing: "Vehicle crossed Tripwire Alpha from the configured entry direction."
    - Persistent Dwell: "Person remained inside Restricted Zone A beyond the configured dwell threshold."
    """
    cls = (object_class or "target").strip().lower()
    cls_title = cls.capitalize()
    rule = (rule_type or "").lower()
    z_name = zone_name or "the restricted security zone"
    t_name = tripwire_name or "the virtual tripwire"

    if "tripwire" in rule or "boundary" in rule or "crossed" in rule:
        if direction:
            return f"{cls_title} crossed {t_name} from the configured {direction} entry direction."
        return f"{cls_title} crossed {t_name} triggering directional boundary rule."

    if "loiter" in rule or "dwell" in rule or dwell_seconds >= 3.0:
        if dwell_seconds > 0:
            return f"{cls_title} remained inside {z_name} for {int(round(dwell_seconds))}s, exceeding the active loitering threshold."
        return f"{cls_title} remained inside {z_name} beyond the configured dwell threshold."

    return f"{cls_title} detected inside {z_name} after crossing the zone boundary."


def generate_timeline_event_description(
    event_type: str,
    payload: Dict[str, Any],
    timestamp: str = "",
    camera_id: str = "CAM-01",
    track_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate structured (time, event_type_label, description) for the Dossier timeline.
    Descriptions are kept strictly to approximately one sentence.
    """
    etype = (event_type or "EVENT").upper()
    rule_type = payload.get("rule_type") or payload.get("rule_id") or ""
    obj_class = payload.get("object_class") or "target"
    zone_name = payload.get("zone_name")
    tripwire_name = payload.get("tripwire_name")
    dwell_secs = float(payload.get("dwell_seconds") or payload.get("dwell_duration_seconds") or 0.0)
    direction = payload.get("direction") or payload.get("heading")
    message = payload.get("message") or ""
    tid_str = f" #{track_id}" if track_id else ""

    # Determine Event Type Label & Description
    if etype == "EVIDENCE":
        label = "Evidence Captured"
        ev_sub = payload.get("evidence_type") or "TARGET"
        if "FACE" in str(ev_sub).upper():
            desc = f"Facial region ROI evidence snapshot captured for Track{tid_str}."
        elif "ANPR" in str(ev_sub).upper() or "PLATE" in str(ev_sub).upper():
            desc = f"Vehicle license plate ROI crop captured for Track{tid_str}."
        elif "TARGET" in str(ev_sub).upper():
            desc = f"High-resolution target evidence crop captured for {obj_class} (Track{tid_str})."
        else:
            desc = f"Target evidence frame captured."
    elif "LOITER" in rule_type.upper() or "DWELL" in rule_type.upper() or dwell_secs > 0:
        label = "Persistent Dwell"
        if dwell_secs > 0:
            desc = f"Target{tid_str} remained inside the zone for {int(round(dwell_secs))} seconds."
        else:
            desc = f"{obj_class.capitalize()}{tid_str} loitered in the restricted sector."
    elif "TRIPWIRE" in rule_type.upper() or "BOUNDARY" in rule_type.upper():
        label = "Tripwire Crossing"
        tw = tripwire_name or "tripwire boundary"
        if direction:
            desc = f"{obj_class.capitalize()}{tid_str} crossed {tw} ({direction} vector)."
        else:
            desc = f"{obj_class.capitalize()}{tid_str} crossed {tw}."
    elif etype == "ALERT" or "INTRUSION" in rule_type.upper() or "ZONE" in rule_type.upper():
        label = "Zone Intrusion"
        zn = zone_name or "Restricted Zone"
        desc = f"{obj_class.capitalize()}{tid_str} entered {zn}."
    elif etype == "TRACKING" or etype == "TRACK":
        label = "Target Tracking"
        desc = f"Target{tid_str} remained inside the restricted zone."
    elif etype == "INCIDENT":
        label = "Incident State"
        lifecycle = payload.get("lifecycle") or payload.get("status") or "active"
        desc = f"Incident situation updated to {lifecycle.upper()}."
    elif etype == "SYSTEM":
        label = "System Checkpoint"
        desc = payload.get("details") or "System operational state checkpoint verified."
    else:
        label = etype.replace("_", " ").title()
        desc = message or f"Surveillance event recorded on {camera_id}."

    return {
        "event_type": label,
        "description": desc,
    }
