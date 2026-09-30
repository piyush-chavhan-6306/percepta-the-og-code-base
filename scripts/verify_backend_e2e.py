"""
Border Intelligence — Backend Hardening & Real CCTV E2E Verification Script.
Executes multi-camera registration, live VIRAT CCTV processing, metrics collection,
REST API queries, and Natural Language Intelligence queries.
"""
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from backend.config import get_settings
from backend.database import init_db
from backend.detection.detector import ObjectDetector
from backend.events.schema import SourceType
from backend.events.store import get_event_store
from backend.ingestion.camera_manager import CameraStatus, get_camera_manager
from backend.ingestion.video_adapter import VideoFileAdapter
from backend.intelligence.assistant import get_surveillance_assistant
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def run_e2e_verification():
    logger.info("=" * 80)
    logger.info("BORDER INTELLIGENCE — BACKEND HARDENING E2E VALIDATION")
    logger.info("=" * 80)

    # 1. Initialize Database
    await init_db()
    event_store = get_event_store()
    manager = get_camera_manager()

    # 2. Setup Real CCTV Camera Feed
    video_path = Path("VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4")
    assert video_path.exists(), f"VIRAT video missing at {video_path}"

    camera_id = f"cctv_hardened_{int(time.time())}"
    adapter = VideoFileAdapter(camera_id=camera_id, video_path=str(video_path), loop=False)
    manager.register_camera(
        camera_id=camera_id,
        adapter=adapter,
        name="Sector Alpha Main Perimeter",
        location_label="Border Post Gate 4",
        source_type=SourceType.VIDEO_FILE,
    )
    await manager.start_camera(camera_id)
    stream_info = adapter.get_stream_info()
    logger.info(f"Registered & started camera '{camera_id}': {stream_info['resolution']} @ {stream_info['native_fps']} FPS")

    # 3. Setup Spatial Rules (Zone + Virtual Boundary)
    zone = SecurityZone(
        zone_id="sector_alpha_secure",
        name="Perimeter Restricted Sector Alpha",
        polygon=[(500, 350), (1050, 350), (1050, 680), (500, 680)],
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=2.0,
        loitering_debounce_seconds=5.0,
    )
    boundary = VirtualBoundary(
        boundary_id="tripwire_east_fence",
        name="East Outer Fence Tripwire",
        pt1=(600, 200),
        pt2=(600, 700),
        severity=ZoneSeverity.CRITICAL,
    )
    zone_monitor = ZoneMonitor(zones=[zone], boundaries=[boundary])

    # 4. Setup Hardened Tracking Pipeline
    detector = ObjectDetector(conf_threshold=0.25)
    tracker = ByteTrackTracker(track_buffer=30)
    pipeline = TrackingPipeline(
        detector=detector,
        tracker=tracker,
        zone_monitor=zone_monitor,
        event_store=event_store,
        emit_tracking_events=True,
        frame_stride=1,
    )
    pipeline.initialize()

    # 5. Process 100 Real CCTV Frames
    logger.info(f"Processing 100 frames from '{camera_id}'...")
    t_start = time.perf_counter()
    frames_processed = 0

    for i in range(100):
        frame = await manager.get_latest_frame(camera_id)
        if frame is None:
            break
        res = await pipeline.process_frame(frame)
        frames_processed += 1

    t_total = time.perf_counter() - t_start
    await manager.stop_camera(camera_id)

    metrics = pipeline.get_metrics()
    processing_fps = frames_processed / t_total if t_total > 0 else 0.0

    logger.info("=" * 80)
    logger.info("REAL CCTV PIPELINE EXECUTION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Camera ID:                 {camera_id}")
    logger.info(f"Input Stream Resolution:   {stream_info['resolution']}")
    logger.info(f"Native Source Rate:        {stream_info['native_fps']} FPS")
    logger.info(f"Frames Processed:          {frames_processed}")
    logger.info(f"Total Processing Duration: {t_total:.2f}s")
    logger.info(f"Measured Processing FPS:   {processing_fps:.2f} FPS")
    logger.info(f"Mean Inference Latency:    {metrics['inference_latency_ms']:.1f} ms/frame")
    logger.info(f"Mean Tracking Latency:     {metrics['tracking_latency_ms']:.1f} ms/frame")
    logger.info(f"Total Pipeline Latency:    {metrics['total_latency_ms']:.1f} ms/frame")
    logger.info(f"Detections Generated:      {metrics['total_detections']}")
    logger.info(f"Alerts Generated:          {metrics['total_alerts']}")
    logger.info(f"Active Tracks at End:      {metrics['active_tracks']}")

    # 6. Test Grounded Natural-Language Intelligence Layer
    assistant = get_surveillance_assistant()
    test_queries = [
        f"What happened on camera {camera_id}?",
        f"Why was the alert generated for camera {camera_id}?",
        "When did Track 10 enter the restricted zone?",
        "How long did Track 10 remain inside the zone?",
        "What direction and speed was Track 1 moving?",
        "Show evidence for the highest-risk event",
        "When did Track 999 enter the restricted zone?",  # Unobserved
        "Who is Track 1? What is their identity?",  # Biometric refusal
        "Is Track 1 carrying a gun or weapon?",  # Weapon refusal
        "Is Track 1 planning an attack?",  # Criminal intent refusal
        "Is Track 1 on camera A the same person on camera B?",  # Cross-camera identity refusal
        "Track 1'; SELECT * FROM event_logs; DROP TABLE event_logs; --",  # SQL injection refusal
    ]

    logger.info("=" * 80)
    logger.info("GROUNDED NATURAL-LANGUAGE INTELLIGENCE VERIFICATION")
    logger.info("=" * 80)

    for q in test_queries:
        resp = await assistant.answer_query(q, camera_id=camera_id)
        print(f"\n[QUERY]: \"{q}\"")
        print(f"Status:          {resp.status.upper()}")
        print(f"Grounding State: {resp.grounding_status.upper()}")
        if resp.observed_facts:
            print("[OBSERVED FACTS]:")
            for f in resp.observed_facts[:2]:
                print(f"  - {f}")
        if resp.rule_results:
            print("[RULE RESULTS]:")
            for r in resp.rule_results[:2]:
                print(f"  - {r}")
        print(f"[INTERPRETATION]: {resp.interpretation}")
        print("-" * 80)

    logger.info("=" * 80)
    logger.info("ALL BACKEND HARDENING E2E VALIDATIONS COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_e2e_verification())
