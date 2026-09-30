"""
Unit tests for CameraManager and multi-camera stream lifecycle management.
"""
import pytest
from datetime import datetime, timezone
import numpy as np

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData
from backend.ingestion.camera_manager import CameraManager, CameraStatus
from backend.ingestion.simulation_adapter import SimulationAdapter


@pytest.mark.asyncio
async def test_camera_manager_registration_and_list():
    manager = CameraManager()
    adapter1 = SimulationAdapter(camera_id="cam_sim_1", width=640, height=480)
    adapter2 = SimulationAdapter(camera_id="cam_sim_2", width=1280, height=720)

    rec1 = manager.register_camera("cam_sim_1", adapter1, name="North Gate", location_label="Sector A")
    rec2 = manager.register_camera("cam_sim_2", adapter2, name="South Gate", location_label="Sector B")

    assert rec1.camera_id == "cam_sim_1"
    assert rec1.name == "North Gate"
    assert rec2.camera_id == "cam_sim_2"

    cams = manager.list_cameras()
    assert len(cams) == 2
    cam_ids = [c["camera_id"] for c in cams]
    assert "cam_sim_1" in cam_ids
    assert "cam_sim_2" in cam_ids


@pytest.mark.asyncio
async def test_camera_manager_start_stop_lifecycle():
    manager = CameraManager()
    adapter = SimulationAdapter(camera_id="cam_lifecycle", width=640, height=480)
    manager.register_camera("cam_lifecycle", adapter)

    # Start
    started = await manager.start_camera("cam_lifecycle")
    assert started is True
    rec = manager.get_camera("cam_lifecycle")
    assert rec.status == CameraStatus.ONLINE

    # Fetch frame
    frame = await manager.get_latest_frame("cam_lifecycle")
    assert frame is not None
    assert frame.camera_id == "cam_lifecycle"
    assert rec.frames_processed == 1

    # Stop
    stopped = await manager.stop_camera("cam_lifecycle")
    assert stopped is True
    assert rec.status == CameraStatus.OFFLINE


@pytest.mark.asyncio
async def test_camera_manager_unknown_camera_handling():
    manager = CameraManager()
    assert manager.get_camera("non_existent") is None
    assert await manager.start_camera("non_existent") is False
    assert await manager.stop_camera("non_existent") is False
    assert await manager.get_latest_frame("non_existent") is None


@pytest.mark.asyncio
async def test_camera_manager_stop_all():
    manager = CameraManager()
    adapter1 = SimulationAdapter(camera_id="cam_stop_1")
    adapter2 = SimulationAdapter(camera_id="cam_stop_2")
    manager.register_camera("cam_stop_1", adapter1)
    manager.register_camera("cam_stop_2", adapter2)

    await manager.start_camera("cam_stop_1")
    await manager.start_camera("cam_stop_2")

    assert manager.get_camera("cam_stop_1").status == CameraStatus.ONLINE
    assert manager.get_camera("cam_stop_2").status == CameraStatus.ONLINE

    await manager.stop_all()
    assert manager.get_camera("cam_stop_1").status == CameraStatus.OFFLINE
    assert manager.get_camera("cam_stop_2").status == CameraStatus.OFFLINE
