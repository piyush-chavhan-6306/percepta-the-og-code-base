"""
Unit tests for Security Zones and Alert Acknowledgement REST APIs.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.schema import AlertEvent, SourceType
from backend.events.store import get_event_store
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_zones_and_boundaries_crud_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a Polygon Zone
        r_zone = await client.post(
            "/api/zones",
            json={
                "zone_id": "ZONE_TEST_NORTH",
                "name": "North Sector Buffer",
                "polygon": [[100.0, 100.0], [500.0, 100.0], [500.0, 500.0], [100.0, 500.0]],
                "severity": "restricted",
                "loitering_threshold_seconds": 3.0,
            },
        )
        assert r_zone.status_code == 200
        z_data = r_zone.json()
        assert z_data["zone_id"] == "ZONE_TEST_NORTH"
        assert z_data["severity"] == "restricted"

        # 2. Create a Virtual Boundary
        r_bound = await client.post(
            "/api/zones/boundary",
            json={
                "boundary_id": "LINE_TEST_FENCE",
                "name": "Fence Line 01",
                "pt1": [200.0, 300.0],
                "pt2": [800.0, 300.0],
                "severity": "critical",
            },
        )
        assert r_bound.status_code == 200
        b_data = r_bound.json()
        assert b_data["boundary_id"] == "LINE_TEST_FENCE"
        assert b_data["severity"] == "critical"

        # 3. List Zones & Boundaries
        r_list = await client.get("/api/zones")
        assert r_list.status_code == 200
        all_zones = r_list.json()
        assert any(z["zone_id"] == "ZONE_TEST_NORTH" for z in all_zones["zones"])
        assert any(b["boundary_id"] == "LINE_TEST_FENCE" for b in all_zones["boundaries"])

        # 4. Delete Zone
        r_del_z = await client.delete("/api/zones/ZONE_TEST_NORTH")
        assert r_del_z.status_code == 200
        assert r_del_z.json()["status"] == "deleted"

        # 5. Delete Boundary
        r_del_b = await client.delete("/api/zones/LINE_TEST_FENCE")
        assert r_del_b.status_code == 200
        assert r_del_b.json()["status"] == "deleted"

        # 6. Delete Non-existent returns 404
        r_del_404 = await client.delete("/api/zones/NON_EXISTENT_ID")
        assert r_del_404.status_code == 404


@pytest.mark.asyncio
async def test_alert_acknowledgement_and_incidents_list_api():
    app = create_app()
    store = get_event_store()

    # Record an alert
    alert = AlertEvent(
        camera_id="cam_ack_test",
        track_id="99",
        incident_id="INC-ACK-001",
        severity="WARNING",
        message="Suspicious entity near fence line",
        source=SourceType.SIMULATION,
    )
    await store.record_event(alert)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Acknowledge Alert
        r_ack = await client.post(f"/api/alerts/{alert.event_id}/acknowledge")
        assert r_ack.status_code == 200
        assert r_ack.json()["status"] == "acknowledged"

        # 2. List Incidents
        r_inc = await client.get("/api/incidents")
        assert r_inc.status_code == 200
        data = r_inc.json()
        assert data["count"] >= 1
        assert any(inc["incident_id"] == "INC-ACK-001" for inc in data["incidents"])
