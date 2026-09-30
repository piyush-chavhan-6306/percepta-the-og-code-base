"""
Unit Tests for Loitering Detection and Dwell Duration Monitoring.
Verifies that:
1. Presence below threshold generates ZERO loitering alerts.
2. Dwell duration exceeding threshold generates a loitering ZoneEvent and AlertEvent.
3. Alert debouncing suppresses continuous alert spam for dwelling tracks.
4. Exit and re-entry cleanly resets dwell clocks and state.
"""
from datetime import datetime, timedelta, timezone
import pytest

from backend.events.schema import SourceType
from backend.tracking.tracker import TrackedObject
from backend.zones.security_zone import (
    SecurityZone,
    ZoneMonitor,
    ZoneSeverity,
)


def _make_track(
    track_id: str,
    cx: float,
    cy: float,
    timestamp: datetime,
    object_class: str = "person",
) -> TrackedObject:
    return TrackedObject(
        track_id=track_id,
        object_class=object_class,
        confidence=0.92,
        bounding_box=[cx - 20, cy - 40, cx + 20, cy + 40],
        normalized_box=[0.1, 0.1, 0.2, 0.2],
        frame_number=1,
        timestamp=timestamp,
        center_x=cx,
        center_y=cy,
    )


def test_short_presence_generates_zero_loitering_alerts():
    polygon = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]
    zone = SecurityZone(
        zone_id="restricted_zone_loiter",
        name="Sensitive Area",
        polygon=polygon,
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=10.0,
    )
    monitor = ZoneMonitor(zones=[zone])

    t0 = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    # Frame 1: Enters zone at t=0s -> Entry alert, but ZERO loitering alerts
    t1 = _make_track("tr_1", 200.0, 200.0, timestamp=t0)
    z_evs1, a_evs1 = monitor.evaluate_tracks([t1], camera_id="cam_01")
    assert len(z_evs1) == 1
    assert z_evs1[0].transition == "entered"
    assert len(a_evs1) == 1
    assert "SECURITY ALERT" in a_evs1[0].message
    assert "LOITERING" not in a_evs1[0].message

    # Frame 2: Dwells at t=3s (3s < 10s threshold) -> ZERO events
    t2 = _make_track("tr_1", 205.0, 205.0, timestamp=t0 + timedelta(seconds=3))
    z_evs2, a_evs2 = monitor.evaluate_tracks([t2], camera_id="cam_01")
    assert len(z_evs2) == 0
    assert len(a_evs2) == 0

    # Frame 3: Dwells at t=8s (8s < 10s threshold) -> ZERO events
    t3 = _make_track("tr_1", 210.0, 210.0, timestamp=t0 + timedelta(seconds=8))
    z_evs3, a_evs3 = monitor.evaluate_tracks([t3], camera_id="cam_01")
    assert len(z_evs3) == 0
    assert len(a_evs3) == 0


def test_exceeding_loitering_threshold_triggers_alert_and_debounces():
    polygon = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]
    zone = SecurityZone(
        zone_id="restricted_zone_loiter",
        name="Sensitive Area",
        polygon=polygon,
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=10.0,
        loitering_debounce_seconds=30.0,
    )
    monitor = ZoneMonitor(zones=[zone])

    t0 = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    # Frame 1: Entry at t=0s
    t1 = _make_track("tr_1", 200.0, 200.0, timestamp=t0)
    monitor.evaluate_tracks([t1], camera_id="cam_01")

    # Frame 2: Reaches t=11s (11s >= 10s threshold) -> LOITERING ALERT FIRES
    t2 = _make_track("tr_1", 205.0, 205.0, timestamp=t0 + timedelta(seconds=11))
    z_evs2, a_evs2 = monitor.evaluate_tracks([t2], camera_id="cam_01")

    assert len(z_evs2) == 1
    assert z_evs2[0].transition == "loitering"
    assert z_evs2[0].dwell_duration_seconds >= 10.0
    assert len(a_evs2) == 1
    assert "LOITERING ALERT" in a_evs2[0].message
    assert a_evs2[0].severity == "RESTRICTED"

    # Frame 3: Next second t=12s -> DEBOUNCED! ZERO NEW ALERTS
    t3 = _make_track("tr_1", 206.0, 206.0, timestamp=t0 + timedelta(seconds=12))
    z_evs3, a_evs3 = monitor.evaluate_tracks([t3], camera_id="cam_01")
    assert len(z_evs3) == 0
    assert len(a_evs3) == 0

    # Frame 4: Next frame at t=25s (< 30s debounce) -> ZERO NEW ALERTS
    t4 = _make_track("tr_1", 207.0, 207.0, timestamp=t0 + timedelta(seconds=25))
    z_evs4, a_evs4 = monitor.evaluate_tracks([t4], camera_id="cam_01")
    assert len(z_evs4) == 0
    assert len(a_evs4) == 0

    # Frame 5: Frame at t=45s (34s after last alert >= 30s debounce) -> SECOND LOITERING ALERT FIRES
    t5 = _make_track("tr_1", 208.0, 208.0, timestamp=t0 + timedelta(seconds=45))
    z_evs5, a_evs5 = monitor.evaluate_tracks([t5], camera_id="cam_01")
    assert len(z_evs5) == 1
    assert z_evs5[0].transition == "loitering"
    assert len(a_evs5) == 1


def test_zone_exit_and_reentry_resets_dwell_timer():
    polygon = [(100.0, 100.0), (300.0, 100.0), (300.0, 300.0), (100.0, 300.0)]
    zone = SecurityZone(
        zone_id="restricted_zone_loiter",
        name="Sensitive Area",
        polygon=polygon,
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=10.0,
    )
    monitor = ZoneMonitor(zones=[zone])

    t0 = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Enters at t=0s
    monitor.evaluate_tracks([_make_track("tr_1", 200.0, 200.0, timestamp=t0)], camera_id="cam_01")

    # 2. Dwells for 5s (below threshold)
    monitor.evaluate_tracks([_make_track("tr_1", 200.0, 200.0, timestamp=t0 + timedelta(seconds=5))], camera_id="cam_01")

    # 3. Exits zone at t=6s
    z_evs_exit, _ = monitor.evaluate_tracks([_make_track("tr_1", 50.0, 50.0, timestamp=t0 + timedelta(seconds=6))], camera_id="cam_01")
    assert len(z_evs_exit) == 1
    assert z_evs_exit[0].transition == "exited"
    assert z_evs_exit[0].dwell_duration_seconds == 6.0

    # 4. Re-enters at t=20s -> New entry, clock resets to 0
    t_reentry = t0 + timedelta(seconds=20)
    z_evs_re, _ = monitor.evaluate_tracks([_make_track("tr_1", 200.0, 200.0, timestamp=t_reentry)], camera_id="cam_01")
    assert len(z_evs_re) == 1
    assert z_evs_re[0].transition == "entered"

    # 5. At t=25s (5s after re-entry, < 10s threshold) -> ZERO loitering alerts
    z_evs_5s, a_evs_5s = monitor.evaluate_tracks([_make_track("tr_1", 200.0, 200.0, timestamp=t_reentry + timedelta(seconds=5))], camera_id="cam_01")
    assert len(z_evs_5s) == 0
    assert len(a_evs_5s) == 0

    # 6. At t=31s (11s after re-entry >= 10s threshold) -> Loitering alert fires
    z_evs_11s, a_evs_11s = monitor.evaluate_tracks([_make_track("tr_1", 200.0, 200.0, timestamp=t_reentry + timedelta(seconds=11))], camera_id="cam_01")
    assert len(z_evs_11s) == 1
    assert z_evs_11s[0].transition == "loitering"
    assert len(a_evs_11s) == 1
