"""
Unit and Integration Tests for Fleet Surveillance Coverage & Operational Health Analytics.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.ingestion.camera_manager import get_camera_manager
from backend.ingestion.simulation_adapter import SimulationAdapter
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_coverage_report_rest_api():
    manager = get_camera_manager()
    cam1 = SimulationAdapter(camera_id="CAM_COV_1", width=640, height=480, fps=25.0)
    manager.register_camera("CAM_COV_1", cam1, name="Sector Alpha Tower")
    await manager.start_camera("CAM_COV_1")

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/system/coverage-report")
        assert r.status_code == 200
        data = r.json()
        assert "total_cameras_registered" in data
        assert "active_cameras_online" in data
        assert "sector_coverage_percentage" in data
        assert "surveillance_readiness_grade" in data
        assert "camera_fleet_status" in data
        assert data["total_cameras_registered"] >= 1
        assert data["active_cameras_online"] >= 1
        assert data["sector_coverage_percentage"] > 0.0

    await manager.stop_all()
