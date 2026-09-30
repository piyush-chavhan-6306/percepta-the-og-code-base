"""
Phase 4D E2E Demonstration Script:
Runs real VIRAT CCTV footage through the entire pipeline (YOLOv8n -> ByteTrack -> Security Zones -> SQLite WAL),
and executes operator natural-language queries against the persisted evidence.
"""
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys

# Ensure root directory is in python path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from backend.database import init_db
from backend.detection.detector import ObjectDetector
from backend.events.bus import get_event_bus
from backend.events.store import get_event_store
from backend.ingestion.video_adapter import VideoFileAdapter
from backend.intelligence.assistant import SurveillanceAssistant, get_surveillance_assistant
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    await init_db()
    event_store = get_event_store()
    event_bus = get_event_bus()

    root = Path(__file__).resolve().parent.parent
    video_path = root / "VIRAT" / "CCTV 01" / "VIRAT_S_000205_02_000409_000566.mp4"

    camera_id = f"cctv_live_{int(datetime.now(timezone.utc).timestamp())}"
    logger.info(f"=== Starting Phase 4D CCTV Intelligence Demonstration on {video_path.name} (Camera: {camera_id}) ===")

    # Setup CCTV Ingestion Adapter
    adapter = VideoFileAdapter(
        camera_id=camera_id,
        video_path=str(video_path),
        target_fps=30.0,
        loop=False,
    )
    await adapter.start()
    info = adapter.get_stream_info()
    w, h = info["width"], info["height"]

    # Security Zones
    zone = SecurityZone(
        zone_id="restricted_alpha",
        name="Sector Alpha Restricted Zone",
        polygon=[(0, 0), (w, 0), (w, int(h * 0.7)), (0, int(h * 0.7))],
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=2.0,
        loitering_debounce_seconds=10.0,
    )
    boundary = VirtualBoundary(
        boundary_id="fence_perimeter",
        name="Perimeter Security Fence",
        pt1=(0.0, float(int(h * 0.5))),
        pt2=(float(w), float(int(h * 0.5))),
        severity=ZoneSeverity.CRITICAL,
    )
    zone_monitor = ZoneMonitor(zones=[zone], boundaries=[boundary])

    detector = ObjectDetector(conf_threshold=0.25)
    tracker = ByteTrackTracker(track_buffer=30)
    pipeline = TrackingPipeline(
        detector=detector,
        tracker=tracker,
        zone_monitor=zone_monitor,
        event_store=event_store,
    )
    pipeline.initialize()

    # Process 90 frames of real CCTV footage
    processed = 0
    while processed < 90:
        frame = await adapter.get_next_frame()
        if frame is None:
            break
        await pipeline.process_frame(frame)
        processed += 1

    await adapter.stop()
    logger.info(f"Finished processing {processed} CCTV frames. Testing Natural-Language Intelligence Layer...\n")

    # Initialize Assistant
    assistant = SurveillanceAssistant()

    test_queries = [
        f"What happened on camera {camera_id}?",
        "When did Track 10 enter the restricted zone?",
        "How long did Track 10 remain inside the zone?",
        "When did Track 1 enter the restricted zone?",
        f"Why was the alert generated for camera {camera_id}?",
        "What direction and speed was Track 1 moving?",
        "Show evidence for the highest-risk event",
        "Who is Track 1? What is their name and identity?",  # Refusal test
        "Is Track 1 carrying a weapon or gun?",              # Refusal test
        "Track 1'; SELECT * FROM event_logs; DROP TABLE event_logs; --", # Security test
    ]

    print("=" * 80)
    print("PHASE 4D GROUNDED NATURAL-LANGUAGE INTELLIGENCE QUERY RESULTS")
    print("=" * 80)

    for i, q in enumerate(test_queries, 1):
        print(f"\n[OPERATOR QUERY {i}]: \"{q}\"")
        res = await assistant.answer_query(q, camera_id=camera_id)
        print(f"Status:          {res.status.upper()}")
        print(f"Grounding State: {res.grounding_status.upper()}")
        print("-" * 80)
        print(res.formatted_text())
        print("-" * 80)


if __name__ == "__main__":
    asyncio.run(main())
