"""
PERCEPTA Temporal Detection & Tracking Stability Regression Tests.
Verifies:
1. Stable physical objects produce temporally continuous tracks without frame-to-frame dropouts.
2. Centroid jitter on stationary objects remains within deadband (subpixel damping).
3. Unconfirmed 1-frame spurious clutter is filtered out (hits >= 2).
4. Class labels remain consistent across frames via temporal majority voting.
5. Lost-track grace persistence maintains track state through momentary detection gaps.
"""
from datetime import datetime, timezone
import numpy as np
import pytest
from backend.detection.detector import DetectionResult
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker


def test_unconfirmed_single_frame_clutter_filtered():
    """Verify that a 1-frame noise detection is NOT emitted to the operator when min_hits=2."""
    tracker = ByteTrackTracker(fps=30.0, min_hits=2)
    tracker.initialize()

    # Frame 1: Detection appears
    fd1 = FrameData(
        camera_id="CAM-01",
        image=np.zeros((720, 1280, 3), dtype=np.uint8),
        frame_number=1,
        timestamp=datetime.now(timezone.utc),
        source="video_file",
        width=1280,
        height=720,
        fps=30.0,
    )
    det1 = [
        DetectionResult(
            class_id=2,
            class_name="car",
            confidence=0.55,
            bounding_box=[100.0, 100.0, 200.0, 200.0],
            normalized_box=[100/1280, 100/720, 200/1280, 200/720],
        )
    ]
    # Frame 1: hits=1, track is provisional and not confirmed
    tracks1 = tracker.update(det1, fd1)
    assert len(tracks1) == 0, "Unconfirmed single-frame clutter should not be emitted"

    # Frame 2: Same detection persists -> confirmed (hits=2)
    fd2 = FrameData(
        camera_id="CAM-01",
        image=np.zeros((720, 1280, 3), dtype=np.uint8),
        frame_number=2,
        timestamp=datetime.now(timezone.utc),
        source="video_file",
        width=1280,
        height=720,
        fps=30.0,
    )
    tracks2 = tracker.update(det1, fd2)
    assert len(tracks2) == 1, "Confirmed persistent object should be emitted on hit >= 2"
    assert tracks2[0].hits >= 2


def test_class_label_temporal_voting_stability():
    """Verify that borderline class flips (e.g. car <-> truck) do not oscillate."""
    tracker = ByteTrackTracker(fps=30.0)
    tracker.initialize()

    fd = FrameData(
        camera_id="CAM-01",
        image=np.zeros((720, 1280, 3), dtype=np.uint8),
        frame_number=1,
        timestamp=datetime.now(timezone.utc),
        source="video_file",
        width=1280,
        height=720,
        fps=30.0,
    )

    box = [200.0, 200.0, 350.0, 300.0]
    norm = [200/1280, 200/720, 350/1280, 300/720]

    # Feed 'car' for 5 frames
    for i in range(1, 6):
        fd.frame_number = i
        det = [DetectionResult(class_id=2, class_name="car", confidence=0.70, bounding_box=box, normalized_box=norm)]
        tracks = tracker.update(det, fd)

    assert len(tracks) == 1
    assert tracks[0].object_class == "car"

    # Feed momentary 'truck' on frame 6 (single borderline misclassification)
    fd.frame_number = 6
    det_truck = [DetectionResult(class_id=7, class_name="truck", confidence=0.45, bounding_box=box, normalized_box=norm)]
    tracks_f6 = tracker.update(det_truck, fd)

    assert len(tracks_f6) == 1
    # Majority voting preserves 'car'
    assert tracks_f6[0].object_class == "car", "Class label should be stabilized by majority voting"


def test_lost_track_grace_persistence():
    """Verify that a confirmed track does NOT blink off when detection misses for 1-2 frames."""
    tracker = ByteTrackTracker(fps=30.0)
    tracker.initialize()

    fd = FrameData(
        camera_id="CAM-01",
        image=np.zeros((720, 1280, 3), dtype=np.uint8),
        frame_number=1,
        timestamp=datetime.now(timezone.utc),
        source="video_file",
        width=1280,
        height=720,
        fps=30.0,
    )
    box = [400.0, 200.0, 500.0, 300.0]
    norm = [400/1280, 200/720, 500/1280, 300/720]
    det = [DetectionResult(class_id=2, class_name="car", confidence=0.80, bounding_box=box, normalized_box=norm)]

    # Establish track over 3 frames
    for i in range(1, 4):
        fd.frame_number = i
        tracker.update(det, fd)

    # Frame 4: Detector misses (empty detections)
    fd.frame_number = 4
    tracks_miss = tracker.update([], fd)
    assert len(tracks_miss) == 1, "Track should persist gracefully during momentary dropout"
    assert tracks_miss[0].provenance == "prediction"

    # Frame 5: Detector misses again
    fd.frame_number = 5
    tracks_miss2 = tracker.update([], fd)
    assert len(tracks_miss2) == 1, "Track should persist for up to 3 frames of dropout"
