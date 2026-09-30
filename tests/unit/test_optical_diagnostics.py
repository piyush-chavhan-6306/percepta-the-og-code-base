"""
Unit and Integration Tests for Optical Quality & CCTV Lens Tampering Diagnostics.
"""
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from backend.ingestion.camera_manager import get_camera_manager
from backend.ingestion.optical_diagnostics import (
    SignalQualityStatus,
    evaluate_optical_quality,
)
from backend.ingestion.simulation_adapter import SimulationAdapter
from backend.main import create_app


def test_evaluate_optical_quality_nominal():
    # Create image with texture/edges
    img = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)
    diag = evaluate_optical_quality(img, camera_id="CAM_NOMINAL")
    assert diag.status == SignalQualityStatus.OPTIMAL
    assert diag.is_tampered_or_degraded is False
    assert diag.blur_score > 30.0


def test_evaluate_optical_quality_blurred_occluded():
    # Pure flat uniform image (simulating spray paint or severe lens occlusion)
    flat_img = np.full((480, 640, 3), 128, dtype=np.uint8)
    diag = evaluate_optical_quality(flat_img, camera_id="CAM_OCCLUDED")
    assert diag.status == SignalQualityStatus.OCCLUDED_OR_BLURRED
    assert diag.is_tampered_or_degraded is True
    assert diag.blur_score == 0.0


def test_evaluate_optical_quality_blinding_glare():
    # Saturated white image (simulating laser or floodlight blinding)
    glare_img = np.full((480, 640, 3), 255, dtype=np.uint8)
    diag = evaluate_optical_quality(glare_img, camera_id="CAM_GLARE")
    assert diag.status == SignalQualityStatus.BLINDED_GLARE
    assert diag.is_tampered_or_degraded is True
    assert diag.glare_percentage >= 99.0


def test_evaluate_optical_quality_blackout():
    # Saturated black image (simulating complete sensor blackout)
    black_img = np.zeros((480, 640, 3), dtype=np.uint8)
    diag = evaluate_optical_quality(black_img, camera_id="CAM_BLACKOUT")
    assert diag.status in (SignalQualityStatus.LOW_LIGHT_DEGRADED, SignalQualityStatus.OCCLUDED_OR_BLURRED)
    assert diag.is_tampered_or_degraded is True


@pytest.mark.asyncio
async def test_camera_diagnostics_rest_api():
    manager = get_camera_manager()
    cam = SimulationAdapter(camera_id="CAM_DIAG_TEST", width=320, height=240, fps=20.0)
    manager.register_camera("CAM_DIAG_TEST", cam)
    await manager.start_camera("CAM_DIAG_TEST")

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/cameras/CAM_DIAG_TEST/diagnostics")
        assert r.status_code == 200
        data = r.json()
        assert data["camera_id"] == "CAM_DIAG_TEST"
        assert "status" in data
        assert "blur_score" in data
        assert "is_tampered_or_degraded" in data

    await manager.stop_all()
