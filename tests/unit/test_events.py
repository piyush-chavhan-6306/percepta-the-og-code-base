"""
Phase 1 Unit & Contract Tests:
1. Schema serialization & deserialization across all event types.
2. EventBus pub/sub & subscriber exception isolation.
3. Persist-Before-Publish durable boundary verification.
4. Deterministic replay ordering (timestamp ASC, seq_id ASC).
5. REST API verification for health and replay endpoints.
"""
from datetime import datetime, timezone
import json
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from backend.database import close_db, init_db
from backend.events.bus import EventBus
from backend.events.schema import (
    AlertEvent,
    BaseEvent,
    CameraHandoffEvent,
    DetectionEvent,
    EvidenceEvent,
    EventType,
    IncidentEvent,
    RiskEvent,
    SourceType,
    SystemEvent,
    TrackingEvent,
    ZoneEvent,
)
from backend.events.store import EventStore
from backend.main import create_app


@pytest_asyncio.fixture
async def test_db():
    """Fixture to set up an in-memory or isolated test database."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    await init_db(database_url=test_db_url)
    yield
    await close_db()


@pytest.mark.asyncio
async def test_all_event_schemas_serialize_deserialize():
    """Verify all event types serialize and deserialize with full type fidelity."""
    now = datetime.now(timezone.utc)

    # 1. DetectionEvent
    det = DetectionEvent(
        camera_id="CAM-01",
        object_class="person",
        bounding_box=[100.0, 150.0, 200.0, 350.0],
        frame_number=42,
        confidence=0.95,
        source=SourceType.VIDEO_FILE,
        timestamp=now,
    )
    det_json = det.model_dump_json()
    det_restored = DetectionEvent.model_validate_json(det_json)
    assert det_restored.object_class == "person"
    assert det_restored.bounding_box == [100.0, 150.0, 200.0, 350.0]
    assert det_restored.event_type == EventType.DETECTION

    # 2. TrackingEvent
    trk = TrackingEvent(
        camera_id="CAM-01",
        track_id="TRK-001",
        lifecycle="created",
        position=[150.0, 250.0],
        velocity=[1.5, -0.5],
        timestamp=now,
    )
    trk_json = trk.model_dump_json()
    trk_restored = TrackingEvent.model_validate_json(trk_json)
    assert trk_restored.track_id == "TRK-001"
    assert trk_restored.velocity == [1.5, -0.5]

    # 3. ZoneEvent
    zone = ZoneEvent(
        camera_id="CAM-01",
        track_id="TRK-001",
        zone_id="ZONE-RESTRICTED-A",
        zone_name="Buffer Strip Alpha",
        zone_severity="restricted",
        transition="entered",
        timestamp=now,
    )
    zone_json = zone.model_dump_json()
    zone_restored = ZoneEvent.model_validate_json(zone_json)
    assert zone_restored.transition == "entered"
    assert zone_restored.zone_severity == "restricted"

    # 4. RiskEvent (Explainable reasons)
    risk = RiskEvent(
        camera_id="CAM-01",
        track_id="TRK-001",
        risk_level="high",
        reasons=["Restricted zone entry", "Approaching boundary perimeter"],
        timestamp=now,
    )
    risk_json = risk.model_dump_json()
    risk_restored = RiskEvent.model_validate_json(risk_json)
    assert "Restricted zone entry" in risk_restored.reasons
    assert risk_restored.risk_level == "high"

    # 5. EvidenceEvent
    ev = EvidenceEvent(
        camera_id="CAM-01",
        track_id="TRK-001",
        incident_id="INC-101",
        frame_path="storage/evidence/CAM-01/frame_42.jpg",
        frame_number=42,
        trigger_reason="Restricted zone crossing",
        frame_type="trigger",
        timestamp=now,
    )
    ev_json = ev.model_dump_json()
    ev_restored = EvidenceEvent.model_validate_json(ev_json)
    assert ev_restored.frame_type == "trigger"

    # 6. AlertEvent
    alt = AlertEvent(
        camera_id="CAM-01",
        track_id="TRK-001",
        incident_id="INC-101",
        severity="HIGH",
        message="Unauthorized entity in restricted zone Buffer Strip Alpha",
        timestamp=now,
    )
    alt_json = alt.model_dump_json()
    alt_restored = AlertEvent.model_validate_json(alt_json)
    assert alt_restored.severity == "HIGH"
    assert not alt_restored.is_acknowledged

    # 7. IncidentEvent
    inc = IncidentEvent(
        camera_id="CAM-01",
        incident_id="INC-101",
        lifecycle="opened",
        event_ids=[det.event_id, trk.event_id, zone.event_id],
        timestamp=now,
    )
    inc_json = inc.model_dump_json()
    inc_restored = IncidentEvent.model_validate_json(inc_json)
    assert len(inc_restored.event_ids) == 3

    # 8. SystemEvent (Failure / Degradation)
    sys_event = SystemEvent(
        camera_id="CAM-02",
        source=SourceType.VIDEO_FILE,
        subtype="camera_unavailable",
        details="Video stream failed to open file",
        timestamp=now,
    )
    sys_json = sys_event.model_dump_json()
    sys_restored = SystemEvent.model_validate_json(sys_json)
    assert sys_restored.subtype == "camera_unavailable"
    assert sys_restored.source == SourceType.VIDEO_FILE

    # 9. CameraHandoffEvent (P1)
    handoff = CameraHandoffEvent(
        camera_id="CAM-01",
        from_camera_id="CAM-01",
        to_camera_id="CAM-02",
        track_id="TRK-001",
        association_score=0.88,
        association_status="likely",
        timestamp=now,
    )
    handoff_json = handoff.model_dump_json()
    handoff_restored = CameraHandoffEvent.model_validate_json(handoff_json)
    assert handoff_restored.association_score == 0.88
    assert handoff_restored.association_status == "likely"


@pytest.mark.asyncio
async def test_event_bus_pub_sub_and_isolation():
    """Verify EventBus typed subscriptions and subscriber error isolation."""
    bus = EventBus()
    received_detections = []
    received_all = []

    async def on_detection(event: BaseEvent):
        received_detections.append(event)

    async def on_wildcard(event: BaseEvent):
        received_all.append(event)

    async def failing_subscriber(event: BaseEvent):
        raise RuntimeError("Subscriber crash")

    await bus.subscribe(on_detection, event_type=EventType.DETECTION)
    await bus.subscribe(failing_subscriber, event_type=EventType.DETECTION)
    await bus.subscribe(on_wildcard, event_type=None)

    det = DetectionEvent(
        camera_id="CAM-01",
        object_class="person",
        bounding_box=[10, 20, 30, 40],
        frame_number=1,
    )
    sys_ev = SystemEvent(
        camera_id="CAM-01",
        subtype="pipeline_degraded",
        details="Test",
    )

    # Publish DetectionEvent: both subscribers should receive despite failing subscriber
    await bus.publish(det)
    assert len(received_detections) == 1
    assert len(received_all) == 1

    # Publish SystemEvent: only wildcard subscriber receives
    await bus.publish(sys_ev)
    assert len(received_detections) == 1
    assert len(received_all) == 2


@pytest.mark.asyncio
async def test_persist_before_publish_contract(test_db):
    """
    Verify Persist-Before-Publish:
    1. Committed events are published to EventBus.
    2. Failed DB commits do NOT publish to EventBus.
    """
    bus = EventBus()
    store = EventStore(bus=bus)
    published_events = []

    async def subscriber(event: BaseEvent):
        published_events.append(event)

    await bus.subscribe(subscriber)

    # 1. Normal successful persist -> publish
    det = DetectionEvent(
        camera_id="CAM-01",
        object_class="person",
        bounding_box=[10, 20, 30, 40],
        frame_number=100,
    )
    seq_id = await store.record_event(det)
    assert seq_id > 0
    assert len(published_events) == 1
    assert published_events[0].event_id == det.event_id

    # 2. Database failure test: Attempting to insert an event with duplicate event_id
    # should raise an IntegrityError and NOT publish to the event bus.
    dup_event = DetectionEvent(
        event_id=det.event_id,  # Duplicate event_id triggers unique constraint violation
        camera_id="CAM-01",
        object_class="person",
        bounding_box=[10, 20, 30, 40],
        frame_number=101,
    )

    with pytest.raises(Exception):
        await store.record_event(dup_event)

    # Bus should still only have the 1 successful event
    assert len(published_events) == 1


@pytest.mark.asyncio
async def test_deterministic_replay_ordering_with_tie_breaker(test_db):
    """
    Verify replay ordering uses deterministic tie-breaking (timestamp ASC, seq_id ASC).
    """
    bus = EventBus()
    store = EventStore(bus=bus)
    fixed_time = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)

    # Insert 5 events with identical timestamp
    event_ids = []
    for i in range(5):
        event = DetectionEvent(
            camera_id="CAM-01",
            object_class="person",
            bounding_box=[i, i, i + 10, i + 10],
            frame_number=i,
            timestamp=fixed_time,
        )
        seq = await store.record_event(event)
        event_ids.append((seq, str(event.event_id)))

    # Fetch all events
    replay = await store.get_events(since=fixed_time)
    assert len(replay) == 5

    # Check that returned sequence IDs are strictly monotonically increasing
    returned_seqs = [item["seq_id"] for item in replay]
    assert returned_seqs == sorted(returned_seqs)

    # Check after_seq filter for incremental pagination/replay
    after_seq_2 = await store.get_events(after_seq=returned_seqs[1])
    assert len(after_seq_2) == 3
    assert after_seq_2[0]["seq_id"] == returned_seqs[2]


@pytest.mark.asyncio
async def test_fastapi_health_and_replay_endpoints(test_db):
    """Verify REST API health and event replay endpoints via AsyncClient."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"

        # 2. Insert event via store and query replay endpoint
        store = EventStore()
        alert = AlertEvent(
            camera_id="CAM-01",
            incident_id="INC-DEMO-01",
            severity="CRITICAL",
            message="Boundary fence breached",
        )
        await store.record_event(alert)

        # 3. GET /api/events
        res_events = await client.get("/api/events")
        assert res_events.status_code == 200
        events_data = res_events.json()
        assert events_data["count"] >= 1
        assert any(e["event_id"] == str(alert.event_id) for e in events_data["events"])

        # 4. GET /api/events/incident/{id}
        res_inc = await client.get(f"/api/events/incident/{alert.incident_id}")
        assert res_inc.status_code == 200
        inc_data = res_inc.json()
        assert inc_data["incident_id"] == "INC-DEMO-01"
        assert len(inc_data["timeline"]) == 1
