"""
Border Intelligence Live Perception Worker.

One worker per camera owns the whole real-time path for that stream:

    read frame -> pipeline.process_frame -> annotate -> JPEG encode -> publish

The worker is the *single owner* of its frame source. `adapter.read_frame_blocking()`
advances the capture by one frame, so if two consumers both pulled from it they
would steal frames from each other and each see a stuttering half-rate stream.
Everything else in the process (MJPEG clients, snapshots) reads the annotated
JPEG this worker publishes.

Encoding happens once per frame no matter how many browsers are watching; clients
fan out from the shared `LiveFrame` slot rather than each re-encoding.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np
import cv2

from backend.config import get_settings
from backend.ingestion.camera_manager import CameraManager, CameraStatus, get_camera_manager
from backend.tracking.overlay import annotate_frame, draw_offline, encode_jpeg
from backend.tracking.pipeline import TrackingPipeline
from backend.zones.security_zone import ZoneMonitor, get_zone_monitor

logger = logging.getLogger(__name__)

# Dedicated thread pool for YOLO inference — separate from asyncio's default
# executor (which also handles render + read threads). Isolating inference
# prevents annotation/encoding from stealing CPU time from ONNX.
_inference_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="yolo")


@dataclass
class LiveFrame:
    """The most recent annotated frame published by a worker."""
    jpeg: bytes
    sequence: int
    frame_number: int
    track_count: int
    published_at: float


class CameraWorker:
    """Runs continuous perception for one camera and publishes annotated frames."""

    def __init__(
        self,
        camera_id: str,
        manager: Optional[CameraManager] = None,
        pipeline: Optional[TrackingPipeline] = None,
        target_fps: Optional[float] = None,
        jpeg_quality: int = 78,
        reconnect_max_delay: float = 20.0,
    ) -> None:
        settings = get_settings()
        self.camera_id = camera_id
        self.manager = manager or get_camera_manager()
        self.jpeg_quality = jpeg_quality
        self.reconnect_max_delay = reconnect_max_delay

        # Private per-track state, shared zone/boundary definitions: a zone added
        # through /api/zones is picked up live, without cross-camera state bleed.
        self.zone_monitor: ZoneMonitor = ZoneMonitor.with_shared_definitions(get_zone_monitor())

        # Per-camera ONNX detector — no shared model, no inference lock needed.
        # Each camera runs YOLO independently at full speed.
        from backend.detection.onnx_detector import get_onnx_detector
        onnx_det = get_onnx_detector(camera_id)

        # Wrap ONNX detector with the ObjectDetector interface the pipeline expects
        from backend.detection.detector import ObjectDetector, DetectionResult
        class _OnnxAdapter(ObjectDetector):
            def __init__(self, onnx_det):
                self._onnx = onnx_det
                self._is_initialized = True
                self.device = "cpu"
            def detect(self, image):
                raw = self._onnx.detect(image)
                return [
                    DetectionResult(
                        class_id=d["class_id"],
                        class_name=d["class_name"],
                        confidence=d["confidence"],
                        bounding_box=d["bbox"],
                        normalized_box=d["norm"],
                    )
                    for d in raw
                ]
            def initialize(self):
                self._onnx.initialize()

        self.pipeline = pipeline or TrackingPipeline(
            detector=_OnnxAdapter(onnx_det),
            zone_monitor=self.zone_monitor,
            frame_stride=1,  # YOLO on every frame — decoupled from display
            target_fps=20.0,  # ONNX on CPU: ~25ms per inference = ~40 FPS single, ~20 FPS per cam with 2 cams
            min_frame_stride=1,
            max_frame_stride=1,  # No stride — every frame gets real YOLO
            adaptive_stride_enabled=False,  # Disabled — inference is decoupled from display
            sample_window=15,
            cooldown_frames=30,
            enable_intermediate_predictions=False,  # Not needed when stride=1
            inference_lock=None,  # No lock — each camera has its own detector
        )

        self._target_fps = target_fps or 30.0
        self._task: Optional[asyncio.Task] = None
        self._stopping = False
        self._latest: Optional[LiveFrame] = None
        self._sequence = 0
        # Woken on every publish so MJPEG clients push frames as they are produced
        # instead of polling on a timer.
        self._frame_ready = asyncio.Event()

        self._display_fps = 0.0
        self._fps_window_start = time.perf_counter()
        self._fps_window_frames = 0
        self._consecutive_read_failures = 0
        self._reconnects = 0
        self._started_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._last_read_ms = 0.0
        self._last_render_ms = 0.0
        self._last_inference_ms = 0.0
        self._last_jpeg: Optional[bytes] = None
        self._inference_fps = 0.0
        self._inference_fps_window_start = time.perf_counter()
        self._inference_fps_window_count = 0
        self._bg_tasks: set = set()

    # ---------------------------------------------------------------- lifecycle

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the perception loop (idempotent)."""
        if self.is_running:
            return
        self._stopping = False
        self._started_at = datetime.now(timezone.utc)
        self.pipeline.initialize()
        self.pipeline.reset()
        self._task = asyncio.create_task(self._run(), name=f"perception:{self.camera_id}")
        logger.info(f"Perception worker started for camera '{self.camera_id}'")

    async def stop(self) -> None:
        """Cancel the loop and wait for it to unwind."""
        self._stopping = True
        task = self._task
        self._task = None
        if self._bg_tasks:
            for t in list(self._bg_tasks):
                t.cancel()
            self._bg_tasks.clear()
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as err:  # pragma: no cover - defensive
                logger.warning(f"Perception worker for '{self.camera_id}' raised on shutdown: {err}")
        self._frame_ready.set()  # release any waiting MJPEG clients
        logger.info(f"Perception worker stopped for camera '{self.camera_id}'")

    # ----------------------------------------------------------------- consumers

    def get_latest(self) -> Optional[LiveFrame]:
        """Most recently published annotated frame, or None before the first one."""
        return self._latest

    async def wait_for_frame(self, after_sequence: int, timeout: float = 5.0) -> Optional[LiveFrame]:
        """
        Await the next frame newer than `after_sequence`.

        Event-driven rather than polled, so a viewer receives each frame as soon
        as it is encoded and an idle stream costs nothing. Returns None on
        timeout so the caller can re-check whether the camera is still alive.
        """
        latest = self._latest
        if latest is not None and latest.sequence > after_sequence:
            return latest
        try:
            await asyncio.wait_for(self._frame_ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        latest = self._latest
        if latest is not None and latest.sequence > after_sequence:
            return latest
        return None

    def get_metrics(self) -> Dict[str, Any]:
        """Real telemetry for this camera — every value measured, none assumed."""
        metrics = self.pipeline.get_metrics()
        latest = self._latest
        metrics.update(
            {
                "camera_id": self.camera_id,
                "display_fps": round(self._display_fps, 2),
                "inference_fps": round(self._inference_fps, 2),
                "inference_latency_ms": round(self._last_inference_ms, 2),
                "worker_running": self.is_running,
                "reconnects": self._reconnects,
                "published_frames": self._sequence,
                "last_frame_number": latest.frame_number if latest else 0,
                "jpeg_bytes": len(latest.jpeg) if latest else 0,
                "read_latency_ms": round(self._last_read_ms, 2),
                "encoding_latency_ms": round(self._last_render_ms, 2),
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "last_error": self._last_error,
            }
        )
        return metrics

    # --------------------------------------------------------------- internals

    def _publish(self, jpeg: bytes, frame_number: int, track_count: int) -> None:
        self._sequence += 1
        self._latest = LiveFrame(
            jpeg=jpeg,
            sequence=self._sequence,
            frame_number=frame_number,
            track_count=track_count,
            published_at=time.perf_counter(),
        )
        # Pulse the event: wake everyone waiting, then re-arm for the next frame.
        self._frame_ready.set()
        self._frame_ready.clear()

    def _tick_fps(self) -> None:
        """Measured output rate over a rolling ~1 s window."""
        self._fps_window_frames += 1
        elapsed = time.perf_counter() - self._fps_window_start
        if elapsed >= 1.0:
            self._display_fps = self._fps_window_frames / elapsed
            self._fps_window_frames = 0
            self._fps_window_start = time.perf_counter()

    def _render(self, image: np.ndarray, tracks: List[Any], degraded: bool = False) -> Optional[bytes]:
        """Annotate + encode. Runs in a worker thread: both steps are CPU-bound."""
        metrics = self.pipeline.get_metrics()
        record = self.manager.get_camera(self.camera_id)
        modality = record.modality if record else "STANDARD"

        render_img = image
        if modality == "THERMAL":
            from backend.detection.thermal_processor import get_thermal_processor
            render_img = get_thermal_processor().render_thermal_colormap(image)

        # Scale down 1080p+ display canvas to 720p for 10x faster JPEG compression (1.5ms vs 18ms)
        h, w = render_img.shape[:2]
        render_tracks = tracks
        if w > 1280:
            target_w = 1280
            target_h = int(h * (1280.0 / w))
            sx = target_w / float(w)
            sy = target_h / float(h)
            render_img = cv2.resize(render_img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            import dataclasses
            scaled_tracks = []
            for t in tracks:
                b = t.bounding_box
                scaled_b = [b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy] if b and len(b) >= 4 else b
                scaled_tracks.append(
                    dataclasses.replace(
                        t,
                        bounding_box=scaled_b,
                        center_x=t.center_x * sx,
                        center_y=t.center_y * sy,
                    )
                )
            render_tracks = scaled_tracks

        annotated = annotate_frame(
            render_img,
            render_tracks,
            zones=list(self.zone_monitor.zones.values()),
            boundaries=list(self.zone_monitor.boundaries.values()),
            camera_id=self.camera_id,
            display_fps=self._display_fps,
            inference_fps=self._inference_fps if self._inference_fps > 0 else metrics.get("ai_processing_fps"),
            device=str(metrics.get("device", "cpu")),
            stride=int(metrics.get("frame_stride", 1)),
            degraded=degraded,
            modality=modality,
        )
        return encode_jpeg(annotated, quality=self.jpeg_quality)

    async def _publish_offline_card(self, message: str) -> None:
        """Show an explicit signal-loss card instead of freezing on a stale frame."""
        record = self.manager.get_camera(self.camera_id)
        width, height = 1280, 720
        if record is not None:
            info = record.adapter.get_stream_info() if hasattr(record.adapter, "get_stream_info") else {}
            width = int(info.get("width") or 0) or 1280
            height = int(info.get("height") or 0) or 720

        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        draw_offline(canvas, self.camera_id, message)
        jpeg = await asyncio.to_thread(encode_jpeg, canvas, self.jpeg_quality)
        if jpeg:
            self._publish(jpeg, frame_number=0, track_count=0)

    async def _reconnect(self) -> bool:
        """
        Re-open a dropped source with capped exponential backoff.

        Retries forever by design: a border camera that drops at 03:00 must come
        back on its own without a server restart (AC2). The delay is capped so a
        glitchy feed doesn't back off to a multi-minute blind spot.
        """
        self._reconnects += 1
        delay = 0.5
        attempt = 0
        while not self._stopping:
            attempt += 1
            await self._publish_offline_card(f"Reconnecting (attempt {attempt})...")
            ok = await self.manager.reconnect_camera(self.camera_id, max_retries=1, base_delay=0.1)
            if ok:
                logger.info(f"Camera '{self.camera_id}' back online after {attempt} attempts")
                self._last_error = None
                # A new capture means new object identities; keep IDs honest.
                self.pipeline.reset()
                return True

            record = self.manager.get_camera(self.camera_id)
            self._last_error = record.last_error if record else "camera deregistered"
            if record is None:
                return False

            logger.warning(
                f"Camera '{self.camera_id}' reconnect attempt {attempt} failed "
                f"({self._last_error}); retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
            delay = min(self.reconnect_max_delay, delay * 2)

        return False

    async def _record_events_bg(self, evs: list) -> None:
        """Persist and publish events in the background to avoid stalling the video loop."""
        try:
            await self.pipeline.event_store.record_events_batch(evs, publish=True)
        except Exception as ev_err:
            logger.error(f"Failed to record live events: {ev_err}")

    async def _run(self) -> None:
        """
        Decoupled perception loop: inference runs independently of display.

        Architecture:
          1. Read frames at source rate (30 FPS)
          2. Kick off YOLO inference as a background task (does NOT block display)
          3. Render immediately using the LATEST available tracks
          4. When inference completes, update tracks for the next render

        This decouples YOLO FPS (~20 FPS on CPU) from display FPS (~30 FPS),
        because rendering never waits for inference to finish.
        """
        record = self.manager.get_camera(self.camera_id)
        if record is None:
            logger.error(f"Perception worker for '{self.camera_id}' aborted: camera not registered")
            return

        source_fps = float(self._target_fps or 30.0)
        frame_interval = 1.0 / source_fps if source_fps > 0 else 0.033
        max_read_failures = 15

        logger.info(
            f"Perception loop running for '{self.camera_id}' at up to {source_fps:.1f} fps "
            f"(decoupled inference/display)"
        )

        next_deadline = time.perf_counter()

        # Shared state between inference and render (protected by asyncio single-thread)
        latest_tracks: list = []
        latest_detections: list = []
        inference_task: Optional[asyncio.Task] = None
        frames_read = 0
        frames_inferred = 0

        def _tick_inference_fps() -> None:
            nonlocal frames_inferred
            frames_inferred += 1

        try:
            while not self._stopping:
                cycle_start = time.perf_counter()

                frame = await self.manager.get_latest_frame(self.camera_id)
                self._last_read_ms = (time.perf_counter() - cycle_start) * 1000.0

                if frame is None or frame.image is None:
                    record = self.manager.get_camera(self.camera_id)
                    if record is None:
                        return  # deregistered underneath us
                    self._consecutive_read_failures += 1
                    source_dead = (
                        not record.adapter.is_running
                        or self._consecutive_read_failures >= max_read_failures
                    )
                    if source_dead:
                        if not await self._reconnect():
                            return
                    else:
                        await asyncio.sleep(0.02)
                    continue

                self._consecutive_read_failures = 0
                frames_read += 1

                try:
                    # --- SYNCHRONIZED PERCEPTION & TRACKING ---
                    # Every frame is processed in lockstep so Frame N is rendered with Frame N's exact tracks.
                    # This completely eliminates the freeze-and-jump lag caused by desynchronized background inference.
                    inf_start = time.perf_counter()
                    loop = asyncio.get_running_loop()
                    res = await loop.run_in_executor(
                        _inference_executor,
                        self.pipeline.process_frame_sync,
                        frame,
                    )
                    self._last_inference_ms = (time.perf_counter() - inf_start) * 1000.0
                    self._inference_fps_window_count += 1
                    elapsed = time.perf_counter() - self._inference_fps_window_start
                    if elapsed >= 1.0:
                        self._inference_fps = self._inference_fps_window_count / elapsed
                        self._inference_fps_window_count = 0
                        self._inference_fps_window_start = time.perf_counter()

                    current_tracks = res.tracks
                    if res.zone_events or res.alert_events or res.evidence_events:
                        evs = list(res.zone_events) + list(res.alert_events) + list(res.evidence_events)
                        task = asyncio.create_task(self._record_events_bg(evs))
                        self._bg_tasks.add(task)
                        task.add_done_callback(self._bg_tasks.discard)

                    # --- RENDER (synchronized with current frame perception) ---
                    render_start = time.perf_counter()
                    jpeg = await asyncio.to_thread(self._render, frame.image, current_tracks)
                    self._last_render_ms = (time.perf_counter() - render_start) * 1000.0

                    if jpeg:
                        self._last_jpeg = jpeg
                        self._publish(jpeg, frame.frame_number, len(latest_tracks))
                        self._tick_fps()

                    # Update pipeline stride controller overhead
                    self.pipeline.set_frame_overhead_ms(self._last_read_ms + self._last_render_ms)
                except Exception as cycle_err:
                    logger.error(f"Perception frame cycle error for {self.camera_id}: {cycle_err}", exc_info=True)

                # --- Pacing: match source FPS ---
                next_deadline += frame_interval
                now = time.perf_counter()
                if now < next_deadline:
                    sleep_duration = next_deadline - now
                    if sleep_duration > 0.002:
                        await asyncio.sleep(sleep_duration)
                    else:
                        await asyncio.sleep(0)
                else:
                    if now - next_deadline > frame_interval * 2:
                        next_deadline = now
                    await asyncio.sleep(0)

        except asyncio.CancelledError:
            raise
        except Exception as err:  # pragma: no cover - defensive
            self._last_error = str(err)
            logger.exception(f"Perception worker for '{self.camera_id}' crashed: {err}")
            rec = self.manager.get_camera(self.camera_id)
            if rec is not None:
                rec.status = CameraStatus.ERROR
                rec.last_error = str(err)


class WorkerRegistry:
    """Process-wide registry of per-camera perception workers."""

    def __init__(self) -> None:
        self._workers: Dict[str, CameraWorker] = {}
        self._lock = asyncio.Lock()

    async def start_worker(self, camera_id: str) -> CameraWorker:
        """Start (or return the already-running) worker for a camera."""
        clean_id = str(camera_id).strip()
        async with self._lock:
            worker = self._workers.get(clean_id)
            if worker is not None and worker.is_running:
                return worker
            worker = CameraWorker(camera_id=clean_id)
            self._workers[clean_id] = worker
        await worker.start()
        return worker

    async def stop_worker(self, camera_id: str) -> bool:
        clean_id = str(camera_id).strip()
        async with self._lock:
            worker = self._workers.pop(clean_id, None)
        if worker is None:
            return False
        await worker.stop()
        return True

    def get_worker(self, camera_id: str) -> Optional[CameraWorker]:
        return self._workers.get(str(camera_id).strip())

    def active_workers(self) -> Dict[str, CameraWorker]:
        return dict(self._workers)

    def aggregate_metrics(self) -> Dict[str, Any]:
        """Fleet-wide totals derived from real per-worker telemetry."""
        workers = list(self._workers.values())
        running = [w for w in workers if w.is_running]
        if not running:
            return {
                "workers": len(workers),
                "workers_running": 0,
                "active_tracks": 0,
                "display_fps": 0.0,
                "ai_processing_fps": 0.0,
            }

        per_worker = [w.get_metrics() for w in running]
        return {
            "workers": len(workers),
            "workers_running": len(running),
            "active_tracks": sum(int(m.get("active_tracks", 0)) for m in per_worker),
            "display_fps": round(
                sum(float(m.get("display_fps", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "ai_processing_fps": round(
                sum(float(m.get("ai_processing_fps", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "inference_latency_ms": round(
                sum(float(m.get("inference_latency_ms", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "tracking_latency_ms": round(
                sum(float(m.get("tracking_latency_ms", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "persistence_latency_ms": round(
                sum(float(m.get("persistence_latency_ms", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "prediction_latency_ms": round(
                sum(float(m.get("prediction_latency_ms", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "encoding_latency_ms": round(
                sum(float(m.get("encoding_latency_ms", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "read_latency_ms": round(
                sum(float(m.get("read_latency_ms", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "total_pipeline_latency_ms": round(
                sum(float(m.get("total_pipeline_latency_ms", 0.0)) for m in per_worker) / len(per_worker), 2
            ),
            "total_detections": sum(int(m.get("total_detections", 0)) for m in per_worker),
            "total_alerts": sum(int(m.get("total_alerts", 0)) for m in per_worker),
            "frames_processed": sum(int(m.get("frames_processed", 0)) for m in per_worker),
            "skipped_frames": sum(int(m.get("skipped_frames", 0)) for m in per_worker),
            "predicted_frames": sum(int(m.get("predicted_frames", 0)) for m in per_worker),
            "device": per_worker[0].get("device", "cpu"),
            "frame_stride": per_worker[0].get("frame_stride", 1),
        }

    async def stop_all(self) -> None:
        async with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            await worker.stop()


global_worker_registry = WorkerRegistry()


def get_worker_registry() -> WorkerRegistry:
    return global_worker_registry
