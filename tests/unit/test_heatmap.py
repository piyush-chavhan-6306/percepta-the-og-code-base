"""
Unit and Integration Tests for Spatial Breach Heatmap Density Matrix Engine.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.schema import SourceType, TrackingEvent
from backend.events.store import get_event_store
from backend.main import create_app
from backend.zones.heatmap import get_heatmap_engine


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_spatial_heatmap_density_computation():
    store = get_event_store()
    engine = get_heatmap_engine()

    # Record tracking events at specific coordinates
    for i in range(10):
        t = TrackingEvent(
            camera_id="cam_heat_test",
            track_id="12",
            lifecycle="updated",
            position=[640.0, 360.0],  # Center of 1280x720 frame
            velocity=[0.0, 0.0],
            object_class="person",
            source=SourceType.SIMULATION,
        )
        await store.record_event(t)

    res = await engine.generate_heatmap(camera_id="cam_heat_test", grid_size=16)
    assert res.camera_id == "cam_heat_test"
    assert res.grid_size == 16
    assert res.total_points >= 10
    assert len(res.density_matrix) == 16
    assert len(res.density_matrix[0]) == 16
    assert res.max_density >= 10
    # Center cell should have density 1.0
    center_row = 8
    center_col = 8
    assert res.density_matrix[center_row][center_col] == 1.0


@pytest.mark.asyncio
async def test_spatial_heatmap_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/cameras/CAM_HEAT_TEST_API/heatmap?grid_size=16")
        assert r.status_code == 200
        data = r.json()
        assert data["camera_id"] == "CAM_HEAT_TEST_API"
        assert data["grid_size"] == 16
        assert "density_matrix" in data
        assert "summary" in data
