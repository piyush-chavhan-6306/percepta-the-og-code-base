"""
Integration Tests for Tracking, Movement, and Security Zone Intelligence Pipeline.
Verifies the complete flow from FrameData -> YOLOv8n -> ByteTrack -> ZoneMonitor -> EventStore -> EventBus -> REST Replay.
"""
from datetime import datetime, timezone
import json
import httpx
import numpy as np
import pytest
from httpx import ASGITransport

from backend.database import init_db
from backend.detection.detector import DetectionResult, ObjectDetector
from backend.events.bus import get_event_bus
from backend.events.schema import EventType, SourceType
from backend.events.store import EventStore, get_event_store
from backend.ingestion.adapter import FrameData
from backend.main import create_app
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity


@pytest.mark.asyncio
async def test_full_pipeline_yolo_to_bytetrack_to_eventstore_to_replay():
    """
    End-to-end integration test:
    Feed sequential simulated frames with a moving target -> YOLO -> Tracker -> Zone Monitor -> SQLite -> REST API.
    """
    await init_db()
    event_store = get_event_store()
    event_bus = get_event_bus()

    # Track received bus events
    bus_events = []
    async def _bus_handler(ev):
        bus_events.append(ev)
    await event_bus.subscribe(_bus_handler)

    # Setup zones and boundary
    zone = SecurityZone(
        zone_id="restricted_alpha",
        name="Sector Alpha Restricted",
        polygon=[(150.0, 150.0), (350.0, 150.0), (350.0, 350.0), (150.0, 350.0)],
        severity=ZoneSeverity.RESTRICTED,
    )
    boundary = VirtualBoundary(
        boundary_id="line_bravo",
        name="Perimeter Fence Bravo",
        pt1=(0.0, 250.0),
        pt2=(640.0, 250.0),
        severity=ZoneSeverity.CRITICAL,
    )

    zone_monitor = ZoneMonitor(zones=[zone], boundaries=[boundary], event_store=event_store)
    detector = ObjectDetector()
    tracker = ByteTrackTracker()

    pipeline = TrackingPipeline(
        detector=detector,
        tracker=tracker,
        zone_monitor=zone_monitor,
        event_store=event_store,
        emit_tracking_events=True,
        # Assert the full per-frame telemetry contract. Production sampling
        # (every Nth frame per track) is a volume control, not a schema change.
        tracking_event_interval_frames=1,
    )
    pipeline.initialize()

    # Create 3 frames moving from (100, 100) -> (200, 200) inside zone -> (200, 300) crossing line
    # For deterministic testing, we can synthesize a person patch or mock detector detection
    camera_id = f"cam_integ_{int(datetime.now().timestamp())}"

    # Generate a realistic continuous trajectory of 6 frames:
    # Starts outside zone at (120, 120), moves into zone at (160, 160) -> (200, 200), then crosses line y=250 at (200, 260)
    frames_data = []
    dets_data = []
    
    positions = [
        (100.0, 100.0, 160.0, 160.0),  # Frame 1: center (130, 130) - outside zone
        (115.0, 120.0, 175.0, 180.0),  # Frame 2: center (145, 150) - outside zone
        (130.0, 140.0, 190.0, 200.0),  # Frame 3: center (160, 170) - inside zone [(150,150) to (350,350)]
        (145.0, 165.0, 205.0, 225.0),  # Frame 4: center (175, 195) - dwelling inside zone
        (160.0, 190.0, 220.0, 250.0),  # Frame 5: center (190, 220) - north of line y=250
        (175.0, 215.0, 235.0, 275.0),  # Frame 6: center (205, 245) - north of line y=250
        (190.0, 240.0, 250.0, 300.0),  # Frame 7: center (220, 270) - south of line y=250 (crossed!)
    ]

    for idx, (x1, y1, x2, y2) in enumerate(positions, start=1):
        f = FrameData(
            camera_id=camera_id,
            frame_number=idx,
            timestamp=datetime.now(timezone.utc),
            image=np.zeros((480, 640, 3), dtype=np.uint8),
            width=640,
            height=480,
            fps=30.0,
            source=SourceType.SIMULATION,
        )
        d = [DetectionResult(0, "person", 0.95, [x1, y1, x2, y2], [x1 / 640, y1 / 480, x2 / 640, y2 / 480])]
        frames_data.append(f)
        dets_data.append(d)

    results = []
    for idx in range(len(frames_data)):
        with pytest.MonkeyPatch.context() as m:
            m.setattr(pipeline.detector, "detect", lambda img, i=idx: dets_data[i])
            res = await pipeline.process_frame(frames_data[idx])
            results.append(res)

    # Assert tracking maintained persistent track ID across all frames
    for r in results:
        assert len(r.tracks) == 1
    t_id = results[0].tracks[0].track_id
    for r in results:
        assert r.tracks[0].track_id == t_id

    # Frame 3: Entered zone
    assert any(ze.transition == "entered" for ze in results[2].zone_events)
    assert len(results[2].alert_events) == 1

    # Frame 4: Dwelling inside zone -> No new alert
    assert len(results[3].alert_events) == 0

    # Frame 7: Crossed boundary line (y: 245 -> 270 across y=250)
    assert any(ze.transition == "crossed" for ze in results[6].zone_events)
    assert len(results[6].alert_events) == 1

    # REST API Replay verification
    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/events?camera_id={camera_id}")
        assert resp.status_code == 200
        resp_data = resp.json()
        events_list = resp_data["events"]
        assert len(events_list) >= 5  # Tracking + Zone + Alert events

        types = [e["event_type"] for e in events_list]
        assert "TRACKING" in types
        assert "ZONE" in types
        assert "ALERT" in types

        # Validate tracking event payload
        track_evs = [e for e in events_list if e["event_type"] == "TRACKING"]
        assert len(track_evs) >= 3
        first_track_payload = json.loads(track_evs[0]["payload"])
        assert "position" in first_track_payload
        assert "velocity" in first_track_payload
        assert first_track_payload["track_id"] == t_id
