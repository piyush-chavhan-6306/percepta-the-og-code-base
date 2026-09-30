"""
Phase 2 Unit Tests: Video Ingestion & Bounded FrameBuffer.
1. FrameBuffer bounded ring behavior & pre/trigger extraction.
2. SimulationAdapter frame generation.
3. VideoFileAdapter video reading & stream metadata.
"""
from datetime import datetime, timezone
from pathlib import Path
import cv2
import numpy as np
import pytest

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData
from backend.ingestion.frame_buffer import FrameBuffer, FrameBufferManager
from backend.ingestion.simulation_adapter import SimulationAdapter
from backend.ingestion.video_adapter import VideoFileAdapter


def create_sample_video(file_path: Path, num_frames: int = 20, width: int = 320, height: int = 240) -> Path:
    """Helper to create a temporary MP4 video file using OpenCV."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(file_path), fourcc, 15.0, (width, height))
    for i in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(frame, f"Frame {i}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        out.write(frame)
    out.release()
    return file_path


def test_frame_buffer_bounded_capacity_and_slicing():
    """Verify FrameBuffer stays strictly within max_frames and extracts pre/trigger frames."""
    capacity = 10
    buf = FrameBuffer(camera_id="CAM-01", max_frames=capacity)

    # Push 20 frames into buffer of capacity 10
    for i in range(1, 21):
        fake_img = np.zeros((10, 10, 3), dtype=np.uint8)
        frame = FrameData(
            camera_id="CAM-01",
            frame_number=i,
            timestamp=datetime.now(timezone.utc),
            image=fake_img,
            width=10,
            height=10,
            fps=15.0,
        )
        buf.push(frame)

    # 1. Size must be bounded to capacity
    assert buf.size() == capacity

    # 2. Oldest frames (1-10) should have been dropped; 11-20 should be present
    assert buf.get_frame(1) is None
    assert buf.get_frame(10) is None
    assert buf.get_frame(11) is not None
    assert buf.get_frame(20) is not None
    latest = buf.get_latest()
    assert latest is not None
    assert latest.frame_number == 20

    # 3. Pre-event extraction around frame 18
    pre_frames = buf.get_pre_event_frames(trigger_frame_number=18, count=5)
    assert len(pre_frames) == 5
    assert [f.frame_number for f in pre_frames] == [13, 14, 15, 16, 17]

    # 4. Trigger frame extraction
    trig_frame = buf.get_trigger_frame(trigger_frame_number=18)
    assert trig_frame is not None
    assert trig_frame.frame_number == 18

    # 5. Window extraction
    window = buf.get_window(start_frame=14, end_frame=16)
    assert len(window) == 3
    assert [f.frame_number for f in window] == [14, 15, 16]


@pytest.mark.asyncio
async def test_simulation_adapter():
    """Verify SimulationAdapter generates frames and populates buffer."""
    buf = FrameBuffer(camera_id="CAM-SIM-01", max_frames=50)
    adapter = SimulationAdapter(
        camera_id="CAM-SIM-01",
        width=320,
        height=240,
        fps=10.0,
        max_frames=10,
        frame_buffer=buf,
    )

    await adapter.start()
    assert adapter.is_running

    frames = []
    while True:
        frame = await adapter.get_next_frame()
        if frame is None:
            break
        frames.append(frame)

    assert len(frames) == 10
    assert frames[0].frame_number == 1
    assert frames[-1].frame_number == 10
    assert frames[0].shape == (240, 320, 3)
    assert buf.size() == 10

    await adapter.stop()
    assert not adapter.is_running


@pytest.mark.asyncio
async def test_video_file_adapter(tmp_path):
    """Verify VideoFileAdapter reads MP4 video, extracts metadata, and fills FrameBuffer."""
    video_path = tmp_path / "test_feed.mp4"
    create_sample_video(video_path, num_frames=10, width=320, height=240)

    buf = FrameBuffer(camera_id="CAM-TEST", max_frames=50)
    adapter = VideoFileAdapter(
        camera_id="CAM-TEST",
        video_path=str(video_path),
        loop=False,
        frame_buffer=buf,
    )

    await adapter.start()
    assert adapter.is_running

    info = adapter.get_stream_info()
    assert info["camera_id"] == "CAM-TEST"
    assert info["resolution"] == "320x240"
    assert info["total_frames"] == 10

    read_frames = []
    while True:
        frame = await adapter.get_next_frame()
        if frame is None:
            break
        read_frames.append(frame)

    assert len(read_frames) == 10
    assert buf.size() == 10
    assert read_frames[0].width == 320
    assert read_frames[0].height == 240

    await adapter.stop()
    assert not adapter.is_running
