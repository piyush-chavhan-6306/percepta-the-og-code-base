"""
Unit Tests for Security Zones, Virtual Boundaries, and Zone Monitoring.
Tests polygon point-in-polygon containment, boundary crossing line intersections,
state transitions (entered, dwelling, exited, crossed), and presence vs. intrusion alerting.
"""
from datetime import datetime, timezone
import pytest

from backend.events.schema import SourceType
from backend.tracking.tracker import TrackedObject
from backend.zones.security_zone import (
    SecurityZone,
    VirtualBoundary,
    ZoneMonitor,
    ZoneSeverity,
)


def _make_track(track_id: str, cx: float, cy: float, object_class: str = "person") -> TrackedObject:
    return TrackedObject(
        track_id=track_id,
        object_class=object_class,
        confidence=0.9,
        bounding_box=[cx - 20, cy - 40, cx + 20, cy + 40],
        normalized_box=[0.1, 0.1, 0.2, 0.2],
        frame_number=1,
        timestamp=datetime.now(timezone.utc),
        center_x=cx,
        center_y=cy,
    )


def test_polygon_security_zone_containment():
    # Rectangular zone from (100, 100) to (300, 300)
    polygon = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]
    zone = SecurityZone(zone_id="zone_restricted_1", name="Alpha Perimeter", polygon=polygon)

    # Inside
    assert zone.contains_point((200.0, 200.0)) is True
    assert zone.contains_point((150.0, 150.0)) is True

    # Outside
    assert zone.contains_point((50.0, 50.0)) is False
    assert zone.contains_point((400.0, 200.0)) is False
    assert zone.contains_point((200.0, 350.0)) is False


def test_virtual_boundary_line_crossing():
    # Horizontal border line from (0, 200) to (640, 200)
    boundary = VirtualBoundary(
        boundary_id="line_border_north",
        name="North Border Line",
        pt1=(0.0, 200.0),
        pt2=(640.0, 200.0),
        severity=ZoneSeverity.CRITICAL,
    )

    # Top-to-bottom crossing (e.g. y: 150 -> 250)
    crossing1 = boundary.check_crossing(prev_point=(320.0, 150.0), curr_point=(320.0, 250.0))
    assert crossing1 is not None

    # Bottom-to-top crossing (e.g. y: 250 -> 150)
    crossing2 = boundary.check_crossing(prev_point=(320.0, 250.0), curr_point=(320.0, 150.0))
    assert crossing2 is not None

    # Parallel movement on one side (no crossing)
    no_crossing = boundary.check_crossing(prev_point=(100.0, 150.0), curr_point=(200.0, 150.0))
    assert no_crossing is None


def test_zone_monitor_entry_dwelling_and_exit_transitions():
    polygon = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]
    zone = SecurityZone(
        zone_id="restricted_zone_1",
        name="Restricted Zone 1",
        polygon=polygon,
        severity=ZoneSeverity.RESTRICTED,
    )
    monitor = ZoneMonitor(zones=[zone])

    # Frame 1: Track 10 is outside (50, 50) -> No events
    t10_f1 = _make_track("10", 50.0, 50.0)
    zone_evs1, alert_evs1 = monitor.evaluate_tracks([t10_f1], camera_id="cam_01")
    assert len(zone_evs1) == 0
    assert len(alert_evs1) == 0

    # Frame 2: Track 10 moves inside (200, 200) -> TRANSITION: ENTERED + ALERT
    t10_f2 = _make_track("10", 200.0, 200.0)
    zone_evs2, alert_evs2 = monitor.evaluate_tracks([t10_f2], camera_id="cam_01")
    assert len(zone_evs2) == 1
    assert zone_evs2[0].transition == "entered"
    assert zone_evs2[0].zone_id == "restricted_zone_1"
    assert len(alert_evs2) == 1
    assert "SECURITY ALERT" in alert_evs2[0].message

    # Frame 3: Track 10 stays inside (210, 210) -> DWELLING: ZERO NEW ALERTS
    t10_f3 = _make_track("10", 210.0, 210.0)
    zone_evs3, alert_evs3 = monitor.evaluate_tracks([t10_f3], camera_id="cam_01")
    assert len(zone_evs3) == 0
    assert len(alert_evs3) == 0  # CRITICAL: No continuous spam while dwelling!

    # Frame 4: Track 10 moves outside (350, 200) -> TRANSITION: EXITED (No alert)
    t10_f4 = _make_track("10", 350.0, 200.0)
    zone_evs4, alert_evs4 = monitor.evaluate_tracks([t10_f4], camera_id="cam_01")
    assert len(zone_evs4) == 1
    assert zone_evs4[0].transition == "exited"
    assert len(alert_evs4) == 0


def test_zone_monitor_virtual_boundary_crossing_event():
    boundary = VirtualBoundary(
        boundary_id="line_border_1",
        name="Border Line Sector 4",
        pt1=(100.0, 200.0),
        pt2=(500.0, 200.0),
        severity=ZoneSeverity.CRITICAL,
    )
    monitor = ZoneMonitor(boundaries=[boundary])

    # Frame 1: Track 5 at (300, 180) - North side
    t5_f1 = _make_track("5", 300.0, 180.0)
    z_evs1, a_evs1 = monitor.evaluate_tracks([t5_f1], camera_id="cam_01")
    assert len(z_evs1) == 0
    assert len(a_evs1) == 0

    # Frame 2: Track 5 moves to (300, 220) - South side (Crosses the line)
    t5_f2 = _make_track("5", 300.0, 220.0)
    z_evs2, a_evs2 = monitor.evaluate_tracks([t5_f2], camera_id="cam_01")
    assert len(z_evs2) == 1
    assert z_evs2[0].transition == "crossed"
    assert z_evs2[0].zone_id == "line_border_1"
    assert len(a_evs2) == 1
    assert "BORDER BREACH" in a_evs2[0].message


def test_virtual_boundary_cardinal_direction_filtering():
    """Verify that tripwires with explicit cardinal direction only trigger for matching movement vectors."""
    # Horizontal tripwire at y=300, requiring SOUTH movement (dy > 0)
    south_boundary = VirtualBoundary(
        boundary_id="south_wire",
        name="Southbound Tripwire",
        pt1=(50.0, 300.0),
        pt2=(550.0, 300.0),
        direction="SOUTH",
    )

    # Moving SOUTH (from y=250 down to y=350) -> Should trigger
    res_south = south_boundary.check_crossing(prev_point=(200.0, 250.0), curr_point=(200.0, 350.0))
    assert res_south == "SOUTH"

    # Moving NORTH (from y=350 up to y=250) -> Must NOT trigger
    res_north = south_boundary.check_crossing(prev_point=(200.0, 350.0), curr_point=(200.0, 250.0))
    assert res_north is None

    # Vertical tripwire at x=400, requiring EAST movement (dx > 0)
    east_boundary = VirtualBoundary(
        boundary_id="east_wire",
        name="Eastbound Tripwire",
        pt1=(400.0, 50.0),
        pt2=(400.0, 550.0),
        direction="EAST",
    )

    # Moving EAST (from x=350 to x=450) -> Should trigger
    assert east_boundary.check_crossing(prev_point=(350.0, 200.0), curr_point=(450.0, 200.0)) == "EAST"

    # Moving WEST (from x=450 to x=350) -> Must NOT trigger
    assert east_boundary.check_crossing(prev_point=(450.0, 200.0), curr_point=(350.0, 200.0)) is None


def test_virtual_boundary_per_track_debounce():
    """Verify that multiple crossing evaluations in rapid succession are debounced per track."""
    boundary = VirtualBoundary(
        boundary_id="wire_debounce",
        name="Debounced Tripwire",
        pt1=(0.0, 200.0),
        pt2=(600.0, 200.0),
        debounce_seconds=5.0,
    )
    monitor = ZoneMonitor(boundaries=[boundary])

    # Frame 1: Track 99 at (300, 180)
    t99_f1 = _make_track("99", 300.0, 180.0)
    monitor.evaluate_tracks([t99_f1], camera_id="cam_01")

    # Frame 2: Track 99 crosses at (300, 220) -> Should alert
    t99_f2 = _make_track("99", 300.0, 220.0)
    _, a_evs2 = monitor.evaluate_tracks([t99_f2], camera_id="cam_01")
    assert len(a_evs2) == 1

    # Frame 3: Track 99 hovers and crosses back at (300, 190) immediately -> Debounced, no alert!
    t99_f3 = _make_track("99", 300.0, 190.0)
    _, a_evs3 = monitor.evaluate_tracks([t99_f3], camera_id="cam_01")
    assert len(a_evs3) == 0
