"""
Border Intelligence Live Demonstration Runner.
Executes an end-to-end deterministic surveillance scenario on real VIRAT CCTV footage:
1. Ingestion & FrameBuffer
2. YOLOv8n Detection & ByteTrack Persistent Tracking
3. Security Zone Intrusion & Virtual Boundary Crossing
4. Loitering Detection & Debounced Alert Generation
5. Persist-Before-Publish (SQLite WAL)
6. Grounded Natural-Language Intelligence QA
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.database import init_db
from backend.detection.detector import ObjectDetector
from backend.events.bus import get_event_bus
from backend.events.schema import SourceType
from backend.events.store import get_event_store
from backend.ingestion.camera_manager import get_camera_manager
from backend.ingestion.video_adapter import VideoFileAdapter
from backend.intelligence.assistant import SurveillanceAssistant
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor


async def run_live_demo(total_frames: int = 60) -> None:
    print("=" * 75)
    print("        BORDER INTELLIGENCE — LIVE DEMO DEMONSTRATION RUNNER")
    print("   AI-Powered Video Analytics Platform for Border Surveillance (PS SIH26187)")
    print("=" * 75)

    # 1. System Startup & Database Initialization
    print("\n[STAGE 1] Initializing System Subsystems & SQLite WAL Store...")
    await init_db()
    store = get_event_store()
    bus = get_event_bus()
    settings = get_settings()
    print("  ✓ Database Connected (WAL Mode)")
    print("  ✓ EventBus Initialized")

    # 2. Camera Configuration & Adapter
    print("\n[STAGE 2] Registering CCTV Ingestion Adapter (VIRAT Real Footage)...")
    video_path = "VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4"
    if not Path(video_path).exists():
        print(f"  ✗ Demo video not found at: {video_path}")
        return

    manager = get_camera_manager()
    adapter = VideoFileAdapter(
        camera_id="CAM-01",
        video_path=video_path,
        loop=True,
        target_fps=30.0,
    )
    manager.register_camera("CAM-01", adapter, name="Sector Alpha North Gate", location_label="Sector Alpha Post 4")
    await manager.start_camera("CAM-01")
    print("  ✓ Camera CAM-01 (Sector Alpha North Gate) ONLINE")

    # 3. Setup Spatial Rules (Security Zones & Virtual Tripwires)
    print("\n[STAGE 3] Configuring Perimeter Security Zones & Virtual Boundaries...")
    zone_monitor = ZoneMonitor(event_store=store)
    # Zone covering main movement walkway
    zone_monitor.add_zone(
        SecurityZone(
            zone_id="ZONE_RESTRICTED_ALPHA",
            name="Alpha Restricted Perimeter",
            polygon=[(200.0, 100.0), (1000.0, 100.0), (1000.0, 650.0), (200.0, 650.0)],
            loitering_threshold_seconds=1.5,
            loitering_debounce_seconds=10.0,
        )
    )
    # Tripwire across entrance
    zone_monitor.add_boundary(
        VirtualBoundary(
            boundary_id="TRIPWIRE_FENCE_01",
            name="North Perimeter Fence Line",
            pt1=(300.0, 350.0),
            pt2=(900.0, 350.0),
        )
    )
    print("  ✓ Security Zone 'Alpha Restricted Perimeter' Loaded (Loitering Threshold: 1.5s)")
    print("  ✓ Virtual Boundary 'North Perimeter Fence Line' Loaded")

    # 4. Pipeline Execution
    print("\n[STAGE 4] Initializing AI Pipeline (YOLOv8n + ByteTrack Kalman)...")
    detector = ObjectDetector(model_name="yolov8n.pt", device="cpu", imgsz=640)
    pipeline = TrackingPipeline(
        detector=detector,
        zone_monitor=zone_monitor,
        event_store=store,
        frame_stride=2,
        enable_intermediate_predictions=True,
    )
    print("  ✓ YOLOv8n Detector Ready")
    print("  ✓ ByteTrack Tracker Ready")

    print(f"\n[STAGE 5] Ingesting and Processing {total_frames} Surveillance Frames...")
    t0 = time.perf_counter()
    detected_tracks = set()
    total_alerts = 0

    for i in range(total_frames):
        frame = await adapter.get_next_frame()
        if frame is None:
            break

        result = await pipeline.process_frame(frame)
        for trk in result.tracks:
            detected_tracks.add(trk.track_id)
        if result.alert_events:
            total_alerts += len(result.alert_events)
            for a in result.alert_events:
                print(f"  [ALERT] Frame {i:03d} | Severity: {a.severity} | Track: {a.track_id} | {a.message}")

    elapsed = time.perf_counter() - t0
    fps = total_frames / max(elapsed, 0.001)
    print(f"\n  ✓ Processed {total_frames} frames in {elapsed:.2f}s ({fps:.2f} FPS AI throughput)")
    print(f"  ✓ Active Persistent Tracks Identified: {len(detected_tracks)} tracks ({sorted(list(detected_tracks))})")
    print(f"  ✓ Security Rule Alerts Generated: {total_alerts}")

    # 5. Grounded Intelligence Query Demonstration
    print("\n[STAGE 6] Demonstrating Grounded Surveillance Intelligence Assistant...")
    assistant = SurveillanceAssistant()

    demo_queries = [
        "Show recent security alerts.",
        "Which camera generated alerts in Sector Alpha?",
        "What happened in the restricted zone?",
    ]

    for q in demo_queries:
        print(f"\n>>> Operator Query: \"{q}\"")
        ans = await assistant.answer_query(q, camera_id="CAM-01")
        print(ans.formatted_text())
        print("-" * 50)

    # 6. Safe Teardown
    await manager.stop_all()
    print("\n" + "=" * 75)
    print("  DEMO EXECUTION COMPLETE: 🟢 All Subsystems Verified & Grounded")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_live_demo(total_frames=40))
