"""
Unit tests for tracker-based intermediate motion prediction and provenance tracking.
"""
from datetime import datetime, timezone
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock

from backend.detection.detector import DetectionResult, ObjectDetector
from backend.events.schema import SourceType
from backend.events.store import EventStore
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity


def _make_frame(frame_number: int = 1) -> FrameData:
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    return FrameData(
        camera_id="cam_pred_test",
        frame_number=frame_number,
        timestamp=datetime.now(timezone.utc),
        image=img,
        width=1280,
        height=720,
        fps=30.0,
        source=SourceType.SIMULATION,
    )


@pytest.mark.asyncio
async def test_tracker_predict_step_advances_coordinates():
    tracker = ByteTrackTracker()
    tracker.initialize()

    fd1 = _make_frame(frame_number=1)
    det1 = [
        DetectionResult(
            class_id=2,
            class_name="car",
            confidence=0.9,
            bounding_box=[100.0, 100.0, 200.0, 200.0],
            normalized_box=[100/1280, 100/720, 200/1280, 200/720],
        )
    ]
    tracks1 = tracker.update(det1, fd1)
    assert len(tracks1) == 1
    assert tracks1[0].provenance == "detection"

    # Intermediate prediction step without YOLO
    fd2 = _make_frame(frame_number=2)
    pred_tracks = tracker.predict_step(fd2)
    assert len(pred_tracks) == 1
    assert pred_tracks[0].track_id == tracks1[0].track_id
    assert pred_tracks[0].provenance == "prediction"


@pytest.mark.asyncio
async def test_pipeline_intermediate_prediction_emits_zero_fake_detections():
    detector = MagicMock(spec=ObjectDetector)
    detector.device = "cpu"
    detector.detect.return_value = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.88,
            bounding_box=[300.0, 300.0, 400.0, 500.0],
            normalized_box=[0.23, 0.41, 0.31, 0.69],
        )
    ]

    tracker = ByteTrackTracker()
    mock_store = AsyncMock(spec=EventStore)

    pipeline = TrackingPipeline(
        detector=detector,
        tracker=tracker,
        event_store=mock_store,
        frame_stride=2,
        enable_intermediate_predictions=True,
    )
    pipeline.initialize()

    # Frame 1: Keyframe with YOLO detection
    res1 = await pipeline.process_frame(_make_frame(frame_number=1))
    assert len(res1.detections) == 1
    assert len(res1.tracks) == 1
    assert res1.tracks[0].provenance == "detection"

    # Frame 2: Intermediate frame with Kalman prediction
    res2 = await pipeline.process_frame(_make_frame(frame_number=2))
    assert len(res2.detections) == 0  # Strictly 0 detections (no fake YOLO detections)
    assert len(res2.tracks) == 1
    assert res2.tracks[0].provenance == "prediction"
    assert res2.tracks[0].track_id == res1.tracks[0].track_id
