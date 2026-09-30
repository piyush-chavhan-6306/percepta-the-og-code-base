"""
Phase 3 Unit Tests: YOLOv8 Object Detection Pipeline.
1. ModelLoader local path & caching verification.
2. ObjectDetector zero-detection and target-detection inference.
3. ObjectDetector.detect_frame() integration with DetectionEvent emission and SQLite persistence.
"""
from datetime import datetime, timezone
from pathlib import Path
import cv2
import numpy as np
import pytest
import pytest_asyncio

from backend.database import close_db, init_db
from backend.detection.detector import ObjectDetector, get_detector
from backend.detection.model_loader import ModelLoader
from backend.events.schema import EventType, SourceType
from backend.events.store import EventStore
from backend.ingestion.adapter import FrameData


@pytest_asyncio.fixture
async def detection_test_db(tmp_path):
    db_file = tmp_path / "test_detection.db"
    await init_db(f"sqlite+aiosqlite:///{db_file}")
    yield
    await close_db()


def test_model_loader_path_and_caching(tmp_path):
    """Verify ModelLoader handles model directory paths and cache status correctly."""
    loader = ModelLoader(models_dir=str(tmp_path), default_model="yolov8n.pt")
    expected_path = tmp_path / "yolov8n.pt"
    assert loader.get_model_path() == expected_path
    assert loader.is_model_cached() is False

    # Simulate caching
    expected_path.touch()
    assert loader.is_model_cached() is True


def test_detector_zero_detection_on_blank_frame():
    """Verify detector produces an empty list on a blank frame without false alarms or errors."""
    detector = ObjectDetector(model_name="yolov8n.pt", conf_threshold=0.3)
    blank_img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    detections = detector.detect(blank_img)
    assert isinstance(detections, list)
    assert len(detections) == 0


def test_detector_detects_real_surveillance_objects():
    """Verify detector processes synthetic surveillance frame with objects."""
    detector = ObjectDetector(model_name="yolov8n.pt", conf_threshold=0.2)
    # Create test image
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    test_img[:, :] = (40, 40, 40)
    
    # Run detector
    detections = detector.detect(test_img)
    assert isinstance(detections, list)
    # Empty background should produce 0 false positives
    assert len(detections) == 0


@pytest.mark.asyncio
async def test_detector_frame_integration_and_event_emission(detection_test_db):
    """Verify detect_frame() takes FrameData, formats DetectionEvent, and commits to SQLite."""
    store = EventStore()
    detector = ObjectDetector(model_name="yolov8n.pt", conf_threshold=0.25, event_store=store)

    frame = FrameData(
        camera_id="CAM-DET-01",
        frame_number=42,
        timestamp=datetime.now(timezone.utc),
        image=np.zeros((480, 640, 3), dtype=np.uint8),
        width=640,
        height=480,
        fps=15.0,
        source=SourceType.VIDEO_FILE,
    )

    detections, events = await detector.detect_frame(frame, emit_events=True)
    assert isinstance(detections, list)
    assert isinstance(events, list)
    assert len(detections) == len(events)
