"""
Border Intelligence ORM Models.
Defines database persistence models for Event Logs, Incidents, and Alerts.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class EventLogModel(Base):
    """
    Durable Event Log table.
    seq_id provides monotonically increasing sequence for deterministic tie-breaking.
    event_id provides public UUID identifier.
    """
    __tablename__ = "event_logs"

    seq_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    track_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="video_file")
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # Complete JSON serialization

    __table_args__ = (
        Index("idx_events_timestamp_seq", "timestamp", "seq_id"),
        Index("idx_events_incident_seq", "incident_id", "seq_id"),
        Index("idx_events_cam_time_seq", "camera_id", "timestamp", "seq_id"),
        Index("idx_events_cam_type_time_seq", "camera_id", "event_type", "timestamp", "seq_id"),
    )


class IncidentModel(Base):
    """Incident aggregation model."""
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="LOW", index=True)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False, default="opened", index=True)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    primary_track_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class AlertModel(Base):
    """Alert entity model."""
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    track_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
