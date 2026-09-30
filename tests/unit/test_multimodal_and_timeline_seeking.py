"""
Unit Tests for Multi-Modal Surveillance, Thermal Processor, Evidence Package Snapshots, and Timeline Seeking.
Aligned with SIH Problem Statement SIH26187.
"""
from datetime import datetime, timezone
import numpy as np
import pytest

from backend.detection.thermal_processor import ThermalPalette, ThermalProcessor, get_thermal_processor
from backend.events.schema import AlertEvent, SourceType
from backend.events.snapshots import BestEvidenceFrameSelector, SnapshotArchiveManager, get_snapshot_manager
from backend.events.store import get_event_store
from backend.database import init_db
from backend.ingestion.camera_manager import CameraManager, get_camera_manager
from backend.ingestion.video_adapter import VideoFileAdapter


@pytest.mark.asyncio
async def test_thermal_processor_colormaps_and_signatures():
    proc = get_thermal_processor()

    # Create synthetic 8-bit thermal frame (200x200 with bright hot spots)
    thermal_raw = np.zeros((200, 200), dtype=np.uint8)
    # Add high-heat body region (person signature)
    thermal_raw[80:140, 90:110] = 235
    # Add engine heat signature
    thermal_raw[40:70, 40:80] = 245

    # 1. Test Ironbow colormap rendering
    ironbow = proc.render_thermal_colormap(thermal_raw, palette=ThermalPalette.IRONBOW)
    assert ironbow.shape == (200, 200, 3)
    assert ironbow.dtype == np.uint8

    # 2. Test White-Hot colormap rendering
    white_hot = proc.render_thermal_colormap(thermal_raw, palette=ThermalPalette.WHITE_HOT)
    assert white_hot.shape == (200, 200, 3)

    # 3. Test Black-Hot colormap rendering
    black_hot = proc.render_thermal_colormap(thermal_raw, palette=ThermalPalette.BLACK_HOT)
    assert black_hot.shape == (200, 200, 3)

    # 4. Extract thermal hotspots
    hotspots = proc.extract_thermal_signatures(thermal_raw, heat_threshold=180.0, min_area=50)
    assert len(hotspots) >= 2
    assert any(h.is_high_heat for h in hotspots)
    assert any(h.max_intensity >= 230.0 for h in hotspots)


@pytest.mark.asyncio
async def test_best_evidence_selector_and_multi_snapshot(tmp_path):
    mgr = SnapshotArchiveManager(snapshot_dir=str(tmp_path / "test_snaps"))

    # Create synthetic frame
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # Add high contrast pattern so Laplacian sharpness > 0
    img[100:200, 100:200] = 255
    img[200:300, 200:300] = 128

    # Test sharpness scoring
    sharpness = BestEvidenceFrameSelector.calculate_sharpness(img)
    assert sharpness > 0.0

    # Test composite frame score
    quality_score = BestEvidenceFrameSelector.score_frame_quality(
        img,
        confidence=0.95,
        bbox=[100.0, 100.0, 300.0, 300.0],
    )
    assert 0.0 <= quality_score <= 100.0

    # Test saving multi-evidence package (Full Scene + Face Crop + ANPR Plate Crop)
    pkg = await mgr.save_multi_evidence_package_async(
        incident_id="INC_TEST_001",
        image=img,
        camera_id="CAM-01",
        frame_number=142,
        trigger_reason="PERIMETER_BREACH",
        bounding_boxes=[[100.0, 100.0, 300.0, 300.0]],
        face_bbox=[100.0, 100.0, 150.0, 150.0],
        plate_bbox=[200.0, 250.0, 280.0, 290.0],
        confidence=0.96,
        modality="STANDARD",
    )

    assert pkg.snapshot_id.startswith("SNAP_INC_TEST_001")
    assert pkg.file_uri.endswith(".jpg")
    assert pkg.face_snapshot_uri is not None and "FACE_" in pkg.face_snapshot_uri
    assert pkg.anpr_snapshot_uri is not None and "ANPR_" in pkg.anpr_snapshot_uri
    assert pkg.confidence == 0.96
    assert pkg.modality == "STANDARD"


@pytest.mark.asyncio
async def test_camera_modality_registration():
    mgr = CameraManager()
    adapter = VideoFileAdapter(camera_id="CAM-IR-TEST", video_path="nonexistent.mp4", modality="IR_NIGHT")
    rec = mgr.register_camera(
        camera_id="CAM-IR-TEST",
        adapter=adapter,
        name="Sector Night Infrared",
        modality="IR_NIGHT",
    )

    assert rec.modality == "IR_NIGHT"
    data = rec.to_dict()
    assert data["modality"] == "IR_NIGHT"


@pytest.mark.asyncio
async def test_timeline_seeking_persistence_and_query():
    await init_db()
    store = get_event_store()

    # Record AlertEvent with evidence and timeline offsets
    alert = AlertEvent(
        camera_id="CAM_TIMELINE_TEST",
        track_id="42",
        confidence=0.97,
        source=SourceType.SIMULATION,
        timestamp=datetime.now(timezone.utc),
        severity="CRITICAL",
        message="CRITICAL: Unauthorized vehicle breach on perimeter",
        threat_score=85.0,
        threat_level="CRITICAL",
        threat_reasons=["+35 Restricted Intrusion", "+30 Tripwire Breach", "+20 Night Movement"],
        causal_chain=["1. Target detected", "2. Tripwire breached", "3. Threat score = 85"],
        evidence_snapshot_uri="/api/evidence/snapshots/file/SNAP_DEMO.jpg",
        face_snapshot_uri="/api/evidence/snapshots/file/FACE_DEMO.jpg",
        anpr_snapshot_uri="/api/evidence/snapshots/file/ANPR_DEMO.jpg",
        best_frame_number=240,
        modality="IR_NIGHT",
        timeline_offset_sec=14.5,
    )
    await store.record_event(alert)

    # Verify query
    alerts = await store.get_alerts(camera_id="CAM_TIMELINE_TEST", limit=10)
    assert len(alerts) >= 1
    target = [a for a in alerts if a["event_id"] == str(alert.event_id)][0]
    assert target["camera_id"] == "CAM_TIMELINE_TEST"
    assert target["track_id"] == "42"
