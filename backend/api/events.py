"""
Border Intelligence Event Replay API Module.
Provides durable query access to historical events from SQLite with deterministic ordering.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db_session
from backend.events.store import EventStore, get_event_store

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
async def get_events(
    since: Optional[datetime] = Query(None, description="ISO-8601 timestamp to filter events >= timestamp"),
    after_seq: Optional[int] = Query(None, description="Return events strictly with seq_id > after_seq"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    event_type: Optional[str] = Query(None, description="Filter by EventType"),
    limit: int = Query(100, ge=1, le=1000, description="Max events to return"),
    session: AsyncSession = Depends(get_db_session),
    event_store: EventStore = Depends(get_event_store),
) -> Dict[str, Any]:
    """
    Durable Event Replay endpoint:
    Returns events ordered by timestamp ASC, seq_id ASC.
    Used by dashboard after reconnection to catch up on missed events.
    """
    events = await event_store.get_events(
        since=since,
        after_seq=after_seq,
        camera_id=camera_id,
        event_type=event_type,
        limit=limit,
        session=session,
    )
    return {
        "count": len(events),
        "events": events,
    }


@router.get("/incident/{incident_id}")
async def get_incident_timeline(
    incident_id: str,
    session: AsyncSession = Depends(get_db_session),
    event_store: EventStore = Depends(get_event_store),
) -> Dict[str, Any]:
    """Retrieve full chronological timeline of events for an incident."""
    timeline = await event_store.get_incident_timeline(incident_id=incident_id, session=session)
    return {
        "incident_id": incident_id,
        "count": len(timeline),
        "timeline": timeline,
    }
