"""
Unit tests for RTSP Camera Adapter and credential sanitization.
"""
import pytest
from backend.ingestion.rtsp_adapter import RTSPAdapter, sanitize_rtsp_url


def test_sanitize_rtsp_url():
    # URL with user:password
    url1 = "rtsp://admin:secret123@192.168.1.100:554/live/ch0"
    sanitized1 = sanitize_rtsp_url(url1)
    assert sanitized1 == "rtsp://admin:***@192.168.1.100:554/live/ch0"
    assert "secret123" not in sanitized1

    # URL without credentials
    url2 = "rtsp://192.168.1.100:554/live/ch0"
    assert sanitize_rtsp_url(url2) == url2

    # Empty string
    assert sanitize_rtsp_url("") == ""


def test_rtsp_adapter_initialization_and_info():
    adapter = RTSPAdapter(
        camera_id="cam_rtsp_test",
        rtsp_url="rtsp://operator:borderpass@10.0.0.50:554/h264",
        target_fps=25.0,
    )
    info = adapter.get_stream_info()
    assert info["camera_id"] == "cam_rtsp_test"
    assert info["source_type"] == "rtsp"
    assert "borderpass" not in info["stream_url"]
    assert "rtsp://operator:***@10.0.0.50:554/h264" == info["stream_url"]
    assert info["is_running"] is False


@pytest.mark.asyncio
async def test_rtsp_adapter_empty_url_raises():
    adapter = RTSPAdapter(camera_id="cam_empty", rtsp_url="")
    with pytest.raises(ValueError, match="Empty RTSP URL"):
        await adapter.start()
