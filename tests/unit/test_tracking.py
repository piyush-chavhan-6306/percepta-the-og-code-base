"""
Unit Tests for Multi-Object Tracking (ByteTrack) & Movement Intelligence.
Tests tracker initialization, single/multi-object tracking, track ID persistence,
track creation, termination, reset, bounded trajectories, and movement vector calculations.
"""
from datetime import datetime, timezone
import numpy as np
import pytest

from backend.detection.detector import DetectionResult
from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.movement import calculate_cardinal_heading, calculate_movement_vector


def _make_frame(frame_num: int = 1, width: int = 640, height: int = 480, fps: float = 30.0) -> FrameData:
    return FrameData(
        camera_id="cam_test",
        frame_number=frame_num,
        timestamp=datetime.now(timezone.utc),
        image=np.zeros((height, width, 3), dtype=np.uint8),
        width=width,
        height=height,
        fps=fps,
        source=SourceType.SIMULATION,
    )


def test_tracker_initialization():
    tracker = ByteTrackTracker(track_high_thresh=0.5, track_buffer=30)
    tracker.initialize()
    assert tracker._is_initialized is True
    assert tracker._tracker is not None
    assert len(tracker.get_active_tracks()) == 0


def test_single_object_tracking_and_center_calculation():
    tracker = ByteTrackTracker()
    tracker.initialize()

    frame1 = _make_frame(frame_num=1)
    dets1 = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.95,
            bounding_box=[100.0, 100.0, 150.0, 200.0],
            normalized_box=[100.0 / 640, 100.0 / 480, 150.0 / 640, 200.0 / 480],
        )
    ]

    tracks1 = tracker.update(dets1, frame1)
    assert len(tracks1) == 1
    t = tracks1[0]
    assert t.object_class == "person"
    assert t.confidence == 0.95
    assert t.center_x == 125.0
    assert t.center_y == 150.0
    assert t.frame_number == 1
    assert t.lifecycle == "created"


def test_multiple_object_tracking():
    tracker = ByteTrackTracker()
    tracker.initialize()

    frame1 = _make_frame(frame_num=1)
    dets = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.92,
            bounding_box=[50.0, 50.0, 100.0, 150.0],
            normalized_box=[50 / 640, 50 / 480, 100 / 640, 150 / 480],
        ),
        DetectionResult(
            class_id=2,
            class_name="car",
            confidence=0.88,
            bounding_box=[300.0, 200.0, 450.0, 320.0],
            normalized_box=[300 / 640, 200 / 480, 450 / 640, 320 / 480],
        ),
    ]

    tracks = tracker.update(dets, frame1)
    assert len(tracks) == 2
    track_ids = {t.track_id for t in tracks}
    assert len(track_ids) == 2
    classes = {t.object_class for t in tracks}
    assert "person" in classes
    assert "car" in classes


def test_track_id_persistence_across_consecutive_frames():
    tracker = ByteTrackTracker(track_high_thresh=0.4, match_thresh=0.8)
    tracker.initialize()

    # Frame 1
    frame1 = _make_frame(frame_num=1)
    dets1 = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.90,
            bounding_box=[100.0, 100.0, 150.0, 200.0],
            normalized_box=[100 / 640, 100 / 480, 150 / 640, 200 / 480],
        )
    ]
    tracks1 = tracker.update(dets1, frame1)
    assert len(tracks1) == 1
    initial_id = tracks1[0].track_id

    # Frame 2: Slight movement
    frame2 = _make_frame(frame_num=2)
    dets2 = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.91,
            bounding_box=[105.0, 103.0, 155.0, 203.0],
            normalized_box=[105 / 640, 103 / 480, 155 / 640, 203 / 480],
        )
    ]
    tracks2 = tracker.update(dets2, frame2)
    assert len(tracks2) == 1
    assert tracks2[0].track_id == initial_id
    assert tracks2[0].lifecycle == "updated"
    assert tracks2[0].age >= 2
    assert tracks2[0].hits >= 2

    # Frame 3: Another slight movement
    frame3 = _make_frame(frame_num=3)
    dets3 = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.89,
            bounding_box=[110.0, 106.0, 160.0, 206.0],
            normalized_box=[110 / 640, 106 / 480, 160 / 640, 206 / 480],
        )
    ]
    tracks3 = tracker.update(dets3, frame3)
    assert len(tracks3) == 1
    assert tracks3[0].track_id == initial_id


def test_tracker_reset():
    tracker = ByteTrackTracker()
    tracker.initialize()

    frame1 = _make_frame(frame_num=1)
    dets1 = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.90,
            bounding_box=[100.0, 100.0, 150.0, 200.0],
            normalized_box=[100 / 640, 100 / 480, 150 / 640, 200 / 480],
        )
    ]
    tracks = tracker.update(dets1, frame1)
    assert len(tracks) == 1

    tracker.reset()
    assert len(tracker.get_active_tracks()) == 0


def test_bounded_trajectory_history():
    max_history = 10
    tracker = ByteTrackTracker(max_trajectory_history=max_history)
    tracker.initialize()

    for f in range(1, 25):
        frame = _make_frame(frame_num=f)
        offset = float(f * 2)
        dets = [
            DetectionResult(
                class_id=0,
                class_name="person",
                confidence=0.90,
                bounding_box=[100.0 + offset, 100.0, 150.0 + offset, 200.0],
                normalized_box=[(100 + offset) / 640, 100 / 480, (150 + offset) / 640, 200 / 480],
            )
        ]
        tracks = tracker.update(dets, frame)

    assert len(tracks) == 1
    assert len(tracks[0].trajectory) <= max_history


def test_movement_vector_calculation():
    # Linear movement East: dx = 20 px across 4 frames
    trajectory = [(100.0, 100.0), (105.0, 100.0), (110.0, 100.0), (115.0, 100.0), (120.0, 100.0)]
    mv = calculate_movement_vector(trajectory, fps=30.0)

    assert mv.dx == 5.0  # 20 / 4
    assert mv.dy == 0.0
    assert mv.distance_px == 20.0
    assert mv.direction_deg == 0.0
    assert mv.cardinal_heading == "E"
    assert mv.speed_px_per_frame == 5.0
    assert mv.speed_px_per_sec == 150.0

    # Linear movement South: dy = 20 px
    trajectory_s = [(100.0, 100.0), (100.0, 110.0), (100.0, 120.0)]
    mv_s = calculate_movement_vector(trajectory_s, fps=30.0)
    assert mv_s.dy == 10.0
    assert mv_s.direction_deg == 90.0
    assert mv_s.cardinal_heading == "S"


def test_cardinal_headings():
    assert calculate_cardinal_heading(0.0) == "E"
    assert calculate_cardinal_heading(45.0) == "SE"
    assert calculate_cardinal_heading(90.0) == "S"
    assert calculate_cardinal_heading(135.0) == "SW"
    assert calculate_cardinal_heading(180.0) == "W"
    assert calculate_cardinal_heading(225.0) == "NW"
    assert calculate_cardinal_heading(270.0) == "N"
    assert calculate_cardinal_heading(315.0) == "NE"
    assert calculate_cardinal_heading(0.0, is_stationary=True) == "STATIONARY"


def test_track_termination_after_track_buffer_expiry():
    tracker = ByteTrackTracker(track_buffer=5)
    tracker.initialize()

    # Step 1: Object present in frame 1
    f1 = _make_frame(frame_num=1)
    dets = [
        DetectionResult(
            class_id=0,
            class_name="person",
            confidence=0.95,
            bounding_box=[100.0, 100.0, 150.0, 200.0],
            normalized_box=[100 / 640, 100 / 480, 150 / 640, 200 / 480],
        )
    ]
    tracker.update(dets, f1)
    assert len(tracker.get_active_tracks()) == 1

    # Step 2: 10 frames of empty detections -> track should expire
    for f in range(2, 12):
        tracker.update([], _make_frame(frame_num=f))

    assert len(tracker.get_active_tracks()) == 0
