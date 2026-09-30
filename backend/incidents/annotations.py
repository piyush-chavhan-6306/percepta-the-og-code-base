"""
Border Intelligence Operator Incident Annotations & Escalation Log Module.
Allows human operators and duty officers to record timestamped tactical notes and disposition states.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from backend.events.schema import BaseEvent, EventType, SourceType
from backend.events.store import EventStore, get_event_store


class OperatorAnnotation(BaseModel):
    annotation_id: str = Field(default_factory=lambda: str(uuid4()))
    incident_id: str
    operator_callsign: str = "Duty Officer"
    note: str
    disposition: str = "INVESTIGATING"  # "INVESTIGATING", "VERIFIED_BREACH", "FALSE_POSITIVE", "QRF_DISPATCHED", "RESOLVED"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AddAnnotationRequest(BaseModel):
    operator_callsign: str = "Duty Officer"
    note: str = Field(..., min_length=1, description="Operator observation or action note")
    disposition: str = "INVESTIGATING"


class AnnotationListResponse(BaseModel):
    incident_id: str
    count: int
    annotations: List[OperatorAnnotation]


class AnnotationManager:
    """Manages recording and retrieval of human operator annotations in SQLite WAL store."""

    def __init__(self, store: Optional[EventStore] = None) -> None:
        self.store = store or get_event_store()

    async def add_annotation(
        self,
        incident_id: str,
        operator_callsign: str,
        note: str,
        disposition: str = "INVESTIGATING",
        camera_id: str = "COMMAND_POST",
    ) -> OperatorAnnotation:
        """Record an operator annotation event to SQLite WAL store."""
        ann = OperatorAnnotation(
            incident_id=incident_id,
            operator_callsign=operator_callsign,
            note=note,
            disposition=disposition,
        )

        payload_dict = {
            "annotation_id": ann.annotation_id,
            "operator_callsign": ann.operator_callsign,
            "note": ann.note,
            "disposition": ann.disposition,
            "timestamp": ann.timestamp.isoformat(),
            "subtype": "operator_annotation",
        }

        event = BaseEvent(
            event_type=EventType.INCIDENT,
            camera_id=camera_id,
            incident_id=incident_id,
            source=SourceType.SIMULATION,
            timestamp=ann.timestamp,
        )

        # Store using event_log model
        from backend.incidents.models import EventLogModel
        from backend.database import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            row = EventLogModel(
                event_id=str(event.event_id),
                event_type=event.event_type.value,
                timestamp=event.timestamp,
                camera_id=event.camera_id,
                incident_id=incident_id,
                confidence=1.0,
                source=event.source.value,
                payload=json.dumps(payload_dict),
            )
            session.add(row)
            await session.commit()

        return ann

    async def get_annotations(self, incident_id: str) -> List[OperatorAnnotation]:
        """Retrieve all operator annotations linked to an incident."""
        timeline = await self.store.get_incident_timeline(incident_id)
        annotations = []
        for e in timeline:
            raw_payload = e.get("payload", {})
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {}
            else:
                payload = raw_payload or {}

            if payload.get("subtype") == "operator_annotation":
                try:
                    t_str = payload.get("timestamp")
                    t = datetime.fromisoformat(t_str) if t_str else datetime.now(timezone.utc)
                    ann = OperatorAnnotation(
                        annotation_id=payload.get("annotation_id", str(uuid4())),
                        incident_id=incident_id,
                        operator_callsign=payload.get("operator_callsign", "Duty Officer"),
                        note=payload.get("note", ""),
                        disposition=payload.get("disposition", "INVESTIGATING"),
                        timestamp=t,
                    )
                    annotations.append(ann)
                except Exception:
                    continue

        return annotations


global_annotation_manager = AnnotationManager()


def get_annotation_manager() -> AnnotationManager:
    return global_annotation_manager
