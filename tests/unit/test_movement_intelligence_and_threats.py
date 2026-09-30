"""
Unit tests for Movement Intelligence, Spatial Reasoning, Explainable Threat Engine,
Modular ANPR, Face Analytics, Multi-Camera Correlation, and Grounded Copilot.
"""
from datetime import datetime, timedelta, timezone
import pytest
import numpy as np

from backend.tracking.movement import (
    calculate_cardinal_heading,
    calculate_movement_vector,
    format_speed_label,
    is_moving_towards,
    detect_abnormal_direction_change,
    detect_oscillating_movement,
)
from backend.intelligence.threat_engine import compute_threat_score, ThreatEngine
from backend.detection.anpr import ANPRProcessor, get_anpr_processor
from backend.detection.face_analytics import FaceAnalyticsProcessor, get_face_processor
from backend.intelligence.correlation import MultiCameraCorrelator, get_correlator
from backend.ingestion.optical_diagnostics import evaluate_optical_quality, SignalQualityStatus, is_night_movement_condition
from backend.intelligence.assistant import SurveillanceAssistant
from backend.zones.security_zone import VirtualBoundary, ZoneSeverity, SecurityZone, ZoneMonitor
from backend.tracking.tracker import TrackedObject


def test_cardinal_heading_calculations():
    # 0 deg = East, 90 deg = South, 180 deg = West, 270 deg = North
    assert calculate_cardinal_heading(0.0) == "E"
    assert calculate_cardinal_heading(45.0) == "SE"
    assert calculate_cardinal_heading(90.0) == "S"
    assert calculate_cardinal_heading(135.0) == "SW"
    assert calculate_cardinal_heading(180.0) == "W"
    assert calculate_cardinal_heading(225.0) == "NW"
    assert calculate_cardinal_heading(270.0) == "N"
    assert calculate_cardinal_heading(315.0) == "NE"
    assert calculate_cardinal_heading(45.0, is_stationary=True) == "STATIONARY"


def test_speed_formatting_honest_reporting():
    # Stationary
    assert format_speed_label(0.5, is_stationary=True) == "Stationary"
    
    # Relative speed
    assert format_speed_label(25.0, is_stationary=False) == "Slow Moving (Rel)"
    assert format_speed_label(60.0, is_stationary=False) == "Moderate (Rel)"
    assert format_speed_label(150.0, is_stationary=False) == "Fast Moving (Rel)"
    
    # Calibrated physical speed
    assert format_speed_label(100.0, is_stationary=False, calibrated_meters_per_pixel=0.024) == "~2.4 m/s (calibrated)"


def test_movement_vector_calculation():
    # Moving East (x increasing, y constant)
    traj = [(100.0, 100.0), (120.0, 100.0), (140.0, 100.0)]
    mv = calculate_movement_vector(traj, fps=30.0)
    assert mv.is_moving is True
    assert mv.cardinal_heading == "E"
    assert mv.distance_px == 40.0


def test_target_approach_detection():
    curr_pos = (100.0, 100.0)
    target_pos = (200.0, 100.0)  # East of current pos (0 deg)
    
    # Heading East (0 deg) -> Moving towards target
    assert is_moving_towards(curr_pos, 0.0, target_pos, tolerance_deg=30.0) is True
    
    # Heading West (180 deg) -> Moving away from target
    assert is_moving_towards(curr_pos, 180.0, target_pos, tolerance_deg=30.0) is False


def test_directional_tripwire_crossing():
    # Vertical tripwire line from (200, 0) to (200, 400)
    boundary = VirtualBoundary(
        boundary_id="TW-01",
        name="Perimeter Fence",
        pt1=(200.0, 0.0),
        pt2=(200.0, 400.0),
        severity=ZoneSeverity.CRITICAL,
    )
    
    # Crossing from West (150) to East (250)
    res_in = boundary.check_crossing((150.0, 200.0), (250.0, 200.0))
    assert res_in in ("inbound", "outbound")
    
    # Crossing opposite direction (250 to 150)
    res_out = boundary.check_crossing((250.0, 200.0), (150.0, 200.0))
    assert res_out in ("inbound", "outbound")
    assert res_in != res_out
    
    # Not crossing (staying on same side)
    assert boundary.check_crossing((100.0, 200.0), (150.0, 200.0)) is None


def test_deterministic_threat_scoring():
    # Normal / Nominal
    score, level, reasons = compute_threat_score()
    assert score == 0.0
    assert level == "NORMAL"
    
    # Single Restricted intrusion: +35 -> RESTRICTED
    score, level, reasons = compute_threat_score(has_restricted_intrusion=True)
    assert score == 35.0
    assert level in ("RESTRICTED", "ELEVATED")
    assert any("+35" in r for r in reasons)
    
    # Restricted (+35) + Tripwire (+30) + Night (+15) + Approach (+15) = 95 -> CRITICAL
    score, level, reasons = compute_threat_score(
        has_restricted_intrusion=True,
        has_tripwire_breach=True,
        has_night_movement=True,
        has_movement_towards_protected=True,
    )
    assert score == 95.0
    assert level == "CRITICAL"
    assert len(reasons) == 4


def test_anpr_prototype():
    anpr = get_anpr_processor()
    assert anpr.is_vehicle("car") is True
    assert anpr.is_vehicle("person") is False
    
    # Synthetic frame test
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[100:300, 100:400] = 120  # Vehicle body
    frame[240:270, 200:300] = 220  # Plate candidate
    
    result = anpr.process_vehicle(frame, bounding_box=[100, 100, 400, 300], object_class="car", vehicle_id="101")
    assert result is not None
    assert result.vehicle_class == "car"
    assert len(result.plate_bounding_box) == 4
    assert result.confidence > 0.0


def test_face_analytics_prototype_non_biometric():
    face_proc = get_face_processor()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    result = face_proc.detect_face_in_person(frame, person_box=[50, 50, 200, 400], track_id="27")
    assert result is not None
    assert result.face_detected is True
    # Verify non-biometric identity claim
    assert "Non-Biometric" in result.identity_claim


def test_multi_camera_correlation():
    correlator = get_correlator()
    t0 = datetime(2026, 8, 28, 22, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 28, 22, 0, 8, tzinfo=timezone.utc)  # 8s later
    
    correlator.record_exit(
        camera_id="CAM-01",
        zone_name="Border Perimeter Buffer Strip",
        track_id="27",
        object_class="person",
        exit_time=t0,
    )
    
    event = correlator.check_correlation_on_entry(
        camera_id="CAM-02",
        zone_name="Gate Approach Corridor",
        track_id="35",
        object_class="person",
        entry_time=t1,
    )
    
    assert event is not None
    assert event.source_camera == "CAM-01"
    assert event.target_camera == "CAM-02"
    assert "Probable cross-camera event correlation" in event.correlation_label
    assert event.time_delta_seconds == 8.0


def test_camera_health_stream_frozen():
    frame1 = np.ones((480, 640, 3), dtype=np.uint8) * 128
    frame2 = np.ones((480, 640, 3), dtype=np.uint8) * 128  # Exactly identical frame
    
    diag = evaluate_optical_quality(frame2, camera_id="CAM-01", prev_image=frame1)
    assert diag.status == SignalQualityStatus.STREAM_FROZEN
    assert diag.is_tampered_or_degraded is True
    assert "CAMERA HEALTH WARNING" in diag.diagnosis_message


def test_night_movement_condition():
    # 23:00 (11 PM) -> Night
    t_night = datetime(2026, 8, 28, 23, 15, 0, tzinfo=timezone.utc)
    assert is_night_movement_condition(t_night) is True
    
    # 14:00 (2 PM) Bright -> Day
    t_day = datetime(2026, 8, 28, 14, 0, 0, tzinfo=timezone.utc)
    assert is_night_movement_condition(t_day, brightness_mean=120.0) is False
    
    # 14:00 (2 PM) Dark sensor (blackout) -> Night / Low Light
    assert is_night_movement_condition(t_day, brightness_mean=20.0) is True


@pytest.mark.asyncio
async def test_grounded_copilot_queries():
    from backend.database import init_db
    await init_db()
    assistant = SurveillanceAssistant()
    
    # 1. Intent refusal check (Biometric identity refusal)
    resp = await assistant.process_query("Who is Track 27? Give me his real name")
    assert resp.grounding_status == "refusal"
    assert "CAPABILITY REFUSAL" in resp.interpretation
    
    # 2. Threat causation query
    resp_threat = await assistant.process_query("Why is the sector threat score elevated?")
    assert resp_threat.grounding_status == "grounded"
    assert "Sector Threat Index" in resp_threat.observed_facts[0]
    
    # 3. Missing record query
    resp_missing = await assistant.process_query("Where did Track 99999 go?")
    assert resp_missing.grounding_status == "no_data"
