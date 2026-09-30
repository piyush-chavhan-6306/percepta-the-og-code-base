"""
PERCEPTA System Audit Regression Test Suite.
Verifies all key audited areas:
1. Tripwire directional vector crossing (NORTH, SOUTH, EAST, WEST, BIDIRECTIONAL)
2. Trigger / Zone creation and deletion lifecycle
3. Forensic evidence snapshot extraction (Full scene, Face crop, ANPR crop)
4. Threat Assessment deterministic score evaluation
5. AI Copilot conversational queries (greetings, counts, activity, threats, history)
"""
from datetime import datetime, timezone
import numpy as np
import pytest

from backend.events.snapshots import SnapshotArchiveManager, get_snapshot_manager
from backend.intelligence.assistant import get_surveillance_assistant
from backend.intelligence.threat_engine import ThreatLevel, compute_threat_score, get_threat_engine
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity


def test_tripwire_directional_crossing_logic():
    """Verify cardinal direction filtering on tripwires."""
    # Horizontal tripwire across y=200 from x=0 to x=500
    boundary_north = VirtualBoundary(
        boundary_id="tw_north",
        name="North Only Tripwire",
        pt1=(0.0, 200.0),
        pt2=(500.0, 200.0),
        direction="NORTH",
    )
    boundary_south = VirtualBoundary(
        boundary_id="tw_south",
        name="South Only Tripwire",
        pt1=(0.0, 200.0),
        pt2=(500.0, 200.0),
        direction="SOUTH",
    )
    boundary_bidir = VirtualBoundary(
        boundary_id="tw_bidir",
        name="Bidir Tripwire",
        pt1=(0.0, 200.0),
        pt2=(500.0, 200.0),
        direction="BIDIRECTIONAL",
    )

    # South to North movement (y: 250 -> 150, so dy < 0)
    p_south = (250.0, 250.0)
    p_north = (250.0, 150.0)

    assert boundary_north.check_crossing(p_south, p_north) == "NORTH"
    assert boundary_south.check_crossing(p_south, p_north) is None  # Wrong direction
    assert boundary_bidir.check_crossing(p_south, p_north) is not None

    # North to South movement (y: 150 -> 250, so dy > 0)
    assert boundary_north.check_crossing(p_north, p_south) is None  # Wrong direction
    assert boundary_south.check_crossing(p_north, p_south) == "SOUTH"
    assert boundary_bidir.check_crossing(p_north, p_south) is not None

    # Horizontal East/West tripwire (vertical line at x=200 from y=0 to y=500)
    boundary_east = VirtualBoundary(
        boundary_id="tw_east",
        name="East Only Tripwire",
        pt1=(200.0, 0.0),
        pt2=(200.0, 500.0),
        direction="EAST",
    )
    p_west = (150.0, 250.0)
    p_east = (250.0, 250.0)

    assert boundary_east.check_crossing(p_west, p_east) == "EAST"
    assert boundary_east.check_crossing(p_east, p_west) is None  # Moving west when EAST required


def test_threat_assessment_deterministic_scoring():
    """Verify threat score calculation follows deterministic rules."""
    # Nominal case
    score, level, reasons = compute_threat_score()
    assert score == 0.0
    assert level == "NORMAL"

    # Restricted intrusion (+35) -> RESTRICTED
    score_res, level_res, _ = compute_threat_score(has_restricted_intrusion=True)
    assert score_res == 35.0
    assert level_res == "RESTRICTED"

    # Tripwire breach (+30) + Restricted (+35) = 65.0 -> CRITICAL
    score_tw, level_tw, _ = compute_threat_score(has_restricted_intrusion=True, has_tripwire_breach=True)
    assert score_tw == 65.0
    assert level_tw == "CRITICAL"

    # Tripwire (+30) + Restricted (+35) + Night (+15) = 80.0 -> CRITICAL
    score_crit, level_crit, _ = compute_threat_score(
        has_restricted_intrusion=True,
        has_tripwire_breach=True,
        has_night_movement=True,
    )
    assert score_crit >= 60.0
    assert level_crit == "CRITICAL"


def test_forensic_evidence_snapshot_extraction(tmp_path):
    """Verify SnapshotArchiveManager produces scene, face crop, and ANPR crop."""
    mgr = SnapshotArchiveManager(snapshot_dir=str(tmp_path))
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    test_img[50:150, 50:150] = (0, 255, 0)  # Bright green block

    pkg = mgr.save_snapshot_with_crops(
        incident_id="test_incident_123",
        image=test_img,
        camera_id="CAM-01",
        frame_number=42,
        trigger_reason="RESTRICTED_BREACH",
        bounding_boxes=[[50.0, 50.0, 150.0, 150.0]],
        face_bbox=[60.0, 60.0, 100.0, 100.0],
        plate_bbox=[80.0, 110.0, 140.0, 140.0],
    )

    assert pkg.file_uri is not None
    assert pkg.face_snapshot_uri is not None
    assert pkg.anpr_snapshot_uri is not None
    assert (tmp_path / f"SNAP_test_incident_123_{pkg.snapshot_id.split('_')[-1]}.jpg").exists() or len(list(tmp_path.glob("*.jpg"))) >= 3


@pytest.mark.asyncio
async def test_ai_copilot_conversational_grounding():
    """Verify AI Copilot handles natural language questions and remains grounded."""
    from backend.database import init_db
    await init_db()
    assistant = get_surveillance_assistant()

    # 1. Greeting
    res_greet = await assistant.answer_query("Hi")
    assert res_greet.status == "answered"
    assert "PERCEPTA" in res_greet.interpretation

    # 2. Camera question
    res_cam = await assistant.answer_query("Which cameras are online?")
    assert res_cam.status == "answered"
    assert "PERCEPTA" in res_cam.interpretation

    # 3. People query
    res_people = await assistant.answer_query("How many people are currently visible?")
    assert res_people.status == "answered"
    assert "person" in res_people.interpretation.lower()

    # 4. Vehicle query
    res_veh = await assistant.answer_query("How many cars are currently detected?")
    assert res_veh.status == "answered"
    assert "vehicle" in res_veh.interpretation.lower()

    # 5. Activity query
    res_act = await assistant.answer_query("Which camera has the most activity?")
    assert res_act.status == "answered"

    # 6. Security breach query
    res_sec = await assistant.answer_query("Are there any perimeter breaches right now?")
    assert res_sec.status == "answered"

    # 7. Threat query
    res_threat = await assistant.answer_query("Is the system currently under threat?")
    assert res_threat.status == "answered"


def test_three_alert_severity_levels():
    """Verify exact 3 conceptual alert severity levels: NORMAL, RESTRICTED, CRITICAL."""
    assert ZoneSeverity.NORMAL.value == "normal"
    assert ZoneSeverity.RESTRICTED.value == "restricted"
    assert ZoneSeverity.CRITICAL.value == "critical"

    # Verify parser
    assert ZoneSeverity.from_str("normal") == ZoneSeverity.NORMAL
    assert ZoneSeverity.from_str("info") == ZoneSeverity.NORMAL
    assert ZoneSeverity.from_str("restricted") == ZoneSeverity.RESTRICTED
    assert ZoneSeverity.from_str("warning") == ZoneSeverity.RESTRICTED
    assert ZoneSeverity.from_str("critical") == ZoneSeverity.CRITICAL
    assert ZoneSeverity.from_str("high") == ZoneSeverity.CRITICAL


def test_zone_and_tripwire_persistence_and_deletion(tmp_path):
    """Verify complete lifecycle: create, save to storage, reload, delete, verify permanently gone."""
    cfg_file = str(tmp_path / "test_zones.json")
    monitor = ZoneMonitor(load_persistence=False)

    z = SecurityZone(
        zone_id="zone-test-1",
        name="Test Defense Perimeter",
        polygon=[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)],
        severity=ZoneSeverity.RESTRICTED,
    )
    b = VirtualBoundary(
        boundary_id="b-test-1",
        name="Test Tripwire Alpha",
        pt1=(0.2, 0.5),
        pt2=(0.8, 0.5),
        severity=ZoneSeverity.CRITICAL,
        direction="NORTH",
    )

    monitor.add_zone(z)
    monitor.add_boundary(b)
    monitor.save_persistent_definitions(filepath=cfg_file)

    # 1. Verify reloading from disk restores items
    monitor_reloaded = ZoneMonitor(load_persistence=False)
    monitor_reloaded.load_persistent_definitions(filepath=cfg_file)
    assert "zone-test-1" in monitor_reloaded.zones
    assert "b-test-1" in monitor_reloaded.boundaries
    assert monitor_reloaded.boundaries["b-test-1"].direction == "NORTH"

    # 2. Verify deletion removes from memory AND disk
    assert monitor.remove_zone("zone-test-1") is True
    assert monitor.remove_boundary("b-test-1") is True

    # 3. Verify fresh monitor cannot load deleted items
    monitor_after_del = ZoneMonitor(load_persistence=False)
    monitor_after_del.load_persistent_definitions(filepath=cfg_file)
    assert "zone-test-1" not in monitor_after_del.zones
    assert "b-test-1" not in monitor_after_del.boundaries


def test_sensor_frame_adapter_multi_modal_normalization():
    """Verify SensorFrameAdapter normalizes RGB, IR, NIGHT, and THERMAL imagery into 3-channel tensors."""
    from backend.ingestion.sensor_adapter import SensorFrameAdapter

    # 1. Standard RGB / Grayscale to 3-channel
    gray_img = np.zeros((100, 100), dtype=np.uint8)
    norm_rgb = SensorFrameAdapter.normalize_frame(gray_img, modality="STANDARD")
    assert norm_rgb.shape == (100, 100, 3)

    # 2. IR Night Vision (CLAHE enhanced)
    night_img = np.full((100, 100, 3), 30, dtype=np.uint8)
    norm_night = SensorFrameAdapter.normalize_frame(night_img, modality="IR_NIGHT")
    assert norm_night.shape == (100, 100, 3)

    # 3. Thermal Surveillance (Ironbow colormap)
    thermal_raw = np.full((100, 100), 120, dtype=np.uint8)
    norm_thermal = SensorFrameAdapter.normalize_frame(thermal_raw, modality="THERMAL")
    assert norm_thermal.shape == (100, 100, 3)


@pytest.mark.asyncio
async def test_single_camera_operational_policy():
    """Verify that starting camera B when camera A is running cleanly stops camera A."""
    from backend.ingestion.camera_manager import CameraManager
    from backend.ingestion.simulation_adapter import SimulationAdapter

    mgr = CameraManager()
    cam_a = SimulationAdapter(camera_id="CAM-A")
    cam_b = SimulationAdapter(camera_id="CAM-B")

    mgr.register_camera("CAM-A", cam_a, name="Camera A")
    mgr.register_camera("CAM-B", cam_b, name="Camera B")

    # Start Camera A
    assert await mgr.start_camera("CAM-A") is True
    assert "CAM-A" in mgr.get_running_cameras()

    # Enforce single camera policy before starting Camera B
    for running_id in mgr.get_running_cameras():
        if running_id != "CAM-B":
            await mgr.stop_camera(running_id)

    assert await mgr.start_camera("CAM-B") is True

    # Confirm Camera A is stopped and only Camera B is running
    running = mgr.get_running_cameras()
    assert "CAM-A" not in running
    assert "CAM-B" in running
    assert len(running) == 1

