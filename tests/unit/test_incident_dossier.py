"""
Unit and Integration Tests for Incident Forensic Dossier & Situation Report (SitRep) Generator.
"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.schema import AlertEvent, SourceType, TrackingEvent, ZoneEvent
from backend.events.store import get_event_store
from backend.incidents.dossier import get_dossier_generator
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_incident_dossier_compilation_and_rest_api():
    store = get_event_store()
    inc_id = f"INC-DOSSIER-{uuid.uuid4().hex[:8]}"

    # Create sequence of events for this incident
    t1 = TrackingEvent(
        camera_id="cam_dossier_test",
        track_id="77",
        incident_id=inc_id,
        lifecycle="created",
        position=[100.0, 150.0],
        velocity=[2.0, 3.0],
        object_class="person",
        speed=3.6,
        direction=45.0,
        source=SourceType.SIMULATION,
    )
    t2 = TrackingEvent(
        camera_id="cam_dossier_test",
        track_id="77",
        incident_id=inc_id,
        lifecycle="updated",
        position=[250.0, 300.0],
        velocity=[3.0, 3.0],
        object_class="person",
        speed=4.2,
        direction=45.0,
        source=SourceType.SIMULATION,
    )
    z1 = ZoneEvent(
        camera_id="cam_dossier_test",
        track_id="77",
        incident_id=inc_id,
        zone_id="ZONE_PERIMETER",
        zone_name="Sector Charlie Buffer Zone",
        zone_severity="restricted",
        transition="entered",
        source=SourceType.SIMULATION,
    )
    a1 = AlertEvent(
        camera_id="cam_dossier_test",
        track_id="77",
        incident_id=inc_id,
        severity="RESTRICTED",
        message="SECURITY ALERT: Track 77 (person) entered restricted zone 'Sector Charlie Buffer Zone'",
        source=SourceType.SIMULATION,
    )

    await store.record_event(t1)
    await store.record_event(t2)
    await store.record_event(z1)
    await store.record_event(a1)

    # 1. Direct generator verification
    gen = get_dossier_generator()
    dossier = await gen.generate_dossier(inc_id)
    assert dossier is not None
    assert dossier.incident_id == inc_id
    assert dossier.camera_id == "cam_dossier_test"
    assert dossier.total_events_logged == 4
    assert dossier.motion_summary is not None
    assert dossier.motion_summary.target_class == "person"
    assert dossier.motion_summary.total_trajectory_points == 2
    assert len(dossier.infractions) >= 1
    assert "TACTICAL SITUATION REPORT" in dossier.tactical_sitrep

    # 2. REST API verification
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/api/incidents/{inc_id}/dossier")
        assert r.status_code == 200
        data = r.json()
        assert data["incident_id"] == inc_id
        assert len(data["forensic_hash"]) == 64
        assert "tactical_sitrep" in data
