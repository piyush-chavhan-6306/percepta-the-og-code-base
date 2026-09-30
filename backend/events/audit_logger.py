"""
Border Intelligence Administrative Audit Log Module.
Records system administrative actions, configuration switches, and operator commands in SQLite WAL store.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from backend.events.schema import BaseEvent, EventType, SourceType
from backend.events.store import EventStore, get_event_store


class AuditLogEntry(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    action: str  # "CAMERA_REGISTER", "PROFILE_SWITCH", "ZONE_CREATE", "ALERT_ACK", "DEMO_RESET"
    actor: str = "SYSTEM_ADMIN"
    details: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLogger:
    """Logs administrative and configuration events to durable SQLite WAL storage."""

    def __init__(self, store: Optional[EventStore] = None) -> None:
        self.store = store or get_event_store()

    async def log_action(
        self,
        action: str,
        details: Dict[str, Any],
        actor: str = "SYSTEM_ADMIN",
    ) -> AuditLogEntry:
        """Record an administrative action to SQLite WAL store."""
        entry = AuditLogEntry(
            action=action,
            actor=actor,
            details=details,
        )

        payload_dict = {
            "audit_id": entry.audit_id,
            "action": entry.action,
            "actor": entry.actor,
            "details": entry.details,
            "timestamp": entry.timestamp.isoformat(),
            "subtype": "admin_audit_log",
        }

        from backend.incidents.models import EventLogModel
        from backend.database import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            row = EventLogModel(
                event_id=entry.audit_id,
                event_type="SYSTEM",
                timestamp=entry.timestamp,
                camera_id="SYSTEM_CORE",
                confidence=1.0,
                source="system",
                payload=json.dumps(payload_dict),
            )
            session.add(row)
            await session.commit()

        return entry

    async def get_audit_logs(self, limit: int = 100) -> List[AuditLogEntry]:
        """Retrieve recent administrative audit log entries."""
        events = await self.store.get_events(event_type="SYSTEM", limit=limit * 2, newest_first=True)
        logs = []
        for e in events:
            raw_payload = e.get("payload", {})
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {}
            else:
                payload = raw_payload or {}

            if payload.get("subtype") == "admin_audit_log":
                try:
                    t_str = payload.get("timestamp")
                    t = datetime.fromisoformat(t_str) if t_str else datetime.now(timezone.utc)
                    logs.append(
                        AuditLogEntry(
                            audit_id=payload.get("audit_id", str(uuid4())),
                            action=payload.get("action", "ADMIN_ACTION"),
                            actor=payload.get("actor", "SYSTEM_ADMIN"),
                            details=payload.get("details", {}),
                            timestamp=t,
                        )
                    )
                except Exception:
                    continue

        return logs[:limit]


global_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    return global_audit_logger
