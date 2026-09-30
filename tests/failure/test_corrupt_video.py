"""
Phase 2 Deliberate Failure Tests:
1. Video file not found (missing camera stream source).
2. Corrupted / unopenable video file format.
3. Reading from stopped / uninitialized stream.
"""
from pathlib import Path
import pytest
from backend.ingestion.video_adapter import VideoFileAdapter


@pytest.mark.asyncio
async def test_missing_video_file_raises_clean_error():
    """Verify that a non-existent video path raises FileNotFoundError cleanly."""
    adapter = VideoFileAdapter(
        camera_id="CAM-ERR-01",
        video_path="non_existent_directory/missing_camera_feed.mp4",
    )
    with pytest.raises(FileNotFoundError) as exc_info:
        await adapter.start()
    assert "Video file not found" in str(exc_info.value)
    assert not adapter.is_running


@pytest.mark.asyncio
async def test_corrupt_video_file_raises_value_error(tmp_path):
    """Verify that a corrupted (garbage bytes) file raises ValueError without crashing."""
    corrupt_file = tmp_path / "corrupt_camera.mp4"
    corrupt_file.write_bytes(b"THIS IS NOT A VALID VIDEO FILE GARBAGE DATA 1234567890")

    adapter = VideoFileAdapter(
        camera_id="CAM-ERR-02",
        video_path=str(corrupt_file),
    )
    with pytest.raises(ValueError) as exc_info:
        await adapter.start()
    assert "Failed to open video file" in str(exc_info.value)
    assert not adapter.is_running


@pytest.mark.asyncio
async def test_reading_from_stopped_adapter():
    """Verify get_next_frame on unstarted or stopped adapter returns None safely."""
    adapter = VideoFileAdapter(
        camera_id="CAM-ERR-03",
        video_path="dummy.mp4",
    )
    frame = await adapter.get_next_frame()
    assert frame is None
