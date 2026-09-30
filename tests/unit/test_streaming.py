"""
Unit tests for WebSocket event streaming and MJPEG video streaming endpoints.
"""
import pytest
from starlette.testclient import TestClient

from backend.events.bus import get_event_bus
from backend.events.schema import AlertEvent, SourceType
from backend.ingestion.camera_manager import get_camera_manager
from backend.ingestion.simulation_adapter import SimulationAdapter
from backend.main import create_app


def test_websocket_events_endpoint_and_broadcast():
    app = create_app()
    bus = get_event_bus()

    client = TestClient(app)
    with client.websocket_connect("/ws/events") as websocket:
        # Send ping, receive pong
        websocket.send_text("ping")
        resp = websocket.receive_text()
        assert "pong" in resp


@pytest.mark.asyncio
async def test_mjpeg_video_stream_serves_worker_annotated_frames():
    """
    The MJPEG generator serves frames published by the camera's perception
    worker. It deliberately does not read the adapter itself — the worker is the
    single owner of the frame source, so a reader here would steal frames.
    """
    from backend.api.streaming import _mjpeg_generator
    from backend.tracking.live_worker import get_worker_registry

    manager = get_camera_manager()
    registry = get_worker_registry()
    adapter = SimulationAdapter(camera_id="cam_stream_mjpeg", width=320, height=240)
    manager.register_camera("cam_stream_mjpeg", adapter)
    await manager.start_camera("cam_stream_mjpeg")
    worker = await registry.start_worker("cam_stream_mjpeg")

    try:
        # Wait for the worker's first published frame (detection on the first
        # frame includes model warm-up, so allow a generous budget).
        frame = await worker.wait_for_frame(after_sequence=0, timeout=60.0)
        assert frame is not None, "worker published no annotated frame"
        assert frame.jpeg.startswith(b"\xff\xd8"), "published payload is not JPEG"

        gen = _mjpeg_generator("cam_stream_mjpeg")
        first_chunk = await anext(gen)
        await gen.aclose()

        assert isinstance(first_chunk, bytes)
        assert b"--frame" in first_chunk
        assert b"Content-Type: image/jpeg" in first_chunk
        assert b"\xff\xd8" in first_chunk
    finally:
        await registry.stop_worker("cam_stream_mjpeg")
        await manager.stop_camera("cam_stream_mjpeg")


@pytest.mark.asyncio
async def test_mjpeg_generator_does_not_consume_camera_frames():
    """
    Regression guard for the frame-stealing bug: streaming to a viewer must not
    advance the camera source, or the worker and the viewer would each see half
    the frames.
    """
    from backend.api.streaming import _mjpeg_generator

    manager = get_camera_manager()
    adapter = SimulationAdapter(camera_id="cam_stream_nosteal", width=160, height=120)
    manager.register_camera("cam_stream_nosteal", adapter)
    await manager.start_camera("cam_stream_nosteal")

    record = manager.get_camera("cam_stream_nosteal")
    frames_before = record.frames_processed

    # No worker running, so the generator has nothing to serve and must exit
    # without ever touching the adapter.
    gen = _mjpeg_generator("cam_stream_nosteal", startup_grace=0.05)
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

    assert record.frames_processed == frames_before

    await manager.stop_camera("cam_stream_nosteal")


def test_mjpeg_stream_nonexistent_camera_returns_404():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/stream/video/non_existent_cam_stream")
    assert response.status_code == 404
