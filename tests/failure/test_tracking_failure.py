"""
Failure Tests for Tracking and Intelligence Pipeline.
Tests graceful error handling for empty/None detections, corrupt bounding boxes,
zero-dimension frames, tracker reset during inference, and strict Persist-Before-Publish DB failures.
"""
from datetime import datetime, timezone
import numpy as np
import pytest
from unittest.mock import AsyncMock, patch

from backend.detection.detector import DetectionResult
from backend.events.bus import EventBus
from backend.events.schema import SourceType, TrackingEvent
from backend.events.store import EventStore
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, ZoneMonitor


def _make_frame(
    frame_num: int = 1,
    image: np.ndarray = None,
    width: int = 640,
    height: int = 480,
    timestamp: datetime = None,
) -> FrameData:
    if image is None:
        image = np.zeros((height, width, 3), dtype=np.uint8)
    return FrameData(
        camera_id="cam_fail_test",
        frame_number=frame_num,
        timestamp=timestamp or datetime.now(timezone.utc),
        image=image,
        width=width,
        height=height,
        fps=30.0,
        source=SourceType.SIMULATION,
    )


def test_tracker_handles_empty_detection_list():
    tracker = ByteTrackTracker()
    tracker.initialize()
    frame = _make_frame()

    tracks = tracker.update([], frame)
    assert tracks == []
    assert len(tracker.get_active_tracks()) == 0


def test_tracker_handles_none_and_corrupt_detections():
    tracker = ByteTrackTracker()
    tracker.initialize()
    frame = _make_frame()

    # None in list, corrupt detection objects
    dets = [
        None,
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.9,
            bounding_box=[100.0, 100.0, 50.0, 50.0],  # Inverted box (x2 < x1, y2 < y1)
            normalized_box=[0, 0, 0, 0],
        ),
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.9,
            bounding_box=[100.0, 100.0, 100.0, 100.0],  # Zero area box
            normalized_box=[0, 0, 0, 0],
        ),
    ]

    tracks = tracker.update(dets, frame)
    assert isinstance(tracks, list)
    assert len(tracks) == 0


def test_tracker_handles_none_frame_and_zero_dimensions():
    tracker = ByteTrackTracker()
    tracker.initialize()

    # None frame
    assert tracker.update([], None) == []

    # Zero dimension frame
    zero_frame = _make_frame(image=np.zeros((0, 0, 3), dtype=np.uint8), width=0, height=0)
    assert tracker.update([], zero_frame) == []


def test_tracker_reset_during_processing():
    tracker = ByteTrackTracker()
    tracker.initialize()

    frame1 = _make_frame(frame_num=1)
    dets1 = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.95,
            bounding_box=[100.0, 100.0, 150.0, 200.0],
            normalized_box=[100 / 640, 100 / 480, 150 / 640, 200 / 480],
        )
    ]
    tracker.update(dets1, frame1)
    assert len(tracker.get_active_tracks()) == 1

    # Reset mid-stream
    tracker.reset()
    assert len(tracker.get_active_tracks()) == 0

    # New frame after reset begins cleanly
    frame2 = _make_frame(frame_num=2)
    tracks2 = tracker.update(dets1, frame2)
    assert len(tracks2) == 1
    assert tracks2[0].lifecycle == "created"


@pytest.mark.asyncio
async def test_pipeline_persist_before_publish_failure_isolation():
    """
    If EventStore database persistence fails, NO event should ever reach the EventBus.
    """
    mock_bus = EventBus()
    received_events = []

    async def _subscriber(ev):
        received_events.append(ev)

    await mock_bus.subscribe(_subscriber)

    # Mock EventStore whose record_event raises a database exception
    mock_store = EventStore(bus=mock_bus)

    with patch.object(mock_store, "record_events_batch", side_effect=RuntimeError("SQLite Disk I/O Error")), \
         patch.object(mock_store, "record_event", side_effect=RuntimeError("SQLite Disk I/O Error")):
        tracker = ByteTrackTracker()
        monitor = ZoneMonitor(
            zones=[SecurityZone("z1", "Test Zone", [(0, 0), (500, 0), (500, 500), (0, 500)])]
        )
        pipeline = TrackingPipeline(tracker=tracker, zone_monitor=monitor, event_store=mock_store)
        pipeline.initialize()

        frame = _make_frame()
        # Mock detector to produce a valid detection
        with patch.object(
            pipeline.detector,
            "detect",
            return_value=[
                DetectionResult(
                    class_id=0,
                    class_name="person",
                    confidence=0.9,
                    bounding_box=[100.0, 100.0, 150.0, 200.0],
                    normalized_box=[0.1, 0.1, 0.2, 0.2],
                )
            ],
        ):
            with pytest.raises(RuntimeError, match="SQLite Disk I/O Error"):
                await pipeline.process_frame(frame)

    # Assert EventBus received 0 leaked events
    assert len(received_events) == 0
