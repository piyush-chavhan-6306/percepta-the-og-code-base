"""
Border Intelligence Pipeline Profiler.
Measures latency breakdown across all 12 pipeline stages:
1. Video decoding
2. Frame preprocessing / normalization
3. YOLO inference
4. Post-processing / NMS
5. ByteTrack tracking
6. Movement vector & velocity calculation
7. Security zone containment
8. Virtual boundary & loitering rules
9. Event schema creation
10. SQLite / WAL commit
11. EventBus publishing
12. MJPEG encoding
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import cv2
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import init_db
from backend.detection.detector import ObjectDetector
from backend.events.bus import get_event_bus
from backend.events.schema import AlertEvent, SourceType, TrackingEvent, ZoneEvent
from backend.events.store import get_event_store
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.zones.security_zone import SecurityZone, VirtualBoundary, ZoneMonitor, ZoneSeverity


async def run_profiling(num_frames: int = 100):
    await init_db()
    store = get_event_store()
    bus = get_event_bus()

    video_path = Path("VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4")
    assert video_path.exists(), f"Video missing: {video_path}"

    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened(), "Failed to open video"

    detector = ObjectDetector(conf_threshold=0.25)
    detector.initialize()

    tracker = ByteTrackTracker(track_buffer=30)
    tracker.initialize()

    zone = SecurityZone(
        zone_id="prof_zone",
        name="Profile Zone",
        polygon=[(500, 350), (1050, 350), (1050, 680), (500, 680)],
        severity=ZoneSeverity.RESTRICTED,
        loitering_threshold_seconds=2.0,
        loitering_debounce_seconds=5.0,
    )
    boundary = VirtualBoundary(
        boundary_id="prof_tripwire",
        name="Profile Tripwire",
        pt1=(600, 200),
        pt2=(600, 700),
        severity=ZoneSeverity.CRITICAL,
    )
    zone_monitor = ZoneMonitor(zones=[zone], boundaries=[boundary])

    # Warmup detector on 3 frames
    for _ in range(3):
        ret, w_frame = cap.read()
        if ret:
            detector.detect(w_frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    # Latency accumulators in seconds
    t_decode = 0.0
    t_preproc = 0.0
    t_inference = 0.0
    t_tracking = 0.0
    t_movement = 0.0
    t_zone = 0.0
    t_loitering = 0.0
    t_event_creation = 0.0
    t_db_commit = 0.0
    t_eventbus_pub = 0.0
    t_mjpeg_enc = 0.0
    t_total_pipeline = 0.0

    frames_read = 0
    total_detections = 0
    total_tracks_count = 0
    total_alerts_count = 0

    t_run_start = time.perf_counter()

    for i in range(1, num_frames + 1):
        t_frame_start = time.perf_counter()

        # 1. Video Decoding
        t0 = time.perf_counter()
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        t1 = time.perf_counter()
        t_decode += (t1 - t0)
        frames_read += 1

        h, w = frame.shape[:2]
        fd = FrameData(
            camera_id="prof_cam",
            frame_number=i,
            timestamp=datetime.now(timezone.utc),
            image=frame,
            width=w,
            height=h,
            fps=30.0,
            source=SourceType.VIDEO_FILE,
        )

        # 2 & 3 & 4. YOLO Inference & Detection
        t0 = time.perf_counter()
        dets = detector.detect(frame)
        t1 = time.perf_counter()
        t_inference += (t1 - t0)
        total_detections += len(dets)

        # 5 & 6. ByteTrack Tracking & Movement Vectors
        t0 = time.perf_counter()
        tracks = tracker.update(dets, fd)
        t1 = time.perf_counter()
        t_tracking += (t1 - t0)
        total_tracks_count += len(tracks)

        # 7 & 8. Security Zone & Loitering Rules
        t0 = time.perf_counter()
        zone_events, alert_events = zone_monitor.evaluate_tracks(tracks, camera_id="prof_cam")
        t1 = time.perf_counter()
        t_zone += (t1 - t0)
        total_alerts_count += len(alert_events)

        # 9. Event Schema Creation
        t0 = time.perf_counter()
        tracking_events = []
        for tr in tracks[:5]:  # Limit to 5 for profile consistency
            te = TrackingEvent(
                camera_id="prof_cam",
                track_id=tr.track_id,
                confidence=tr.confidence,
                source=SourceType.VIDEO_FILE,
                timestamp=tr.timestamp,
                lifecycle=tr.lifecycle,
                position=[tr.center_x, tr.center_y],
                velocity=[tr.velocity[0], tr.velocity[1]],
                object_class=tr.object_class,
                bounding_box=tr.bounding_box,
                frame_number=tr.frame_number,
                speed=tr.speed_px_per_frame,
                direction=tr.direction_deg,
            )
            tracking_events.append(te)
        t1 = time.perf_counter()
        t_event_creation += (t1 - t0)

        # 10. SQLite WAL Persistence
        t0 = time.perf_counter()
        for ze in zone_events:
            await store.record_event(ze, publish=False)
        for ae in alert_events:
            await store.record_event(ae, publish=False)
        for te in tracking_events[:2]:  # Persist sample tracks
            await store.record_event(te, publish=False)
        t1 = time.perf_counter()
        t_db_commit += (t1 - t0)

        # 11. EventBus Publishing
        t0 = time.perf_counter()
        for ae in alert_events:
            await bus.publish(ae)
        t1 = time.perf_counter()
        t_eventbus_pub += (t1 - t0)

        # 12. MJPEG JPEG Encoding (optional live stream simulation)
        t0 = time.perf_counter()
        cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        t1 = time.perf_counter()
        t_mjpeg_enc += (t1 - t0)

        t_frame_end = time.perf_counter()
        t_total_pipeline += (t_frame_end - t_frame_start)

    cap.release()
    t_run_total = time.perf_counter() - t_run_start
    overall_fps = frames_read / t_run_total if t_run_total > 0 else 0.0

    print("=" * 80)
    print("PIPELINE PERFORMANCE PROFILING BREAKDOWN (100 FRAMES @ 720p)")
    print("=" * 80)
    print(f"Total Frames Processed:    {frames_read}")
    print(f"Total Elapsed Time:        {t_run_total:.3f} s")
    print(f"Overall Throughput:        {overall_fps:.2f} FPS")
    print(f"Mean Total Frame Latency:  {(t_total_pipeline / frames_read) * 1000.0:.2f} ms/frame")
    print("-" * 80)
    print(f"1. Video Decoding:         {(t_decode / frames_read) * 1000.0:.2f} ms/frame  ({(t_decode / t_total_pipeline) * 100.0:.1f}%)")
    print(f"2. YOLOv8n Inference:      {(t_inference / frames_read) * 1000.0:.2f} ms/frame  ({(t_inference / t_total_pipeline) * 100.0:.1f}%)")
    print(f"3. ByteTrack Tracking:     {(t_tracking / frames_read) * 1000.0:.2f} ms/frame  ({(t_tracking / t_total_pipeline) * 100.0:.1f}%)")
    print(f"4. Zone & Loitering Rules: {(t_zone / frames_read) * 1000.0:.2f} ms/frame  ({(t_zone / t_total_pipeline) * 100.0:.1f}%)")
    print(f"5. Event Schema Creation:  {(t_event_creation / frames_read) * 1000.0:.2f} ms/frame  ({(t_event_creation / t_total_pipeline) * 100.0:.1f}%)")
    print(f"6. SQLite WAL Persistence: {(t_db_commit / frames_read) * 1000.0:.2f} ms/frame  ({(t_db_commit / t_total_pipeline) * 100.0:.1f}%)")
    print(f"7. EventBus Publishing:    {(t_eventbus_pub / frames_read) * 1000.0:.2f} ms/frame  ({(t_eventbus_pub / t_total_pipeline) * 100.0:.1f}%)")
    print(f"8. MJPEG JPEG Encoding:    {(t_mjpeg_enc / frames_read) * 1000.0:.2f} ms/frame  ({(t_mjpeg_enc / t_total_pipeline) * 100.0:.1f}%)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_profiling(100))
