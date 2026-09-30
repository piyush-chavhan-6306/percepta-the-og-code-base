"""
Phase 1 verification harness: prove real boxes land on real pixels.

Runs a registered VIRAT clip through the real TrackingPipeline, burns the real
tracking geometry in with backend.tracking.overlay, and writes sample JPEGs for
visual inspection. This is a developer tool, not part of the serving path.

    .\\venv\\Scripts\\python scripts\\smoke_overlay.py
"""
import asyncio
from collections import Counter
from pathlib import Path
import sys
import time

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import init_db  # noqa: E402
from backend.ingestion.video_adapter import VideoFileAdapter  # noqa: E402
from backend.tracking.overlay import annotate_frame, encode_jpeg  # noqa: E402
from backend.tracking.pipeline import TrackingPipeline  # noqa: E402
from backend.zones.security_zone import (  # noqa: E402
    SecurityZone,
    VirtualBoundary,
    ZoneMonitor,
    ZoneSeverity,
)

CLIP = "VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4"
FRAMES = 150
SAVE_AT = {50, 100, 149}
OUT_DIR = Path("smoke_out")


async def main() -> int:
    await init_db("sqlite+aiosqlite:///smoke_test.db")
    OUT_DIR.mkdir(exist_ok=True)

    adapter = VideoFileAdapter(camera_id="CAM-SMOKE", video_path=CLIP)
    await adapter.start()
    info = adapter.get_stream_info()
    width, height = info["width"], info["height"]
    print(f"source: {width}x{height} @ {info['native_fps']} fps, {info['total_frames']} frames")

    # Zones sized to this clip's real resolution, not guessed constants.
    zone_monitor = ZoneMonitor()
    zone_monitor.add_zone(
        SecurityZone(
            zone_id="Z-SMOKE",
            name="Restricted Apron",
            polygon=[
                (int(width * 0.08), int(height * 0.45)),
                (int(width * 0.48), int(height * 0.45)),
                (int(width * 0.55), int(height * 0.95)),
                (int(width * 0.04), int(height * 0.95)),
            ],
            severity=ZoneSeverity.RESTRICTED,
        )
    )
    zone_monitor.add_boundary(
        VirtualBoundary(
            boundary_id="B-SMOKE",
            name="Perimeter Tripwire",
            pt1=(int(width * 0.62), int(height * 0.30)),
            pt2=(int(width * 0.62), int(height * 0.92)),
            severity=ZoneSeverity.CRITICAL,
        )
    )

    pipeline = TrackingPipeline(
        zone_monitor=zone_monitor,
        frame_stride=2,
        inference_lock=asyncio.Lock(),
    )
    pipeline.initialize()

    frames_seen = 0
    id_frames = Counter()
    detection_frames = 0
    prediction_frames = 0
    total_alerts = 0
    jpeg_bytes = 0
    started = time.perf_counter()

    for _ in range(FRAMES):
        frame = await asyncio.to_thread(adapter.read_frame_blocking)
        if frame is None:
            break
        frames_seen += 1

        result = await pipeline.process_frame(frame)
        total_alerts += len(result.alert_events)
        for track in result.tracks:
            id_frames[track.track_id] += 1
            if track.provenance == "prediction":
                prediction_frames += 1
            else:
                detection_frames += 1

        metrics = pipeline.get_metrics()
        annotated = annotate_frame(
            frame.image,
            result.tracks,
            zones=list(zone_monitor.zones.values()),
            boundaries=list(zone_monitor.boundaries.values()),
            camera_id="CAM-SMOKE",
            display_fps=frame.fps,
            inference_fps=metrics["ai_processing_fps"],
            device=metrics["device"],
            stride=metrics["frame_stride"],
        )
        encoded = encode_jpeg(annotated)
        jpeg_bytes = len(encoded) if encoded else 0

        if frames_seen - 1 in SAVE_AT:
            out = OUT_DIR / f"frame_{frames_seen - 1:03d}.jpg"
            cv2.imwrite(str(out), annotated)
            print(f"  wrote {out} ({len(result.tracks)} boxes)")

    elapsed = time.perf_counter() - started
    await adapter.stop()

    metrics = pipeline.get_metrics()
    print(f"\nframes={frames_seen} elapsed={elapsed:.2f}s throughput={frames_seen / elapsed:.1f} fps")
    print(f"boxes drawn: {detection_frames} measured + {prediction_frames} predicted")
    print(f"distinct track ids: {len(id_frames)}   alerts: {total_alerts}   jpeg: {jpeg_bytes} bytes")
    print("longest-lived ids:", id_frames.most_common(8))
    print(
        "metrics:",
        {
            k: metrics[k]
            for k in (
                "frames_processed",
                "skipped_frames",
                "predicted_frames",
                "total_detections",
                "active_tracks",
                "inference_latency_ms",
                "total_pipeline_latency_ms",
                "frame_stride",
                "device",
            )
        },
    )
    print("latency buffer len (must stay bounded):", len(pipeline._recent_latencies))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
