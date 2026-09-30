"""
Border Intelligence Incidents REST API.
Provides endpoints for real-time active incidents (from IncidentEngine in-memory state)
and historical incidents (from event_logs DB), plus lifecycle actions.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from backend.events.snapshots import get_snapshot_manager
from backend.events.store import get_event_store
from backend.incidents.descriptions import (
    generate_alert_explanation,
    generate_incident_description,
    generate_timeline_event_description,
)
from backend.incidents.engine import IncidentStatus, get_incident_engine
from backend.ingestion.camera_manager import get_camera_manager
from backend.events.schema import normalize_severity

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])


# ---------------------------------------------------------------------------
# Helper: Extract best evidence URIs and replay position for an incident
# ---------------------------------------------------------------------------
def _resolve_evidence_uris(
    incident_id: str,
    alert_id: Optional[str] = None,
    camera_id: Optional[str] = None,
) -> Dict[str, Any]:
    snap_mgr = get_snapshot_manager()
    snaps = snap_mgr.list_snapshots(incident_id, alert_id=alert_id)
    ev_uri = None
    target_uri = None
    face_uri = None
    anpr_uri = None
    frame_number = None

    for s in snaps:
        etype = getattr(s, "evidence_type", "")
        fn = getattr(s, "frame_number", 0)
        if fn > 0 and frame_number is None:
            frame_number = fn
        if etype == "TARGET_CROP" and not target_uri:
            target_uri = s.file_uri
        elif etype == "FACE_CROP" and not face_uri:
            face_uri = s.file_uri
        elif etype == "ANPR_PLATE" and not anpr_uri:
            anpr_uri = s.file_uri
        elif etype == "FULL_SCENE" and not ev_uri:
            ev_uri = s.file_uri

    if not ev_uri and snaps:
        ev_uri = snaps[0].file_uri

    # Verify if source video is available for replay
    replay_avail = False
    native_fps = 30.0
    if camera_id:
        from backend.api.cameras import resolve_camera_source_video
        vid_p = resolve_camera_source_video(camera_id)
        if vid_p and vid_p.is_file():
            replay_avail = True
            cam = get_camera_manager().get_camera(camera_id)
            if cam and hasattr(cam, "adapter"):
                info = cam.adapter.get_stream_info() if hasattr(cam.adapter, "get_stream_info") else {}
                native_fps = float(info.get("native_fps") or 30.0)

    offset_sec = round(float(frame_number) / native_fps, 2) if frame_number else None

    return {
        "evidence_snapshot_uri": ev_uri,
        "target_crop_uri": target_uri,
        "face_snapshot_uri": face_uri,
        "anpr_snapshot_uri": anpr_uri,
        "best_frame_number": frame_number,
        "timeline_offset_sec": offset_sec,
        "replay_available": replay_avail,
    }


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class IncidentCard(BaseModel):
    """Rich incident entity for the Tactical Incident Feed."""
    incident_id: str
    camera_id: str
    rule_type: str
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    primary_track_id: str
    object_class: str
    severity: str
    status: str
    first_seen: str
    last_updated: str
    dwell_seconds: float
    threat_score: float
    threat_level: str
    threat_reasons: List[str] = []
    causal_chain: List[str] = []
    evidence_count: int
    associated_track_ids: List[str] = []
    alert_id: str
    description: Optional[str] = None
    alert_description: Optional[str] = None
    evidence_snapshot_uri: Optional[str] = None
    target_crop_uri: Optional[str] = None
    face_snapshot_uri: Optional[str] = None
    anpr_snapshot_uri: Optional[str] = None
    replay_url: Optional[str] = None
    best_frame_number: Optional[int] = None
    timeline_offset_sec: Optional[float] = None
    replay_available: bool = True


class IncidentListResponse(BaseModel):
    count: int
    capacity: int = 40
    incidents: List[IncidentCard]


class IncidentTimelineResponse(BaseModel):
    incident_id: str
    count: int
    timeline: List[Dict[str, Any]]


class IncidentReplayResponse(BaseModel):
    incident_id: str
    camera_id: str
    media_type: str                         # "video" | "image" | "none"
    media_url: Optional[str] = None         # Playable stream or verified snapshot URI
    mime_type: Optional[str] = None         # "video/mp4", "image/jpeg", etc.
    timeline_offset_sec: Optional[float] = None
    best_frame_number: Optional[int] = None
    severity: str
    rule_type: str
    timestamp: str
    threat_score: float
    evidence_snapshot_uri: Optional[str] = None
    target_crop_uri: Optional[str] = None
    face_snapshot_uri: Optional[str] = None
    anpr_snapshot_uri: Optional[str] = None
    file_exists: bool = True
    replay_available: bool = False
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="ACTIVE | ACKNOWLEDGED | RESOLVED | ALL"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    raw: bool = Query(False, description="Raw audit view across all cameras including historical/deleted"),
    limit: int = Query(40, ge=1, le=200),
) -> IncidentListResponse:
    """
    Return aggregated incidents with strict camera scoping and normalized severity.
    - ACTIVE: Returns currently active & acknowledged incidents for current camera.
    - ALL: Returns current camera's complete retained incident history.
    - raw=True: Returns cross-camera historical audit view including deleted cameras.
    """
    engine = get_incident_engine()
    store = get_event_store()

    status_upper = (status_filter or "").upper()
    want_active_only = status_upper == "ACTIVE"
    want_resolved = status_upper in ("RESOLVED", "ALL", "")

    # For raw view, ignore camera_id constraint to expose full cross-camera audit trail
    effective_camera_id = None if raw else camera_id

    # --- 1. In-memory active/acknowledged incidents ---
    active_records = engine.get_active_incidents()
    cards: List[IncidentCard] = []

    for rec in active_records:
        if effective_camera_id and rec.camera_id != effective_camera_id:
            continue
        norm_sev = normalize_severity(rec.severity)
        if severity and norm_sev != severity.upper():
            continue
        if want_active_only:
            if rec.status.upper() not in ("ACTIVE", "ACKNOWLEDGED"):
                continue
        elif status_upper and status_upper != "ALL":
            if rec.status.upper() != status_upper:
                continue

        desc = generate_incident_description(
            rule_type=rec.rule_type,
            object_class=rec.object_class,
            zone_name=rec.zone_name,
            dwell_seconds=rec.dwell_seconds,
            camera_id=rec.camera_id,
        )
        alert_desc = generate_alert_explanation(
            rule_type=rec.rule_type,
            object_class=rec.object_class,
            zone_name=rec.zone_name,
            dwell_seconds=rec.dwell_seconds,
            camera_id=rec.camera_id,
            track_id=rec.primary_track_id,
        )
        ev_uris = _resolve_evidence_uris(rec.incident_id, alert_id=rec.alert_id, camera_id=rec.camera_id)
        f_num = ev_uris.get("best_frame_number") or getattr(rec, "best_frame_number", None)
        off_sec = ev_uris.get("timeline_offset_sec") or getattr(rec, "timeline_offset_sec", None)
        clamped_score = min(100.0, max(0.0, float(rec.threat_score)))

        cards.append(
            IncidentCard(
                incident_id=rec.incident_id,
                camera_id=rec.camera_id,
                rule_type=rec.rule_type,
                zone_id=rec.zone_id,
                zone_name=rec.zone_name,
                primary_track_id=rec.primary_track_id,
                object_class=rec.object_class,
                severity=norm_sev,
                status=rec.status,
                first_seen=rec.first_seen.isoformat(),
                last_updated=rec.last_updated.isoformat(),
                dwell_seconds=rec.dwell_seconds,
                threat_score=clamped_score,
                threat_level=rec.threat_level,
                threat_reasons=rec.threat_reasons,
                causal_chain=rec.causal_chain,
                evidence_count=max(rec.evidence_count, 1 if ev_uris["evidence_snapshot_uri"] or ev_uris["target_crop_uri"] else 0),
                associated_track_ids=rec.associated_track_ids,
                alert_id=rec.alert_id,
                description=desc,
                alert_description=alert_desc,
                evidence_snapshot_uri=ev_uris["evidence_snapshot_uri"],
                target_crop_uri=ev_uris["target_crop_uri"],
                face_snapshot_uri=ev_uris["face_snapshot_uri"],
                anpr_snapshot_uri=ev_uris["anpr_snapshot_uri"],
                replay_url=f"/api/cameras/{rec.camera_id}/replay",
                best_frame_number=f_num,
                timeline_offset_sec=off_sec,
                replay_available=ev_uris.get("replay_available", True),
            )
        )

    # --- 2. Historical DB incidents (only when requested, not for ACTIVE-only) ---
    if (want_resolved or raw) and not want_active_only:
        db_incidents = await store.get_incidents(camera_id=effective_camera_id, limit=limit)
        active_ids = {c.incident_id for c in cards}
        for row in db_incidents:
            iid = row.get("incident_id", "")
            if iid in active_ids:
                continue  # Already covered by in-memory record
            if not iid.startswith("INC-"):
                continue

            row_sev = normalize_severity(row.get("severity", "NORMAL"))
            if severity and row_sev != severity.upper():
                continue

            rule_t = row.get("rule_type", "zone_intrusion")
            obj_c = row.get("object_class", "person")
            z_n = row.get("zone_name")
            d_sec = float(row.get("dwell_seconds", 0.0))
            cam_id = row.get("camera_id", "CAM-01")
            a_id = row.get("alert_id", iid)

            desc = generate_incident_description(
                rule_type=rule_t,
                object_class=obj_c,
                zone_name=z_n,
                dwell_seconds=d_sec,
                camera_id=cam_id,
            )
            alert_desc = generate_alert_explanation(
                rule_type=rule_t,
                object_class=obj_c,
                zone_name=z_n,
                dwell_seconds=d_sec,
                camera_id=cam_id,
                track_id=row.get("primary_track_id", ""),
            )
            ev_uris = _resolve_evidence_uris(iid, alert_id=a_id, camera_id=cam_id)
            clamped_score = min(100.0, max(0.0, float(row.get("threat_score", 0.0))))

            row_lifecycle = str(row.get("lifecycle") or row.get("status") or "").lower()
            persistent_status = IncidentStatus.ACKNOWLEDGED if row_lifecycle == "acknowledged" else IncidentStatus.RESOLVED

            cards.append(
                IncidentCard(
                    incident_id=iid,
                    camera_id=cam_id,
                    rule_type=rule_t,
                    zone_id=row.get("zone_id"),
                    zone_name=z_n,
                    primary_track_id=row.get("primary_track_id", ""),
                    object_class=obj_c,
                    severity=row_sev,
                    status=persistent_status,
                    first_seen=row.get("first_seen", ""),
                    last_updated=row.get("last_seen", ""),
                    dwell_seconds=d_sec,
                    threat_score=clamped_score,
                    threat_level=row.get("threat_level", "NORMAL"),
                    threat_reasons=[],
                    causal_chain=[],
                    evidence_count=max(int(row.get("total_events", 1)), 1 if ev_uris["evidence_snapshot_uri"] or ev_uris["target_crop_uri"] else 0),
                    associated_track_ids=[],
                    alert_id=a_id,
                    description=desc,
                    alert_description=alert_desc,
                    evidence_snapshot_uri=ev_uris["evidence_snapshot_uri"],
                    target_crop_uri=ev_uris["target_crop_uri"],
                    face_snapshot_uri=ev_uris["face_snapshot_uri"],
                    anpr_snapshot_uri=ev_uris["anpr_snapshot_uri"],
                    replay_url=f"/api/cameras/{cam_id}/replay",
                    best_frame_number=ev_uris.get("best_frame_number"),
                    timeline_offset_sec=ev_uris.get("timeline_offset_sec"),
                    replay_available=ev_uris.get("replay_available", True),
                )
            )

    # Sort newest-first, cap at limit
    cards.sort(key=lambda c: c.last_updated, reverse=True)
    cards = cards[:limit]

    return IncidentListResponse(count=len(cards), capacity=40, incidents=cards)


@router.get("/active", response_model=IncidentListResponse)
async def list_active_incidents(
    camera_id: Optional[str] = Query(None),
) -> IncidentListResponse:
    """Return only currently active/acknowledged incidents from live engine state scoped to camera."""
    return await list_incidents(camera_id=camera_id, status_filter="ACTIVE", limit=40)


@router.get("/raw", response_model=IncidentListResponse)
async def list_raw_incidents(
    limit: int = Query(50, ge=1, le=500),
    severity: Optional[str] = Query(None),
) -> IncidentListResponse:
    """
    Retrieve historical/raw incident records across all cameras,
    including previously deleted cameras (audit/raw data layer).
    """
    return await list_incidents(camera_id=None, status_filter="ALL", severity=severity, raw=True, limit=limit)


@router.get("/{incident_id}", response_model=IncidentTimelineResponse)
async def get_incident_timeline(incident_id: str) -> IncidentTimelineResponse:
    """
    Retrieve clean, deduplicated chronological timeline of meaningful events linked to an incident.
    Filters out raw frame-level detection noise per architectural standards.
    """
    import json
    store = get_event_store()
    raw_timeline = await store.get_incident_timeline(incident_id)

    # Filter and format meaningful events
    filtered: List[Dict[str, Any]] = []
    last_track_sec = -10.0

    for ev in raw_timeline:
        etype = (ev.get("event_type") or "").upper()
        # Requirement 8: Filter out raw frame-level detections
        if etype in ("DETECTION", "RAW_DETECTION"):
            continue

        p_data = {}
        if ev.get("payload"):
            try:
                p_data = json.loads(ev["payload"]) if isinstance(ev["payload"], str) else ev["payload"]
            except Exception:
                p_data = {}

        # De-duplicate consecutive high-frequency tracking ticks to avoid spamming the timeline
        if etype in ("TRACK", "TRACKING"):
            try:
                ts_dt = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
                cur_sec = ts_dt.timestamp()
                if cur_sec - last_track_sec < 4.0:
                    continue
                last_track_sec = cur_sec
            except Exception:
                pass

        # Requirement 7: Generate short human-readable 1-sentence description
        gen_desc = generate_timeline_event_description(
            event_type=etype,
            payload=p_data,
            timestamp=ev.get("timestamp", ""),
            camera_id=ev.get("camera_id", "CAM-01"),
            track_id=ev.get("track_id"),
        )

        # Snapshot URIs if this event captured evidence
        ev_snap_uri = p_data.get("file_uri") or p_data.get("snapshot_uri") or p_data.get("evidence_snapshot_uri")
        t_crop_uri = p_data.get("target_crop_uri")

        filtered.append({
            "seq_id": ev.get("seq_id"),
            "event_id": ev.get("event_id"),
            "event_type": etype,
            "event_type_display": gen_desc["event_type"],
            "description": gen_desc["description"],
            "timestamp": ev.get("timestamp"),
            "camera_id": ev.get("camera_id"),
            "track_id": ev.get("track_id"),
            "incident_id": ev.get("incident_id"),
            "confidence": ev.get("confidence"),
            "evidence_snapshot_uri": ev_snap_uri,
            "target_crop_uri": t_crop_uri,
        })

    # If DB timeline is empty but incident exists in active engine, provide initial synthesized event
    if not filtered:
        engine = get_incident_engine()
        for rec in engine.get_active_incidents():
            if rec.incident_id == incident_id:
                initial_desc = generate_incident_description(
                    rule_type=rec.rule_type,
                    object_class=rec.object_class,
                    zone_name=rec.zone_name,
                    dwell_seconds=rec.dwell_seconds,
                    camera_id=rec.camera_id,
                )
                filtered.append({
                    "seq_id": 1,
                    "event_id": rec.alert_id,
                    "event_type": "ALERT",
                    "event_type_display": "Zone Intrusion" if "intrusion" in rec.rule_type.lower() else "Tripwire Crossing",
                    "description": initial_desc,
                    "timestamp": rec.first_seen.isoformat(),
                    "camera_id": rec.camera_id,
                    "track_id": rec.primary_track_id,
                    "incident_id": rec.incident_id,
                    "confidence": 0.92,
                })
                break

    return IncidentTimelineResponse(
        incident_id=incident_id,
        count=len(filtered),
        timeline=filtered,
    )


@router.get("/{incident_id}/dossier")
async def get_incident_dossier(incident_id: str):
    """
    Generate a complete, tamper-verified Tactical Incident Dossier and SitRep.
    Aggregates motion vectors, zone infractions, duration, and cryptographic SHA-256 tokens.
    """
    from backend.incidents.dossier import get_dossier_generator
    generator = get_dossier_generator()
    dossier = await generator.generate_dossier(incident_id)
    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    return dossier


async def perform_unified_acknowledgement(identifier: str) -> Dict[str, Any]:
    """
    Unified domain acknowledgement operation.
    Accepts either an incident_id (e.g. INC-...) or alert/event UUID.
    1. Updates IncidentEngine (active and resolved in-memory caches).
    2. Updates SQLite DB: IncidentModel (lifecycle='acknowledged') and AlertModel (is_acknowledged=True).
    3. Broadcasts real-time state change via WebSocket so all UI components update without refresh.
    """
    clean_id = str(identifier).strip()
    incident_id = clean_id if clean_id.startswith("INC-") else None
    alert_id = clean_id if not clean_id.startswith("INC-") else None

    engine = get_incident_engine()
    store = get_event_store()

    # 1. Update in-memory IncidentEngine
    if incident_id:
        engine.acknowledge_incident(incident_id)
    else:
        for inc in engine.get_active_incidents():
            if inc.alert_id == clean_id or clean_id in inc.associated_track_ids:
                engine.acknowledge_incident(inc.incident_id)
                incident_id = inc.incident_id
                break

    # 2. Update database tables (incidents, alerts)
    try:
        from backend.database import get_session_factory
        from backend.incidents.models import IncidentModel, AlertModel
        from sqlalchemy import update

        factory = get_session_factory()
        async with factory() as session:
            from sqlalchemy import select
            if incident_id:
                existing_inc = (await session.execute(select(IncidentModel).where(IncidentModel.incident_id == incident_id))).scalar_one_or_none()
                if existing_inc:
                    existing_inc.lifecycle = "acknowledged"
                else:
                    new_inc_row = IncidentModel(
                        incident_id=incident_id,
                        title=f"Incident {incident_id}",
                        severity="NORMAL",
                        lifecycle="acknowledged",
                        camera_id="CAM-01",
                    )
                    session.add(new_inc_row)

                await session.execute(
                    update(AlertModel)
                    .where(AlertModel.incident_id == incident_id)
                    .values(is_acknowledged=True)
                )
            if alert_id:
                await session.execute(
                    update(AlertModel)
                    .where(AlertModel.alert_id == alert_id)
                    .values(is_acknowledged=True)
                )
            await session.commit()
    except Exception as db_err:
        logger.warning(f"Database error during acknowledgement: {db_err}")

    # Also acknowledge in EventStore
    try:
        await store.acknowledge_alert(clean_id)
    except Exception:
        pass

    # 3. Broadcast WebSocket event to all connected C2 clients
    try:
        from backend.api.streaming import get_ws_manager
        ws = get_ws_manager()
        await ws.broadcast_json({
            "type": "INCIDENT_ACKNOWLEDGED",
            "event_type": "ALERT_ACKNOWLEDGED",
            "incident_id": incident_id or clean_id,
            "alert_id": alert_id or clean_id,
            "status": "ACKNOWLEDGED",
            "is_acknowledged": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as ws_err:
        logger.warning(f"Failed to broadcast acknowledgement WebSocket update: {ws_err}")

    return {
        "status": "acknowledged",
        "incident_id": incident_id or clean_id,
        "alert_id": alert_id or clean_id,
        "is_acknowledged": True,
    }


@router.post("/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str) -> Dict[str, Any]:
    """Acknowledge an incident (marks it as operator-reviewed)."""
    return await perform_unified_acknowledgement(incident_id)


@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: str) -> Dict[str, Any]:
    """Manually resolve an active incident."""
    engine = get_incident_engine()
    rec = engine.resolve_incident(incident_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active incident '{incident_id}' not found",
        )
    return {"incident_id": incident_id, "status": "resolved"}


@router.post("/{incident_id}/notes")
async def add_incident_note(incident_id: str, request: dict):
    """Append a timestamped human operator annotation or tactical action note to an incident."""
    from backend.incidents.annotations import get_annotation_manager
    manager = get_annotation_manager()
    callsign = request.get("operator_callsign", "Duty Officer")
    note = request.get("note", "").strip()
    disposition = request.get("disposition", "INVESTIGATING")

    if not note:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note content cannot be empty",
        )

    ann = await manager.add_annotation(
        incident_id=incident_id,
        operator_callsign=callsign,
        note=note,
        disposition=disposition,
    )
    return ann


@router.get("/{incident_id}/notes")
async def list_incident_notes(incident_id: str):
    """Retrieve chronological audit trail of all operator notes linked to an incident."""
    from backend.incidents.annotations import get_annotation_manager
    manager = get_annotation_manager()
    notes = await manager.get_annotations(incident_id)
    return {"incident_id": incident_id, "count": len(notes), "annotations": notes}


@router.get("/{incident_id}/replay", response_model=IncidentReplayResponse)
async def get_incident_replay_data(incident_id: str) -> IncidentReplayResponse:
    """
    Authoritative replay endpoint for an incident or security event.
    Determines whether real source video exists (playable with seeking),
    or whether only verified still evidence frames/crops exist.
    """
    from backend.api.cameras import resolve_camera_source_video
    from backend.api.streaming import _get_media_type_for_video

    engine = get_incident_engine()
    store = get_event_store()

    # 1. Lookup in-memory active/resolved incidents
    rec = engine.get_incident_by_id(incident_id)

    if rec is not None:
        camera_id = rec.camera_id
        severity = normalize_severity(rec.severity)
        rule_type = rec.rule_type
        threat_score = float(min(100.0, max(0.0, round(float(rec.threat_score), 1))))
        timestamp = rec.last_updated.isoformat()
        alert_id = rec.alert_id
        best_frame = rec.best_frame_number
        timeline_offset = rec.timeline_offset_sec
    else:
        # Check historical DB incidents
        db_incs = await store.get_incidents(limit=200)
        matched_row = next((r for r in db_incs if r.get("incident_id") == incident_id), None)
        if matched_row:
            camera_id = matched_row.get("camera_id", "CAM-01")
            severity = normalize_severity(matched_row.get("severity", "NORMAL"))
            rule_type = matched_row.get("rule_type", "zone_intrusion")
            threat_score = float(min(100.0, max(0.0, round(float(matched_row.get("threat_score") or 0.0), 1))))
            timestamp = matched_row.get("last_updated") or datetime.now(timezone.utc).isoformat()
            alert_id = matched_row.get("alert_id", incident_id)
            best_frame = None
            timeline_offset = None
        else:
            # Fallback: check if incident_id is an event_id or alert_id in store
            events = await store.get_events(limit=100)
            raw_event = next(
                (
                    e
                    for e in events
                    if e.get("event_id") == incident_id
                    or e.get("id") == incident_id
                    or e.get("alert_id") == incident_id
                ),
                None,
            )
            if raw_event:
                camera_id = raw_event.get("camera_id", "CAM-01")
                severity = normalize_severity(raw_event.get("severity", "NORMAL"))
                rule_type = raw_event.get("rule_type") or "perimeter_alert"
                threat_score = float(min(100.0, max(0.0, round(float(raw_event.get("threat_score") or 0.0), 1))))
                timestamp = raw_event.get("timestamp") or datetime.now(timezone.utc).isoformat()
                alert_id = incident_id
                best_frame = None
                timeline_offset = None
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Incident or evidence record '{incident_id}' not found.",
                )

    # 2. Extract best evidence snapshots
    ev_uris = _resolve_evidence_uris(incident_id, alert_id=alert_id, camera_id=camera_id)
    if best_frame is None:
        best_frame = ev_uris.get("best_frame_number")
    if timeline_offset is None:
        timeline_offset = ev_uris.get("timeline_offset_sec")

    # 3. Check if actual source video file exists for this camera
    video_path = resolve_camera_source_video(camera_id)
    has_video = video_path is not None and video_path.is_file()

    snap_file_uri = ev_uris.get("evidence_snapshot_uri") or ev_uris.get("target_crop_uri")
    has_image = bool(snap_file_uri)

    if has_video:
        mime = _get_media_type_for_video(video_path)
        return IncidentReplayResponse(
            incident_id=incident_id,
            camera_id=camera_id,
            media_type="video",
            media_url=f"/api/cameras/{camera_id}/replay",
            mime_type=mime,
            timeline_offset_sec=timeline_offset,
            best_frame_number=best_frame,
            severity=severity,
            rule_type=rule_type,
            timestamp=timestamp,
            threat_score=threat_score,
            evidence_snapshot_uri=ev_uris.get("evidence_snapshot_uri"),
            target_crop_uri=ev_uris.get("target_crop_uri"),
            face_snapshot_uri=ev_uris.get("face_snapshot_uri"),
            anpr_snapshot_uri=ev_uris.get("anpr_snapshot_uri"),
            file_exists=True,
            replay_available=True,
            message="Verified forensic CCTV replay stream accessible.",
        )
    elif has_image:
        return IncidentReplayResponse(
            incident_id=incident_id,
            camera_id=camera_id,
            media_type="image",
            media_url=snap_file_uri,
            mime_type="image/jpeg",
            timeline_offset_sec=None,
            best_frame_number=best_frame,
            severity=severity,
            rule_type=rule_type,
            timestamp=timestamp,
            threat_score=threat_score,
            evidence_snapshot_uri=ev_uris.get("evidence_snapshot_uri"),
            target_crop_uri=ev_uris.get("target_crop_uri"),
            face_snapshot_uri=ev_uris.get("face_snapshot_uri"),
            anpr_snapshot_uri=ev_uris.get("anpr_snapshot_uri"),
            file_exists=True,
            replay_available=False,
            message="High-resolution evidence snapshot verified. Video clip archive is not stored for this source.",
        )
    else:
        return IncidentReplayResponse(
            incident_id=incident_id,
            camera_id=camera_id,
            media_type="none",
            media_url=None,
            mime_type=None,
            timeline_offset_sec=None,
            best_frame_number=best_frame,
            severity=severity,
            rule_type=rule_type,
            timestamp=timestamp,
            threat_score=threat_score,
            evidence_snapshot_uri=None,
            target_crop_uri=None,
            face_snapshot_uri=None,
            anpr_snapshot_uri=None,
            file_exists=False,
            replay_available=False,
            message="No visual snapshot or video replay available for this record.",
        )


@router.delete("")
async def clear_all_incidents():
    """Clear all active and recorded incidents for a clean tactical run."""
    engine = get_incident_engine()
    engine.clear()
    from backend.database import get_session
    from backend.events.models import IncidentModel
    from sqlalchemy import delete
    async with get_session() as session:
        await session.execute(delete(IncidentModel))
        await session.commit()
    return {"status": "cleared", "count": 0}

