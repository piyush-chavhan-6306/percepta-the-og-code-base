"""
Border Intelligence Configuration Benchmark Matrix.
Compares different CPU optimization configurations on real VIRAT CCTV footage:
- Resolution: 640 vs 512 vs 480
- Frame Stride: 1 vs 2 vs 3
Measures: Throughput FPS, Mean Frame Latency, Inference Latency, Tracking Latency,
Total Detections, Active Tracks, Security Alerts, and Loitering Alarms.
"""
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time
import cv2

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import init_db
from backend.detection.detector import ObjectDetector
from backend.events.store import get_event_store
from backend.ingestion.adapter import FrameData
from backend.events.schema import SourceType
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity

logging.basicConfig(level=logging.WARNING)


async def benchmark_config(name: str, imgsz: int, stride: int, num_frames: int = 100):
    await init_db()
    store = get_event_store()

    video_path = Path("VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4")
    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened(), "Could not open video"

    detector = ObjectDetector(conf_threshold=0.25, imgsz=imgsz)
    detector.initialize()

    tracker = ByteTrackTracker(track_buffer=30)
    tracker.initialize()

    zone = SecurityZone(
        zone_id="bench_zone",
        name="Sector Alpha",
        polygon=[(500, 350), (1050, 350), (1050, 680), (500, 680)],
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=2.0,
        loitering_debounce_seconds=5.0,
    )
    boundary = VirtualBoundary(
        boundary_id="bench_tripwire",
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
    )
    pipeline.initialize()

    # Warmup
    for _ in range(3):
        ret, w_frame = cap.read()
        if ret:
            detector.detect(w_frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    t_start = time.perf_counter()
    frames_processed = 0
    inference_times = []
    tracking_times = []
    total_frame_times = []

    for i in range(1, num_frames + 1):
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        h, w = frame.shape[:2]
        fd = FrameData(
            camera_id="bench_cam",
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

        frames_processed += 1
        total_frame_times.append((t1 - t0) * 1000.0)
        if res.inference_latency_ms > 0:
            inference_times.append(res.inference_latency_ms)
        if res.tracking_latency_ms > 0:
            tracking_times.append(res.tracking_latency_ms)

    cap.release()
    t_total = time.perf_counter() - t_start

    fps = frames_processed / t_total if t_total > 0 else 0.0
    mean_frame_lat = sum(total_frame_times) / len(total_frame_times) if total_frame_times else 0.0
    mean_inf_lat = sum(inference_times) / len(inference_times) if inference_times else 0.0
    mean_trk_lat = sum(tracking_times) / len(tracking_times) if tracking_times else 0.0
    metrics = pipeline.get_metrics()

    return {
        "name": name,
        "imgsz": imgsz,
        "stride": stride,
        "fps": round(fps, 2),
        "mean_latency_ms": round(mean_frame_lat, 1),
        "inference_ms": round(mean_inf_lat, 1),
        "tracking_ms": round(mean_trk_lat, 1),
        "detections": metrics["total_detections"],
        "alerts": metrics["total_alerts"],
        "active_tracks": metrics["active_tracks"],
    }


async def main():
    configs = [
        ("Baseline (imgsz=640, stride=1)", 640, 1),
        ("Resolution 512 (stride=1)", 512, 1),
        ("Resolution 480 (stride=1)", 480, 1),
        ("Adaptive Stride 2 (imgsz=640)", 640, 2),
        ("Stride 2 + Res 512", 512, 2),
        ("Adaptive Stride 3 (imgsz=640)", 640, 3),
    ]

    print("=" * 95)
    print("RUNNING BORDER INTELLIGENCE BENCHMARK MATRIX (100 FRAMES @ 720p CCTV)")
    print("=" * 95)

    results = []
    for name, imgsz, stride in configs:
        res = await benchmark_config(name, imgsz, stride, num_frames=100)
        results.append(res)
        print(f"-> {name:<32} | {res['fps']:>5.2f} FPS | {res['mean_latency_ms']:>5.1f} ms/frame | Inf: {res['inference_ms']:>4.1f}ms | Dets: {res['detections']:>4} | Tracks: {res['active_tracks']} | Alerts: {res['alerts']}")

    print("\n" + "=" * 95)
    print(f"{'Configuration':<32} | {'FPS':<6} | {'Latency':<9} | {'Inference':<9} | {'Detections':<10} | {'Tracks':<6} | {'Alerts':<6}")
    print("-" * 95)
    for r in results:
        print(f"{r['name']:<32} | {r['fps']:>5.2f}  | {r['mean_latency_ms']:>5.1f} ms | {r['inference_ms']:>5.1f} ms | {r['detections']:>10} | {r['active_tracks']:>6} | {r['alerts']:>6}")
    print("=" * 95)


if __name__ == "__main__":
    asyncio.run(main())
