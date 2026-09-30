"""
Border Intelligence Event Store Module.
Implements the Persist-Before-Publish contract, deterministic replay queries,
exponential backoff retry for SQLite write contention, and SQLite persistence using SQLAlchemy async.
"""
import asyncio
from datetime import datetime
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db_session, get_session_factory
from backend.events.bus import EventBus, get_event_bus
from backend.events.schema import BaseEvent, EventType, SourceType, SystemEvent
from backend.incidents.models import EventLogModel

logger = logging.getLogger(__name__)


class EventStore:
    """Durable Event Store with Persist-Before-Publish and deterministic replay."""

    def __init__(self, bus: Optional[EventBus] = None, max_retries: int = 5) -> None:
        self.bus = bus or get_event_bus()
        self.max_retries = max_retries
        self._stats_cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self._stats_cache_ttl = 2.0

    async def record_event(
        self,
        event: BaseEvent,
        session: Optional[AsyncSession] = None,
        publish: bool = True,
    ) -> int:
        """
        Durable Persist-Before-Publish:
        Persists single event to SQLite event_logs table and publishes to EventBus on commit.
        """
        seq_ids = await self.record_events_batch([event], session=session, publish=publish)
        return seq_ids[0] if seq_ids else 0

    async def record_events_batch(
        self,
        events: List[BaseEvent],
        session: Optional[AsyncSession] = None,
        publish: bool = True,
    ) -> List[int]:
        """
        Atomically persist a batch of events in a single SQLite WAL transaction.
        Enforces Persist-Before-Publish: publishes all events only after commit succeeds.
        """
        if not events:
            return []

        log_entries = [
            EventLogModel(
                event_id=str(ev.event_id),
                event_type=ev.event_type.value,
                timestamp=ev.timestamp,
                camera_id=ev.camera_id,
                track_id=ev.track_id,
                incident_id=ev.incident_id,
                confidence=ev.confidence,
                source=ev.source.value if hasattr(ev.source, "value") else str(ev.source),
                payload=ev.model_dump_json(),
            )
            for ev in events
        ]

        if session is not None:
            session.add_all(log_entries)
            await session.flush()
            seq_ids = [entry.seq_id for entry in log_entries]
            if publish:
                for ev in events:
                    await self.bus.publish(ev)
            return seq_ids

        factory = get_session_factory()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                async with factory() as local_session:
                    local_session.add_all(log_entries)
                    await local_session.commit()
                    seq_ids = [entry.seq_id for entry in log_entries]

                    if publish:
                        for ev in events:
                            await self.bus.publish(ev)
                    return seq_ids
            except (OperationalError, DBAPIError) as err:
                last_error = err
                backoff_ms = (2 ** attempt) * 10 + (attempt * 5)
                await asyncio.sleep(backoff_ms / 1000.0)
            except Exception as err:
                raise err

        logger.error(f"EventStore failed to persist event batch after {self.max_retries} attempts: {last_error}")
        raise last_error or RuntimeError("Failed to persist event batch due to database write contention")

    async def get_events(
        self,
        since: Optional[datetime] = None,
        after_seq: Optional[int] = None,
        camera_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        newest_first: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """
        Durable Event Replay API with deterministic ordering.

        Default ordering is ``timestamp ASC, seq_id ASC``: replay clients page
        forward with ``after_seq`` and need the oldest unseen rows first.

        ``newest_first=True`` flips both keys to DESC for callers that want "the
        last N events" instead. That distinction is not cosmetic -- the log grows
        without bound, so an ascending ``limit`` silently returns the oldest rows
        in the whole database. On a log with 169k rows, a caller asking for 500
        recent events was reading events from the very first run.
        """
        query = select(EventLogModel)

        if since is not None:
            query = query.where(EventLogModel.timestamp >= since)
        if after_seq is not None:
            query = query.where(EventLogModel.seq_id > after_seq)
        if camera_id is not None:
            query = query.where(EventLogModel.camera_id == camera_id)
        if event_type is not None:
            query = query.where(EventLogModel.event_type == event_type)

        # Deterministic tie-breaking sequence
        if newest_first:
            query = query.order_by(EventLogModel.timestamp.desc(), EventLogModel.seq_id.desc())
        else:
            query = query.order_by(EventLogModel.timestamp.asc(), EventLogModel.seq_id.asc())
        query = query.limit(limit)

        async def _exec(s: AsyncSession) -> List[Dict[str, Any]]:
            result = await s.execute(query)
            rows = result.scalars().all()
            return [
                {
                    "seq_id": row.seq_id,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "timestamp": row.timestamp.isoformat(),
                    "camera_id": row.camera_id,
                    "track_id": row.track_id,
                    "incident_id": row.incident_id,
                    "confidence": row.confidence,
                    "source": row.source,
                    "payload": row.payload,
                }
                for row in rows
            ]

        if session is not None:
            return await _exec(session)

        factory = get_session_factory()
        async with factory() as local_session:
            return await _exec(local_session)

    async def get_incident_timeline(
        self,
        incident_id: str,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve all events related to an incident ordered deterministically."""
        query = (
            select(EventLogModel)
            .where(EventLogModel.incident_id == incident_id)
            .order_by(EventLogModel.timestamp.asc(), EventLogModel.seq_id.asc())
        )

        async def _exec(s: AsyncSession) -> List[Dict[str, Any]]:
            result = await s.execute(query)
            rows = result.scalars().all()
            return [
                {
                    "seq_id": row.seq_id,
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "timestamp": row.timestamp.isoformat(),
                    "camera_id": row.camera_id,
                    "track_id": row.track_id,
                    "incident_id": row.incident_id,
                    "confidence": row.confidence,
                    "source": row.source,
                    "payload": row.payload,
                }
                for row in rows
            ]

        if session is not None:
            return await _exec(session)

        factory = get_session_factory()
        async with factory() as local_session:
            return await _exec(local_session)


    async def get_alerts(
        self,
        camera_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve stored alert events with filtering."""
        query = select(EventLogModel).where(EventLogModel.event_type == "ALERT")
        if camera_id is not None:
            query = query.where(EventLogModel.camera_id == camera_id)
        query = query.order_by(EventLogModel.timestamp.desc(), EventLogModel.seq_id.desc()).limit(limit)

        async def _exec(s: AsyncSession) -> List[Dict[str, Any]]:
            result = await s.execute(query)
            rows = result.scalars().all()
            alerts = []
            for row in rows:
                item = {
                    "seq_id": row.seq_id,
                    "event_id": row.event_id,
                    "timestamp": row.timestamp.isoformat(),
                    "camera_id": row.camera_id,
                    "track_id": row.track_id,
                    "incident_id": row.incident_id,
                    "confidence": row.confidence,
                    "source": row.source,
                    "payload": row.payload,
                    "message": None,
                    "severity": None,
                    "is_acknowledged": False,
                }
                if row.payload:
                    try:
                        p_data = json.loads(row.payload)
                        if isinstance(p_data, dict):
                            item["message"] = p_data.get("message")
                            item["severity"] = p_data.get("severity")
                    except Exception:
                        pass
                if severity:
                    sev_val = str(item.get("severity") or "").upper()
                    if sev_val != severity.upper():
                        continue
                alerts.append(item)
            return alerts

        if session is not None:
            return await _exec(session)

        factory = get_session_factory()
        async with factory() as local_session:
            return await _exec(local_session)

    async def get_system_stats(self, session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """
        Compute high-level event counts and database metrics.

        These three COUNT(*) scans grow with the event log (250k+ rows within an
        hour of live tracking). The dashboard polls this every second, and on
        SQLite each full scan contends with the perception worker's event writes
        -- the visible symptom was the MJPEG stream stalling for up to ~2 s every
        time the counts were recomputed. A short TTL cache collapses a burst of
        polls into one scan without making the numbers meaningfully stale.
        """
        from sqlalchemy import func

        now = time.perf_counter()
        cached = self._stats_cache
        if cached is not None and (now - cached[0]) < self._stats_cache_ttl:
            return cached[1]

        async def _exec(s: AsyncSession) -> Dict[str, Any]:
            total_events_query = select(func.count(EventLogModel.seq_id))
            alerts_query = select(func.count(EventLogModel.seq_id)).where(EventLogModel.event_type == "ALERT")
            cameras_query = select(func.count(func.distinct(EventLogModel.camera_id)))

            total_events = (await s.execute(total_events_query)).scalar() or 0
            total_alerts = (await s.execute(alerts_query)).scalar() or 0
            active_cameras = (await s.execute(cameras_query)).scalar() or 0

            return {
                "total_events": total_events,
                "total_alerts": total_alerts,
                "distinct_cameras_logged": active_cameras,
            }

        if session is not None:
            stats = await _exec(session)
        else:
            factory = get_session_factory()
            async with factory() as local_session:
                stats = await _exec(local_session)

        self._stats_cache = (now, stats)
        return stats

    async def acknowledge_alert(self, event_id: str, session: Optional[AsyncSession] = None) -> bool:
        """Mark an alert event or incident as acknowledged."""
        from sqlalchemy import update
        clean_id = str(event_id).strip()

        async def _exec(s: AsyncSession) -> bool:
            stmt = select(EventLogModel).where(EventLogModel.event_id == clean_id)
            res = await s.execute(stmt)
            row = res.scalar_one_or_none()
            if not row:
                return False
            # Update payload JSON to set is_acknowledged: True
            import json
            try:
                data = json.loads(row.payload)
                data["is_acknowledged"] = True
                row.payload = json.dumps(data)
                await s.commit()
                return True
            except Exception:
                return False

        if session is not None:
            return await _exec(session)

        factory = get_session_factory()
        async with factory() as local_session:
            return await _exec(local_session)

    async def get_incidents(
        self,
        camera_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve aggregated incidents list."""
        from sqlalchemy import func
        from backend.incidents.models import IncidentModel
        # Group by incident_id from EventLogModel, outer joining IncidentModel for persistent lifecycle
        query = (
            select(
                EventLogModel.incident_id,
                EventLogModel.camera_id,
                func.count(EventLogModel.seq_id).label("total_events"),
                func.min(EventLogModel.timestamp).label("first_seen"),
                func.max(EventLogModel.timestamp).label("last_seen"),
                func.max(IncidentModel.lifecycle).label("lifecycle"),
            )
            .outerjoin(IncidentModel, EventLogModel.incident_id == IncidentModel.incident_id)
            .where(EventLogModel.incident_id.isnot(None))
        )
        if camera_id is not None:
            query = query.where(EventLogModel.camera_id == camera_id)
        query = (
            query.group_by(EventLogModel.incident_id, EventLogModel.camera_id)
            .order_by(func.max(EventLogModel.timestamp).desc())
            .limit(limit)
        )

        async def _exec(s: AsyncSession) -> List[Dict[str, Any]]:
            res = await s.execute(query)
            rows = res.all()
            return [
                {
                    "incident_id": r.incident_id,
                    "camera_id": r.camera_id,
                    "total_events": r.total_events,
                    "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                    "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                    "status": "acknowledged" if r.lifecycle == "acknowledged" else ("resolved" if r.lifecycle == "resolved" else "opened"),
                    "lifecycle": r.lifecycle or "opened",
                }
                for r in rows
            ]

        if session is not None:
            return await _exec(session)

        factory = get_session_factory()
        async with factory() as local_session:
            return await _exec(local_session)

    async def get_evidence_records(
        self,
        camera_id: Optional[str] = None,
        evidence_type: Optional[str] = None,
        incident_id: Optional[str] = None,
        track_id: Optional[str] = None,
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve stored evidence events with optional filtering."""
        query = select(EventLogModel).where(EventLogModel.event_type == "EVIDENCE")
        if camera_id is not None:
            query = query.where(EventLogModel.camera_id == camera_id)
        if incident_id is not None:
            query = query.where(EventLogModel.incident_id == incident_id)
        if track_id is not None:
            query = query.where(EventLogModel.track_id == track_id)

        query = query.order_by(EventLogModel.timestamp.desc(), EventLogModel.seq_id.desc()).limit(limit)

        async def _exec(s: AsyncSession) -> List[Dict[str, Any]]:
            result = await s.execute(query)
            rows = result.scalars().all()
            records = []
            for row in rows:
                p_data = {}
                if row.payload:
                    try:
                        p_data = json.loads(row.payload)
                    except Exception:
                        pass

                ev_type = p_data.get("evidence_type") or "UNKNOWN"
                if evidence_type and ev_type.upper() != evidence_type.upper():
                    continue

                records.append({
                    "seq_id": row.seq_id,
                    "event_id": row.event_id,
                    "evidence_id": p_data.get("evidence_id") or row.event_id,
                    "evidence_type": ev_type,
                    "camera_id": row.camera_id,
                    "track_id": row.track_id,
                    "incident_id": row.incident_id or p_data.get("incident_id") or p_data.get("alert_id"),
                    "alert_id": p_data.get("alert_id"),
                    "timestamp": row.timestamp.isoformat(),
                    "file_path": p_data.get("file_path"),
                    "file_uri": p_data.get("file_uri"),
                    "sha256_hash": p_data.get("sha256_hash"),
                    "bounding_box": p_data.get("bounding_box"),
                    "object_class": p_data.get("object_class"),
                    "confidence": row.confidence,
                    "severity": p_data.get("severity", "LOW"),
                    "zone_id": p_data.get("zone_id"),
                    "zone_name": p_data.get("zone_name"),
                    "tripwire_id": p_data.get("tripwire_id"),
                    "tripwire_name": p_data.get("tripwire_name"),
                    "anpr_result": p_data.get("anpr_result"),
                    "face_metadata": p_data.get("face_metadata"),
                    "sharpness_score": p_data.get("sharpness_score"),
                })
            return records

        if session is not None:
            return await _exec(session)

        factory = get_session_factory()
        async with factory() as local_session:
            return await _exec(local_session)


global_event_store = EventStore()


def get_event_store() -> EventStore:
    return global_event_store
