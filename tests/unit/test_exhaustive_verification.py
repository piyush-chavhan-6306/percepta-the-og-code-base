"""
Exhaustive Read-Only Backend Verification Suite for Border Intelligence.
Covers all edge cases, invalid inputs, concurrency, restart, failure modes,
SQL injection rejection, credential leakage prevention, and full route enumeration.
"""
import asyncio
import json
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import get_settings
from backend.database import close_db, get_session_factory, init_db
from backend.events.schema import AlertEvent, BaseEvent, EventType, SourceType
from backend.events.store import get_event_store
from backend.ingestion.camera_manager import get_camera_manager
from backend.ingestion.simulation_adapter import SimulationAdapter
from backend.main import create_app
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneSeverity, get_zone_monitor


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_route_enumeration_and_invalid_inputs():
    """Verify all REST routes respond correctly to valid and invalid inputs."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Root & Health
        r = await client.get("/")
        assert r.status_code == 200
        r = await client.get("/api/health")
        assert r.status_code == 200
        r = await client.get("/api/readiness")
        assert r.status_code == 200

        # 2. System endpoints
        r = await client.get("/api/system/status")
        assert r.status_code == 200
        r = await client.get("/api/system/metrics")
        assert r.status_code == 200
        r = await client.get("/api/system/coverage-report")
        assert r.status_code == 200
        r = await client.get("/api/system/profiles")
        assert r.status_code == 200
        r = await client.get("/api/system/audit-logs")
        assert r.status_code == 200
        r = await client.get("/api/system/db-diagnostics")
        assert r.status_code == 200

        # 3. Threat and Forensics
        r = await client.get("/api/threat/level")
        assert r.status_code == 200
        r = await client.get("/api/evidence/audit-integrity?limit=50")
        assert r.status_code == 200
        r = await client.get("/api/evidence/verify/NON_EXISTENT_ID")
        assert r.status_code == 404

        # 4. Cameras & Diagnostics
        r = await client.get("/api/cameras")
        assert r.status_code == 200
        r = await client.get("/api/cameras/NON_EXISTENT_CAM")
        assert r.status_code == 404
        r = await client.get("/api/cameras/NON_EXISTENT_CAM/diagnostics")
        assert r.status_code == 404
        r = await client.get("/api/cameras/NON_EXISTENT_CAM/heatmap")
        assert r.status_code == 200
        assert "density_matrix" in r.json()

        # 5. Alerts & Incidents
        r = await client.get("/api/alerts")
        assert r.status_code == 200
        r = await client.get("/api/incidents")
        assert r.status_code == 200
        r = await client.get("/api/incidents/NON_EXISTENT_INC/timeline")
        assert r.status_code == 404
        r = await client.get("/api/incidents/NON_EXISTENT_INC/dossier")
        assert r.status_code == 404
        r = await client.get("/api/incidents/NON_EXISTENT_INC/notes")
        assert r.status_code == 200

        # 6. Zones & Templates
        r = await client.get("/api/zones")
        assert r.status_code == 200
        r = await client.get("/api/zones/templates")
        assert r.status_code == 200
        r = await client.delete("/api/zones/NON_EXISTENT_ZONE")
        assert r.status_code == 404

        # 7. Multi-Modal Sensors
        r = await client.get("/api/sensors/status")
        assert r.status_code == 200
        r = await client.post("/api/sensors/ingest", json={"invalid": "payload"})
        assert r.status_code == 422  # Pydantic validation error

        # 8. Event Export
        r = await client.get("/api/events/export?format=json")
        assert r.status_code == 200
        r = await client.get("/api/events/export?format=csv")
        assert r.status_code == 200
        r = await client.get("/api/events/export?format=unsupported_format")
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_concurrency_and_stress_persistence():
    """Verify database handles 50 concurrent writes without deadlocks or WAL corruption."""
    store = get_event_store()

    async def record_worker(worker_id: int):
        event = AlertEvent(
            camera_id="cam_stress_test",
            track_id=str(worker_id),
            incident_id=f"INC_STRESS_{worker_id}",
            severity="WARNING",
            message=f"Stress test message from worker {worker_id}",
            source=SourceType.SIMULATION,
        )
        return await store.record_event(event)

    try:
        tasks = [record_worker(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 50
        assert all(isinstance(r, int) and r > 0 for r in results)
    finally:
        # This suite shares one SQLite file with every other test, and these 50
        # rows carry track_ids "0".."49". The assistant's get_track_events()
        # matches on track_id alone (IDs are camera-local, so it cannot scope by
        # camera for a bare "Track 17" question), which means the leftover
        # track_id="17" alert here silently shadows the seeded fixture in
        # test_intelligence_assistant -- this file sorts first, so its rows are
        # already committed by the time those tests run. Clean up after
        # ourselves rather than leaking state across modules.
        from sqlalchemy import text
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("DELETE FROM event_logs WHERE camera_id = 'cam_stress_test';"))
            await session.commit()


@pytest.mark.asyncio
async def test_database_restart_and_persistence_recovery():
    """Verify database recovers and maintains historical records across restart/reconnection."""
    store = get_event_store()
    test_id = f"RECOVERY_TEST_{uuid.uuid4().hex[:6]}"

    event = AlertEvent(
        camera_id="cam_recovery",
        track_id="999",
        incident_id=test_id,
        severity="CRITICAL",
        message="Persistence survival verification event",
        source=SourceType.SIMULATION,
    )
    await store.record_event(event)

    # Simulate database close and re-initialization
    await close_db()
    await init_db()

    # Re-fetch event after restart
    recovered_store = get_event_store()
    timeline = await recovered_store.get_incident_timeline(test_id)
    assert len(timeline) >= 1
    assert timeline[0]["incident_id"] == test_id


@pytest.mark.asyncio
async def test_credential_leakage_and_security_refusal():
    """Verify RTSP passwords are never leaked and injection attempts are rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register camera with sensitive RTSP credentials
        r = await client.post(
            "/api/cameras/register",
            json={
                "camera_id": "CAM_RTSP_SECRET",
                "source_type": "rtsp",
                "source_url": "rtsp://admin:P@ssw0rd123!@192.168.1.100:554/live",
                "name": "Secret Perimeter Gate",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "P@ssw0rd123!" not in json.dumps(data)
        assert data["camera_id"] == "CAM_RTSP_SECRET"

        # 2. Refuse SQL Injection queries in intelligence assistant
        r_ai = await client.post(
            "/api/intelligence/query",
            json={"query": "SELECT * FROM events WHERE 1=1; DROP TABLE events; --"},
        )
        assert r_ai.status_code == 200
        ai_resp = r_ai.json()
        assert ai_resp["status"] in ["invalid_query", "unsupported", "refused"]
        interp = ai_resp["interpretation"].lower()
        assert "refusal" in interp or "forbidden" in interp or "cannot" in interp or "unsupported" in interp


@pytest.mark.asyncio
async def test_event_ordering_and_deterministic_sequence():
    """Verify monotonic sequence ID incrementation and strict chronological sorting."""
    store = get_event_store()
    cam = f"CAM_SEQ_{uuid.uuid4().hex[:6]}"

    e1 = AlertEvent(camera_id=cam, track_id="1", severity="INFO", message="First event", source=SourceType.SIMULATION)
    e2 = AlertEvent(camera_id=cam, track_id="2", severity="INFO", message="Second event", source=SourceType.SIMULATION)
    e3 = AlertEvent(camera_id=cam, track_id="3", severity="INFO", message="Third event", source=SourceType.SIMULATION)

    res1 = await store.record_event(e1)
    res2 = await store.record_event(e2)
    res3 = await store.record_event(e3)

    assert res1 < res2 < res3

    events = await store.get_events(camera_id=cam, limit=10)
    seqs = [e["seq_id"] for e in events]
    # Replay sorting in ascending order
    assert seqs == sorted(seqs)
