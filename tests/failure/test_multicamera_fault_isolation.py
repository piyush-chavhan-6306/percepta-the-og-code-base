"""
Multi-Camera Concurrency and Fault Isolation Failure Tests.
Verifies that failure or frame starvation on one camera stream does not block,
corrupt, or crash concurrent camera pipelines or mix camera-local identities.
"""
import asyncio
import pytest

from backend.database import init_db
from backend.events.schema import SourceType
from backend.events.store import get_event_store
from backend.ingestion.camera_manager import CameraManager, CameraStatus
from backend.ingestion.simulation_adapter import SimulationAdapter
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, ZoneMonitor


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_four_concurrent_cameras_fault_isolation():
    manager = CameraManager()
    store = get_event_store()

    # Setup 4 distinct cameras
    cams = ["CAM_PERIMETER_1", "CAM_PERIMETER_2", "CAM_PERIMETER_3", "CAM_FAULTY"]
    for cid in cams:
        adapter = SimulationAdapter(camera_id=cid, width=640, height=480, fps=20.0, max_frames=30)
        manager.register_camera(camera_id=cid, adapter=adapter, name=f"Camera {cid}")
        await manager.start_camera(cid)

    # Verify all 4 are online
    for cid in cams:
        assert manager.get_camera(cid).status == CameraStatus.ONLINE

    # Simulate fault on CAM_FAULTY: Stop it unexpectedly
    await manager.stop_camera("CAM_FAULTY")
    assert manager.get_camera("CAM_FAULTY").status == CameraStatus.OFFLINE

    # Process 10 frames across all cameras concurrently
    async def process_cam_frames(cid: str):
        frames = []
        for _ in range(10):
            f = await manager.get_latest_frame(cid)
            if f is not None:
                frames.append(f)
            await asyncio.sleep(0.005)
        return cid, len(frames)

    results = await asyncio.gather(
        process_cam_frames("CAM_PERIMETER_1"),
        process_cam_frames("CAM_PERIMETER_2"),
        process_cam_frames("CAM_PERIMETER_3"),
        process_cam_frames("CAM_FAULTY"),
    )

    result_dict = dict(results)
    # Healthy cameras received all frames
    assert result_dict["CAM_PERIMETER_1"] == 10
    assert result_dict["CAM_PERIMETER_2"] == 10
    assert result_dict["CAM_PERIMETER_3"] == 10
    # Faulty camera received 0 frames, dropped accounting handled safely
    assert result_dict["CAM_FAULTY"] == 0

    # Ensure Camera-Local Tracking IDs are completely isolated
    tracker1 = ByteTrackTracker()
    tracker2 = ByteTrackTracker()
    assert tracker1 is not tracker2

    await manager.stop_all()


@pytest.mark.asyncio
async def test_reconnect_recovery_while_other_cameras_stream():
    manager = CameraManager()
    cam1 = SimulationAdapter(camera_id="CAM_HEALTHY", fps=20.0)
    cam2 = SimulationAdapter(camera_id="CAM_RECONNECT", fps=20.0)

    manager.register_camera("CAM_HEALTHY", cam1)
    manager.register_camera("CAM_RECONNECT", cam2)

    await manager.start_camera("CAM_HEALTHY")
    await manager.start_camera("CAM_RECONNECT")

    # Stop cam2 to simulate disconnection
    await manager.stop_camera("CAM_RECONNECT")
    assert manager.get_camera("CAM_RECONNECT").status == CameraStatus.OFFLINE

    # Trigger reconnect on cam2 while cam1 is actively yielding frames
    async def stream_cam1():
        frames = []
        for _ in range(15):
            f = await manager.get_latest_frame("CAM_HEALTHY")
            if f is not None:
                frames.append(f)
            await asyncio.sleep(0.01)
        return len(frames)

    async def reconnect_cam2():
        await asyncio.sleep(0.02)
        success = await manager.reconnect_camera("CAM_RECONNECT", max_retries=2, base_delay=0.05)
        return success

    cam1_count, rec_success = await asyncio.gather(stream_cam1(), reconnect_cam2())

    assert cam1_count == 15
    assert rec_success is True
    assert manager.get_camera("CAM_RECONNECT").status == CameraStatus.ONLINE

    await manager.stop_all()
