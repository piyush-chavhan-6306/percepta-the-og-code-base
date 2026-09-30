"""
Phase 3 Deliberate Failure Tests:
1. Handling corrupted / empty image arrays in ObjectDetector.
2. Handling None image inputs without crashing.
3. Handling invalid frame dimensions (0x0).
"""
import numpy as np
import pytest
from backend.detection.detector import ObjectDetector


def test_detector_handles_none_image():
    """Verify detector handles None image input safely."""
    detector = ObjectDetector(model_name="yolov8n.pt")
    detections = detector.detect(None)  # type: ignore
    assert detections == []


def test_detector_handles_empty_numpy_array():
    """Verify detector handles 0-sized numpy array without crashing."""
    detector = ObjectDetector(model_name="yolov8n.pt")
    empty_img = np.array([], dtype=np.uint8)
    detections = detector.detect(empty_img)
    assert detections == []


def test_detector_handles_zero_dimension_image():
    """Verify detector handles 0x0 image shape safely."""
    detector = ObjectDetector(model_name="yolov8n.pt")
    zero_dim_img = np.zeros((0, 0, 3), dtype=np.uint8)
    detections = detector.detect(zero_dim_img)
    assert detections == []
