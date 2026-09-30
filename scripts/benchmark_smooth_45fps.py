"""
Smooth 45 FPS Demo Performance Experiment on Real VIRAT CCTV Footage.
Evaluates:
- Capture FPS vs Processing FPS vs Display FPS
- Stride 1 vs Stride 2 vs Stride 3
- Tracker Kalman Intermediate Prediction
- Decoupled Ingestion & MJPEG Streaming
- Accuracy Safety: Persistent Tracks, Detections, ID Continuity, Security Alerts
"""
import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time
import cv2
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import init_db
from backend.detection.detector import ObjectDetector
from backend.events.schema import SourceType
from backend.events.store import get_event_store
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity

logging.basicConfig(level=logging.WARNING)


async def run_experiment(name: str, stride: int, intermediate_pred: bool, adaptive: bool, num_frames: int = 100):
    await init_db()
    store = get_event_store()

    video_path = Path("VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4")
    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened(), f"Cannot open video: {video_path}"

    detector = ObjectDetector(conf_threshold=0.25, imgsz=640)
    detector.initialize()

    tracker = ByteTrackTracker(track_buffer=30)
    tracker.initialize()

    zone = SecurityZone(
        zone_id="smooth_zone",
        name="Perimeter Sector Alpha",
        polygon=[(500, 350), (1050, 350), (1050, 680), (500, 680)],
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=2.0,
        loitering_debounce_seconds=5.0,
    )
    boundary = VirtualBoundary(
        boundary_id="smooth_tripwire",
        name="Fence Line Beta",
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
        target_fps=30.0,
        adaptive_stride_enabled=adaptive,
        sample_window=10,
        cooldown_frames=20,
        enable_intermediate_predictions=intermediate_pred,
    )
    pipeline.initialize()

    # Warmup detector
    for _ in range(3):
        ret, w_frame = cap.read()
        if ret:
            detector.detect(w_frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    # Initial CPU & Memory sample
    process = psutil.Process()
    mem_start_mb = process.memory_info().rss / (1024 * 1024)

    t_start = time.perf_counter()
    inf_latencies = []
    trk_latencies = []
    tot_latencies = []
    capture_latencies = []
    display_enc_latencies = []

    for i in range(1, num_frames + 1):
        t_cap_0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        t_cap_1 = time.perf_counter()
        capture_latencies.append((t_cap_1 - t_cap_0) * 1000.0)

        # Simulate concurrent display JPEG encoding on latest frame
        t_disp_0 = time.perf_counter()
        cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        t_disp_1 = time.perf_counter()
        display_enc_latencies.append((t_disp_1 - t_disp_0) * 1000.0)

        h, w = frame.shape[:2]
        fd = FrameData(
            camera_id="smooth_cam",
            frame_number=i,
            timestamp=datetime.now(timezone.utc),
            image=frame,
            width=w,
            height=h,
            fps=30.0,
            source=SourceType.VIDEO_FILE,
        )

        t0 = time.perf_counter()
        res = await pipeline.process_frame(fd)
        t1 = time.perf_counter()

        tot_latencies.append((t1 - t0) * 1000.0)
        if res.inference_latency_ms > 0:
            inf_latencies.append(res.inference_latency_ms)
        if res.tracking_latency_ms > 0:
            trk_latencies.append(res.tracking_latency_ms)

    cap.release()
    t_elapsed = time.perf_counter() - t_start
    mem_end_mb = process.memory_info().rss / (1024 * 1024)

    metrics = pipeline.get_metrics()
    total_frames = metrics["frames_processed"] + metrics["frames_skipped"]
    fps = total_frames / t_elapsed if t_elapsed > 0 else 0.0

    mean_cap_ms = sum(capture_latencies) / len(capture_latencies) if capture_latencies else 0.0
    mean_disp_ms = sum(display_enc_latencies) / len(display_enc_latencies) if display_enc_latencies else 0.0
    display_fps = 1000.0 / (mean_cap_ms + mean_disp_ms) if (mean_cap_ms + mean_disp_ms) > 0 else 0.0

    return {
        "name": name,
        "processing_fps": round(fps, 2),
        "display_fps": round(display_fps, 1),
        "mean_latency_ms": round(sum(tot_latencies) / len(tot_latencies), 1) if tot_latencies else 0.0,
        "inference_ms": round(sum(inf_latencies) / len(inf_latencies), 1) if inf_latencies else 0.0,
        "tracking_ms": round(sum(trk_latencies) / len(trk_latencies), 1) if trk_latencies else 0.0,
        "frames_processed": metrics["frames_processed"],
        "frames_skipped": metrics["frames_skipped"],
        "detections": metrics["total_detections"],
        "active_tracks": metrics["active_tracks"],
        "alerts": metrics["total_alerts"],
        "final_stride": metrics["frame_stride"],
        "mem_delta_mb": round(mem_end_mb - mem_start_mb, 1),
    }


async def main():
    experiments = [
        ("A. Full-Frame (stride=1, imgsz=640)", 1, False, False),
        ("B. Fixed Stride 2 (without pred)", 2, False, False),
        ("C. Fixed Stride 2 + Kalman Pred", 2, True, False),
        ("D. Fixed Stride 3 + Kalman Pred", 3, True, False),
        ("E. Adaptive Stride + Kalman Pred", 1, True, True),
    ]

    print("=" * 115)
    print("BORDER INTELLIGENCE SMOOTH 45 FPS EXPERIMENT BENCHMARK (100 FRAMES @ 720p CCTV)")
    print("=" * 115)

    results = []
    for name, stride, intermediate_pred, adaptive in experiments:
        res = await run_experiment(name, stride, intermediate_pred, adaptive, num_frames=100)
        results.append(res)
        print(f"-> {name:<35} | CV FPS: {res['processing_fps']:>5.2f} | Disp FPS: {res['display_fps']:>4.1f} | Lat: {res['mean_latency_ms']:>4.1f}ms | Tracks: {res['active_tracks']}/10 | Alerts: {res['alerts']}")

    print("\n" + "=" * 115)
    print(f"{'Configuration':<35} | {'CV FPS':<7} | {'Disp FPS':<8} | {'Latency':<8} | {'Inference':<9} | {'Track Lat':<9} | {'Tracks':<6} | {'Alerts':<6} | {'RAM Δ'}")
    print("-" * 115)
    for r in results:
        print(f"{r['name']:<35} | {r['processing_fps']:>5.2f}  | {r['display_fps']:>5.1f}   | {r['mean_latency_ms']:>5.1f} ms | {r['inference_ms']:>5.1f} ms | {r['tracking_ms']:>5.1f} ms | {r['active_tracks']:>6} | {r['alerts']:>6} | {r['mem_delta_mb']:>4.1f}MB")
    print("=" * 115)


if __name__ == "__main__":
    asyncio.run(main())
