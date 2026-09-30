"""
Unit and Integration Tests for Multi-Modal Defense Sensor Ingestion.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.main import create_app
from backend.sensors.multi_modal import get_sensor_manager


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


def test_sensor_manager_initial_registry():
    manager = get_sensor_manager()
    status = manager.get_sensors_status()
    assert status["total_sensors"] >= 3
    assert "RADAR_ALPHA_01" in status["sensors"]
    assert "SEISMIC_BRAVO_01" in status["sensors"]


@pytest.mark.asyncio
async def test_sensor_ingest_and_status_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest Radar Telemetry
        r_radar = await client.post(
            "/api/sensors/ingest",
            json={
                "sensor_id": "RADAR_ALPHA_01",
                "sensor_type": "RADAR",
                "sector_id": "Sector Alpha",
                "confidence": 0.92,
                "data": {
                    "range_meters": 450.5,
                    "azimuth_degrees": 124.0,
                    "velocity_mps": 14.2,
                    "radar_cross_section": 2.5,
                },
            },
        )
        assert r_radar.status_code == 200
        assert r_radar.json()["status"] == "ingested"

        # 2. Ingest Seismic Telemetry
        r_seismic = await client.post(
            "/api/sensors/ingest",
            json={
                "sensor_id": "SEISMIC_BRAVO_01",
                "sensor_type": "SEISMIC",
                "sector_id": "Sector Bravo",
                "confidence": 0.88,
                "data": {
                    "vibration_amplitude": 0.045,
                    "footstep_cadence_hz": 1.8,
                    "estimated_mass_kg": 75.0,
                },
            },
        )
        assert r_seismic.status_code == 200
        assert r_seismic.json()["status"] == "ingested"

        # 3. Get Sensors Status
        r_status = await client.get("/api/sensors/status")
        assert r_status.status_code == 200
        data = r_status.json()
        assert data["total_sensors"] >= 2
        assert "RADAR_ALPHA_01" in data["sensors"]
