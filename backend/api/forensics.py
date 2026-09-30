"""
Border Intelligence Forensic Evidence REST API.
Provides endpoints for cryptographic verification of surveillance records and chain-of-custody audits.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.events.forensics import (
    EventVerificationResult,
    IntegrityAuditReport,
    get_forensics_engine,
)

router = APIRouter(prefix="/api/evidence", tags=["Forensic Evidence"])


@router.get("/verify/{event_id}", response_model=EventVerificationResult)
async def verify_event_authenticity(event_id: str) -> EventVerificationResult:
    """Cryptographically verify the authenticity and SHA-256 signature of a recorded surveillance event."""
    engine = get_forensics_engine()
    result = await engine.verify_event(event_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event record '{event_id}' not found in SQLite store",
        )
    return result


@router.get("/audit-integrity", response_model=IntegrityAuditReport)
async def audit_database_integrity(
    limit: int = Query(200, ge=10, le=1000, description="Number of recent records to audit"),
) -> IntegrityAuditReport:
    """
    Perform a complete cryptographic chain-of-custody audit on persisted surveillance event logs.
    Returns proof of non-tampering and root chain hash.
    """
    engine = get_forensics_engine()
    return await engine.audit_database_integrity(limit=limit)


@router.get("/records")
async def list_evidence_records(
    camera_id: Optional[str] = Query(None),
    evidence_type: Optional[str] = Query(None),
    incident_id: Optional[str] = Query(None),
    track_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Retrieve indexed forensic evidence records from persistent audit database.
    Supports filtering by camera, evidence type (PERSON, FACE, VEHICLE, ANPR, ZONE_VIOLATION, etc.),
    incident ID, and track ID.
    """
    from backend.events.store import get_event_store
    store = get_event_store()
    records = await store.get_evidence_records(
        camera_id=camera_id,
        evidence_type=evidence_type,
        incident_id=incident_id,
        track_id=track_id,
        limit=limit,
    )
    return {"count": len(records), "evidence": records}



@router.get("/snapshots/{incident_id}")
async def get_incident_snapshots(incident_id: str):
    """Retrieve list of visual JPEG evidence snapshots captured for an incident."""
    from backend.events.snapshots import get_snapshot_manager
    manager = get_snapshot_manager()
    snaps = manager.list_snapshots(incident_id)
    return {"incident_id": incident_id, "count": len(snaps), "snapshots": snaps}


@router.get("/snapshots/file/{filename}")
async def get_snapshot_image_file(filename: str):
    """Serve visual JPEG snapshot image file."""
    import os
    from fastapi.responses import FileResponse
    from backend.events.snapshots import get_snapshot_manager
    manager = get_snapshot_manager()
    file_path = manager.snapshot_dir / filename
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot file '{filename}' not found",
        )
    return FileResponse(str(file_path), media_type="image/jpeg")


@router.get("/timeline/{camera_id}")
async def get_camera_event_timeline(
    camera_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """
    Retrieve chronological events with deterministic timestamp offsets,
    frame indices, and snapshot URIs for video timeline seeking.
    """
    import json
    from backend.events.store import get_event_store
    store = get_event_store()
    alerts = await store.get_alerts(camera_id=camera_id, limit=limit)
    timeline_items = []

    for idx, a in enumerate(alerts):
        t_str = a.get("timestamp", "")
        payload_data = {}
        if a.get("payload"):
            try:
                payload_data = json.loads(a["payload"])
            except Exception:
                pass

        timeline_items.append({
            "seq_id": a["seq_id"],
            "event_id": a["event_id"],
            "camera_id": camera_id,
            "timestamp": t_str,
            "track_id": a.get("track_id"),
            "severity": a.get("severity", "CRITICAL"),
            "message": a.get("message", "Perimeter Alert"),
            "threat_score": payload_data.get("threat_score", 75),
            "threat_level": payload_data.get("threat_level", "HIGH"),
            "evidence_snapshot_uri": payload_data.get("evidence_snapshot_uri"),
            "face_snapshot_uri": payload_data.get("face_snapshot_uri"),
            "anpr_snapshot_uri": payload_data.get("anpr_snapshot_uri"),
            "best_frame_number": payload_data.get("best_frame_number", idx * 30 + 15),
            "timeline_offset_sec": payload_data.get("timeline_offset_sec", float(idx * 5)),
            "pre_roll_sec": 5.0,
            "post_roll_sec": 5.0,
        })

    return {
        "camera_id": camera_id,
        "count": len(timeline_items),
        "timeline": timeline_items,
    }


@router.get("/seek/{event_id}")
async def seek_event_playback(
    event_id: str,
    pre_sec: float = Query(5.0, ge=1.0, le=30.0),
    post_sec: float = Query(5.0, ge=1.0, le=30.0),
):
    """
    Retrieve exact video seeking parameters and replay metadata for a specific incident.
    """
    import json
    from backend.events.store import get_event_store
    store = get_event_store()
    raw = await store.get_event_by_id(event_id)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    payload_data = {}
    if raw.get("payload"):
        try:
            payload_data = json.loads(raw["payload"])
        except Exception:
            pass

    return {
        "event_id": event_id,
        "camera_id": raw["camera_id"],
        "timestamp": raw["timestamp"],
        "track_id": raw.get("track_id"),
        "severity": raw.get("severity", "CRITICAL"),
        "message": raw.get("message"),
        "threat_score": payload_data.get("threat_score"),
        "threat_reasons": payload_data.get("threat_reasons", []),
        "causal_chain": payload_data.get("causal_chain", []),
        "evidence_snapshot_uri": payload_data.get("evidence_snapshot_uri"),
        "face_snapshot_uri": payload_data.get("face_snapshot_uri"),
        "anpr_snapshot_uri": payload_data.get("anpr_snapshot_uri"),
        "best_frame_number": payload_data.get("best_frame_number"),
        "pre_roll_sec": pre_sec,
        "post_roll_sec": post_sec,
        "playback_url": f"/api/streaming/feed/{raw['camera_id']}",
    }


@router.get("/replay/{incident_id}")
async def get_evidence_replay(incident_id: str):
    """Retrieve verified replay/evidence playback metadata for an incident or event."""
    from backend.api.incidents import get_incident_replay_data
    return await get_incident_replay_data(incident_id)
