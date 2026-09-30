"""
Border Intelligence Surveillance Event & Forensic Data Export REST API.
Provides endpoints to export filtered surveillance events in CSV and JSON formats.
"""
import csv
import io
import json
from typing import Optional
from fastapi import APIRouter, Query, Response

from backend.events.store import get_event_store

router = APIRouter(prefix="/api/events/export", tags=["Forensic Data Export"])


@router.get("")
async def export_events(
    format: str = Query("json", pattern="^(json|csv)$", description="Export format: 'json' or 'csv'"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type: ALERT, TRACKING, ZONE, SYSTEM"),
    limit: int = Query(500, ge=1, le=5000, description="Max events to export"),
):
    """
    Export historical surveillance events and forensic logs in structured JSON or CSV format.

    Exports the ``limit`` *most recent* matching events, then presents them
    oldest-first so the file reads forward in time. Without the recency
    selection an export from a long-running deployment returns the very first
    events ever recorded rather than the incident the operator is looking at.
    """
    store = get_event_store()
    events = await store.get_events(
        camera_id=camera_id,
        event_type=event_type,
        limit=limit,
        newest_first=True,
    )
    events.reverse()

    if format.lower() == "csv":
        output = io.StringIO()
        fieldnames = ["seq_id", "event_id", "timestamp", "camera_id", "track_id", "incident_id", "event_type", "confidence", "payload"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for e in events:
            writer.writerow({
                "seq_id": e.get("seq_id", ""),
                "event_id": e.get("event_id", ""),
                "timestamp": e.get("timestamp", ""),
                "camera_id": e.get("camera_id", ""),
                "track_id": e.get("track_id", "") or "",
                "incident_id": e.get("incident_id", "") or "",
                "event_type": e.get("event_type", ""),
                "confidence": e.get("confidence", "") or "",
                "payload": str(e.get("payload", "")),
            })

        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=surveillance_export_{camera_id or 'all'}.csv"},
        )

    return {
        "format": "json",
        "count": len(events),
        "camera_filter": camera_id,
        "event_type_filter": event_type,
        "events": events,
    }
