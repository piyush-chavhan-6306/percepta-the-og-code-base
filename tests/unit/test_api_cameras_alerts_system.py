"""
Unit tests for Camera, Alerts, Incidents, and System Observability REST APIs.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.schema import AlertEvent, SourceType
from backend.events.store import get_event_store
from backend.ingestion.camera_manager import get_camera_manager
from backend.ingestion.simulation_adapter import SimulationAdapter
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_api_cameras_endpoints():
    app = create_app()
    manager = get_camera_manager()
    adapter = SimulationAdapter(camera_id="cam_api_test", width=640, height=480)
    manager.register_camera("cam_api_test", adapter, name="API Test Camera")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List cameras
        r_list = await client.get("/api/cameras")
        assert r_list.status_code == 200
        data = r_list.json()
        assert data["count"] >= 1
        cam_ids = [c["camera_id"] for c in data["cameras"]]
        assert "cam_api_test" in cam_ids

        # 2. Get single camera
        r_single = await client.get("/api/cameras/cam_api_test")
        assert r_single.status_code == 200
        assert r_single.json()["camera_id"] == "cam_api_test"

        # 3. Start camera
        r_start = await client.post("/api/cameras/cam_api_test/start")
        assert r_start.status_code == 200
        assert r_start.json()["status"] == "started"

        # 4. Stop camera
        r_stop = await client.post("/api/cameras/cam_api_test/stop")
        assert r_stop.status_code == 200
        assert r_stop.json()["status"] == "stopped"

        # 5. Delete camera
        r_del = await client.delete("/api/cameras/cam_api_test")
        assert r_del.status_code == 200
        assert r_del.json()["status"] == "deregistered"
        assert manager.get_camera("cam_api_test") is None

        # 6. Non-existent camera returns 404
        r_404 = await client.get("/api/cameras/non_existent_camera_id")
        assert r_404.status_code == 404

        # 7. Deleting non-existent camera returns 404
        r_del_404 = await client.delete("/api/cameras/non_existent_camera_id")
        assert r_del_404.status_code == 404


@pytest.mark.asyncio
async def test_api_alerts_and_incidents_endpoints():
    app = create_app()
    store = get_event_store()

    # Record an alert event
    alert = AlertEvent(
        camera_id="cam_alert_api",
        track_id="42",
        incident_id="INC-ALERT-99",
        severity="CRITICAL",
        message="Critical boundary breach detected",
        source=SourceType.SIMULATION,
    )
    await store.record_event(alert)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Query alerts
        r_alerts = await client.get("/api/alerts?camera_id=cam_alert_api")
        assert r_alerts.status_code == 200
        data = r_alerts.json()
        assert data["count"] >= 1
        assert data["alerts"][0]["camera_id"] == "cam_alert_api"

        # 2. Query incident timeline
        r_inc = await client.get("/api/incidents/INC-ALERT-99")
        assert r_inc.status_code == 200
        inc_data = r_inc.json()
        assert inc_data["incident_id"] == "INC-ALERT-99"
        assert inc_data["count"] >= 1


@pytest.mark.asyncio
async def test_api_system_status_and_metrics():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. System status
        r_status = await client.get("/api/system/status")
        assert r_status.status_code == 200
        st = r_status.json()
        assert st["status"] == "online"
        assert "database" in st
        assert "total_cameras" in st

        # 2. System metrics
        r_metrics = await client.get("/api/system/metrics")
        assert r_metrics.status_code == 200
        met = r_metrics.json()
        assert "telemetry" in met
        assert "total_events" in met["telemetry"]


@pytest.mark.asyncio
async def test_api_cameras_register_deregister_reconnect():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a simulation camera
        r_reg = await client.post(
            "/api/cameras/register",
            json={
                "camera_id": "cam_dynamic_01",
                "name": "Dynamic North Fence",
                "source_type": "simulation",
                "location_label": "Northern Perimeter",
                "fps": 20.0,
            },
        )
        assert r_reg.status_code == 200
        assert r_reg.json()["camera_id"] == "cam_dynamic_01"

        # 2. Reconnect camera
        r_rec = await client.post("/api/cameras/cam_dynamic_01/reconnect")
        assert r_rec.status_code == 200
        assert r_rec.json()["status"] == "reconnected"

        # 3. Deregister camera
        r_del = await client.delete("/api/cameras/cam_dynamic_01")
        assert r_del.status_code == 200
        assert r_del.json()["status"] == "deregistered"


@pytest.mark.asyncio
async def test_api_readiness_probe_and_demo_reset():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Readiness probe
        r_ready = await client.get("/api/readiness")
        assert r_ready.status_code == 200
        data = r_ready.json()
        assert "status" in data
        assert "checks" in data
        assert data["checks"]["database_connected"] is True

        # 2. Demo reset
        r_reset = await client.post("/api/system/demo-reset")
        assert r_reset.status_code == 200
        assert r_reset.json()["status"] == "reset_complete"
