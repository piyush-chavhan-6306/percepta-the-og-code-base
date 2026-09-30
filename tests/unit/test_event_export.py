"""
Unit and Integration Tests for Surveillance Event & Incident Forensic Exporter.
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
async def test_event_export_json_and_csv_rest_api():
    store = get_event_store()

    # Record sample alert
    alert = AlertEvent(
        camera_id="cam_export_test",
        track_id="88",
        incident_id="INC_EXP_01",
        severity="CRITICAL",
        message="CRITICAL BOUNDARY CROSSING",
        source=SourceType.SIMULATION,
    )
    await store.record_event(alert)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test JSON Export
        r_json = await client.get("/api/events/export?format=json&limit=50")
        assert r_json.status_code == 200
        data = r_json.json()
        assert data["format"] == "json"
        assert data["count"] >= 1
        assert len(data["events"]) >= 1

        # 2. Test CSV Export
        r_csv = await client.get("/api/events/export?format=csv&limit=50")
        assert r_csv.status_code == 200
        assert "text/csv" in r_csv.headers["content-type"]
        csv_text = r_csv.text
        assert "seq_id,event_id,timestamp,camera_id" in csv_text
        assert "cam_export_test" in csv_text or "CRITICAL" in csv_text
