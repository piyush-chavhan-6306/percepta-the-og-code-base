"""
Final Real CCTV E2E Benchmark for Backend Freeze Verification.
Measures performance, latency, accuracy, and track retention on VIRAT CCTV:
A. Full-Frame (imgsz=640, stride=1)
B. Fixed Stride 2 (imgsz=640, stride=2)
C. Adaptive Stride Mode (imgsz=640, target_fps=25.0, adaptive=True)
"""
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import init_db
from backend.detection.detector import ObjectDetector
from backend.events.schema import SourceType
from backend.events.store import get_event_store
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("freeze_bench")


async def run_freeze_benchmark(config_name: str, stride: int, adaptive: bool, num_frames: int = 100):
    await init_db()
    store = get_event_store()

    video_path = Path("VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4")
    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened(), "Failed to open VIRAT video"

    detector = ObjectDetector(conf_threshold=0.25, imgsz=640)
    detector.initialize()

    tracker = ByteTrackTracker(track_buffer=30)
    tracker.initialize()

    zone = SecurityZone(
        zone_id="freeze_zone",
        name="Sector Alpha",
        polygon=[(500, 350), (1050, 350), (1050, 680), (500, 680)],
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=2.0,
        loitering_debounce_seconds=5.0,
    )
    boundary = VirtualBoundary(
        boundary_id="freeze_tripwire",
        name="East Fence",
        pt1=(600, 200),
        pt2=(600, 700),
        severity=ZoneSeverity.CRITICAL,
    )
    zone_monitor = ZoneMonitor(zones=[zone], boundaries=[boundary])

    pipeline = TrackingPipeline(
        detector=detector,
        tracker=tracker,
        zone_monitor=zone_monitor,
        event_store=store,
        emit_tracking_events=True,
        frame_stride=stride,
        target_fps=25.0,
        adaptive_stride_enabled=adaptive,
        sample_window=10,
        cooldown_frames=20,
    )
    pipeline.initialize()

    # Warmup
    for _ in range(3):
        ret, w_frame = cap.read()
        if ret:
            detector.detect(w_frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    t_start = time.perf_counter()
    inf_latencies = []
    trk_latencies = []
    db_latencies = []
    tot_latencies = []

    for i in range(1, num_frames + 1):
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        h, w = frame.shape[:2]
        fd = FrameData(
            camera_id="cam_freeze",
            frame_number=i,
            timestamp=datetime.now(timezone.utc),
            image=frame,
            width=w,
            height=h,
            fps=30.0,
            source=SourceType.VIDEO_FILE,
        )

        res = await pipeline.process_frame(fd)
        t1 = time.perf_counter()

        tot_latencies.append((t1 - t0) * 1000.0)
        if res.inference_latency_ms > 0:
            inf_latencies.append(res.inference_latency_ms)
        if res.tracking_latency_ms > 0:
            trk_latencies.append(res.tracking_latency_ms)
        if res.persistence_latency_ms > 0:
            db_latencies.append(res.persistence_latency_ms)

    cap.release()
    t_elapsed = time.perf_counter() - t_start

    metrics = pipeline.get_metrics()
    total_frames = metrics["frames_processed"] + metrics["frames_skipped"]
    fps = total_frames / t_elapsed if t_elapsed > 0 else 0.0

    return {
        "name": config_name,
        "frames_processed": metrics["frames_processed"],
        "frames_skipped": metrics["frames_skipped"],
        "fps": round(fps, 2),
        "mean_latency_ms": round(sum(tot_latencies) / len(tot_latencies), 1) if tot_latencies else 0.0,
        "inference_ms": round(sum(inf_latencies) / len(inf_latencies), 1) if inf_latencies else 0.0,
        "tracking_ms": round(sum(trk_latencies) / len(trk_latencies), 1) if trk_latencies else 0.0,
        "persistence_ms": round(sum(db_latencies) / len(db_latencies), 1) if db_latencies else 0.0,
        "detections": metrics["total_detections"],
        "active_tracks": metrics["active_tracks"],
        "alerts": metrics["total_alerts"],
        "final_stride": metrics["frame_stride"],
    }


async def main():
    runs = [
        ("A. Full-Frame (stride=1)", 1, False),
        ("B. Fixed Stride 2 (stride=2)", 2, False),
        ("C. Adaptive Stride Mode", 1, True),
    ]

    print("=" * 105)
    print("FINAL BACKEND FREEZE BENCHMARK MATRIX (100 FRAMES @ 720p CCTV)")
    print("=" * 105)

    results = []
    for name, stride, adaptive in runs:
        res = await run_freeze_benchmark(name, stride, adaptive, num_frames=100)
        results.append(res)

    print("\n" + "=" * 105)
    print(f"{'Configuration':<28} | {'FPS':<6} | {'Total Lat':<9} | {'Inference':<9} | {'Track Lat':<9} | {'DB Lat':<7} | {'Processed/Skipped':<17} | {'Tracks':<6} | {'Alerts':<6} | {'Final Stride'}")
    print("-" * 105)
    for r in results:
        proc_skip = f"{r['frames_processed']} / {r['frames_skipped']}"
        print(f"{r['name']:<28} | {r['fps']:>5.2f}  | {r['mean_latency_ms']:>5.1f} ms | {r['inference_ms']:>5.1f} ms | {r['tracking_ms']:>5.1f} ms | {r['persistence_ms']:>4.1f} ms | {proc_skip:<17} | {r['active_tracks']:>6} | {r['alerts']:>6} | {r['final_stride']}")
    print("=" * 105)


if __name__ == "__main__":
    asyncio.run(main())
