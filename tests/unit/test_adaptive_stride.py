"""
Unit tests for adaptive frame stride controller, hysteresis, cooldown, and ByteTrack track state preservation.
"""
from datetime import datetime, timezone
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from backend.detection.detector import DetectionResult, ObjectDetector
from backend.events.schema import SourceType
from backend.events.store import EventStore
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.tracking.tracker import TrackedObject
from backend.zones.security_zone import ZoneMonitor


def _make_frame(frame_number: int = 1) -> FrameData:
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    return FrameData(
        camera_id="test_cam",
        frame_number=frame_number,
        timestamp=datetime.now(timezone.utc),
        image=img,
        width=640,
        height=480,
        fps=30.0,
        source=SourceType.SIMULATION,
    )


@pytest.mark.asyncio
async def test_adaptive_stride_increases_under_heavy_load():
    detector = MagicMock(spec=ObjectDetector)
    detector.device = "cpu"
    detector.detect.return_value = []

    tracker = MagicMock(spec=ByteTrackTracker)
    tracker.update.return_value = []

    mock_store = AsyncMock(spec=EventStore)

    pipeline = TrackingPipeline(
        detector=detector,
        tracker=tracker,
        event_store=mock_store,
        frame_stride=1,
        target_fps=30.0,
        min_frame_stride=1,
        max_frame_stride=3,
        adaptive_stride_enabled=True,
        sample_window=3,
        cooldown_frames=5,
    )
    pipeline.initialize()

    # Simulate 3 slow frames (100ms latency = 10 FPS, below target 30 * 0.85 = 25.5 FPS)
    pipeline._recent_latencies = [100.0, 100.0, 100.0]
    pipeline._evaluate_adaptive_stride()

    assert pipeline.frame_stride == 2
    assert pipeline._cooldown_counter == 5


@pytest.mark.asyncio
async def test_adaptive_stride_decreases_when_performance_recovers():
    detector = MagicMock(spec=ObjectDetector)
    detector.device = "cpu"
    detector.detect.return_value = []

    tracker = MagicMock(spec=ByteTrackTracker)
    tracker.update.return_value = []

    mock_store = AsyncMock(spec=EventStore)

    pipeline = TrackingPipeline(
        detector=detector,
        tracker=tracker,
        event_store=mock_store,
        frame_stride=2,
        target_fps=20.0,
        min_frame_stride=1,
        max_frame_stride=3,
        adaptive_stride_enabled=True,
        sample_window=3,
        cooldown_frames=5,
    )
    pipeline.initialize()

    # Simulate fast frames (10ms latency at stride 2 = 200 FPS effective, above target 20 * 1.4 = 28 FPS)
    pipeline._recent_latencies = [10.0, 10.0, 10.0]
    pipeline._evaluate_adaptive_stride()

    assert pipeline.frame_stride == 1
    assert pipeline._cooldown_counter == 5


@pytest.mark.asyncio
async def test_stride_cooldown_prevents_rapid_oscillation():
    pipeline = TrackingPipeline(
        adaptive_stride_enabled=True,
        target_fps=30.0,
        sample_window=2,
        cooldown_frames=10,
        frame_stride=1,
    )
    pipeline._cooldown_counter = 5
    pipeline._recent_latencies = [100.0, 100.0]

    # Evaluate should not change stride because cooldown is active
    pipeline._evaluate_adaptive_stride()
    assert pipeline.frame_stride == 1
    assert pipeline._cooldown_counter == 4


@pytest.mark.asyncio
async def test_bytetrack_state_preserved_during_skipped_frames():
    mock_store = AsyncMock(spec=EventStore)
    tracker = ByteTrackTracker()
    pipeline = TrackingPipeline(
        tracker=tracker,
        event_store=mock_store,
        frame_stride=2,
    )
    pipeline.initialize()

    dummy_track = TrackedObject(
        track_id=42,
        object_class="car",
        confidence=0.95,
        center_x=200.0,
        center_y=300.0,
        bounding_box=[150.0, 250.0, 250.0, 350.0],
        normalized_box=[0.2, 0.3, 0.4, 0.5],
        frame_number=1,
        timestamp=datetime.now(timezone.utc),
        lifecycle="updated",
    )
    pipeline._last_tracks = [dummy_track]

    # Process frame 2 (intermediate frame when stride=2, since (2 - 1) % 2 != 0)
    res_skipped = await pipeline.process_frame(_make_frame(frame_number=2))

    assert res_skipped.detections == []
    assert len(res_skipped.tracks) == 1
    assert res_skipped.tracks[0].track_id == 42
    assert pipeline._frames_skipped == 1


@pytest.mark.asyncio
async def test_watchdog_metrics_reporting():
    pipeline = TrackingPipeline(frame_stride=2, target_fps=30.0)
    pipeline._frames_processed = 10
    pipeline._frames_skipped = 5
    pipeline._last_inference_ms = 42.5
    pipeline._last_tracking_ms = 2.1
    pipeline._last_persistence_ms = 1.3
    pipeline._last_total_ms = 45.9

    metrics = pipeline.get_metrics()
    assert metrics["frames_processed"] == 10
    assert metrics["frames_skipped"] == 5
    assert metrics["inference_latency_ms"] == 42.5
    assert metrics["tracking_latency_ms"] == 2.1
    assert metrics["persistence_latency_ms"] == 1.3
    assert metrics["total_latency_ms"] == 45.9
    assert metrics["frame_stride"] == 2
