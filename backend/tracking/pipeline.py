"""
Border Intelligence Tracking & Intelligence Pipeline Module.
Coordinates the end-to-end flow:
FrameData -> ObjectDetector -> ByteTrackTracker -> ZoneMonitor -> EventStore -> EventBus.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

# Dedicated background thread pool for disk I/O and SHA-256 calculation
# Prevents disk writes from blocking real-time perception loop
# Set to 4 workers to allow faster concurrent snapshot saving (CPU intensive tasks bypassed)
_evidence_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="evidence")

from backend.detection.detector import DetectionResult, ObjectDetector, get_detector
from backend.events.schema import (
    ANPREvent,
    AlertEvent,
    DetectionEvent,
    EvidenceEvent,
    EvidenceType,
    FaceAnalyticsEvent,
    IncidentEvent,
    TrackingEvent,
    ZoneEvent,
)
from backend.events.store import EventStore, get_event_store
from backend.ingestion.adapter import FrameData
from backend.tracking.bytetrack_wrapper import ByteTrackTracker
from backend.tracking.tracker import BaseTracker, TrackedObject
from backend.zones.security_zone import ZoneMonitor

logger = logging.getLogger(__name__)


@dataclass
class FrameProcessingResult:
    """Consolidated results of running one frame through the intelligence pipeline."""
    frame_number: int
    detections: List[DetectionResult]
    tracks: List[TrackedObject]
    zone_events: List[ZoneEvent]
    alert_events: List[AlertEvent]
    tracking_events: List[TrackingEvent]
    evidence_events: List[EvidenceEvent] = field(default_factory=list)
    inference_latency_ms: float = 0.0
    tracking_latency_ms: float = 0.0
    persistence_latency_ms: float = 0.0
    total_latency_ms: float = 0.0


class TrackingPipeline:
    """
    Unified multi-object tracking and movement intelligence pipeline.
    Enforces Persist-Before-Publish at every stage with comprehensive telemetry.
    """

    def __init__(
        self,
        detector: Optional[ObjectDetector] = None,
        tracker: Optional[BaseTracker] = None,
        zone_monitor: Optional[ZoneMonitor] = None,
        event_store: Optional[EventStore] = None,
        emit_detection_events: bool = False,
        emit_tracking_events: bool = True,
        frame_stride: int = 1,
        target_fps: float = 25.0,
        min_frame_stride: int = 1,
        max_frame_stride: int = 3,
        adaptive_stride_enabled: bool = False,
        sample_window: int = 15,
        cooldown_frames: int = 30,
        enable_intermediate_predictions: bool = True,
        inference_lock: Optional["asyncio.Lock"] = None,
        tracking_event_interval_frames: int = 10,
        async_detection: bool = False,
    ) -> None:
        self.detector = detector or get_detector()
        self.tracker = tracker or ByteTrackTracker()
        self.zone_monitor = zone_monitor or ZoneMonitor()
        self.event_store = event_store or get_event_store()
        self.emit_detection_events = emit_detection_events
        self.emit_tracking_events = emit_tracking_events
        self.frame_stride = max(1, frame_stride)
        self.target_fps = target_fps
        self.min_frame_stride = min_frame_stride
        self.max_frame_stride = max_frame_stride
        self.adaptive_stride_enabled = adaptive_stride_enabled
        self.sample_window = sample_window
        self.cooldown_frames = cooldown_frames
        self.enable_intermediate_predictions = enable_intermediate_predictions
        self.inference_lock = inference_lock
        self.async_detection = async_detection
        self._async_detection_task: Optional[asyncio.Task] = None
        # Tracking events are pure telemetry (heatmaps, incident dossiers, replay)
        # and every visible object emits one per detection frame. At ~10 tracks
        # and 12 detection fps that is ~10M rows/day -- the DB grew 154 MB in an
        # hour of demo footage. Sampling every Nth frame *per track* keeps the
        # trajectory shape (and the heatmap) while bounding growth ~10x. Alerts
        # and zone events are never sampled: those must be exact.
        self.tracking_event_interval_frames = max(1, tracking_event_interval_frames)
        self._last_track_event_frame: Dict[int, int] = {}
        self._is_initialized = False

        # Telemetry & Metrics
        self._frames_processed = 0
        self._frames_skipped = 0
        self._frames_predicted = 0
        self._total_detections = 0
        self._total_alerts = 0
        self._last_inference_ms = 0.0
        self._last_tracking_ms = 0.0
        self._last_prediction_ms = 0.0
        self._last_persistence_ms = 0.0
        self._last_total_ms = 0.0
        self._start_time = time.perf_counter()
        self._last_tracks: List[TrackedObject] = []
        self._cooldown_counter = 0
        self._recent_latencies: list[float] = []
        # Per-frame cost the pipeline itself cannot see (frame read, annotate,
        # JPEG encode). The stride controller must include it or it optimizes a
        # metric that excludes ~17 ms of every frame and settles one stride too
        # low. Callers that only run the pipeline leave this at 0.
        self._frame_overhead_ms = 0.0

    def set_frame_overhead_ms(self, overhead_ms: float) -> None:
        """
        Report the out-of-pipeline cost of delivering one frame.

        The live worker calls this each cycle with its measured read + annotate +
        encode time so adaptive stride decisions are made against the rate the
        operator actually sees rather than inference latency alone.
        """
        self._frame_overhead_ms = max(0.0, float(overhead_ms))

    def initialize(self) -> None:
        """Initialize detector and tracker."""
        if not self._is_initialized:
            self.detector.initialize()
            self.tracker.initialize()
            self._is_initialized = True
            logger.info("TrackingPipeline initialized successfully.")

    def reset(self) -> None:
        """Reset internal pipeline states."""
        self.tracker.reset()
        self.zone_monitor.reset()
        self._last_tracks = []
        self._frames_processed = 0
        self._frames_skipped = 0
        self._frames_predicted = 0
        self._cooldown_counter = 0
        self._recent_latencies.clear()
        self._last_track_event_frame.clear()
        self._start_time = time.perf_counter()

    def get_metrics(self) -> Dict[str, Any]:
        """Return comprehensive operational pipeline telemetry."""
        elapsed = time.perf_counter() - self._start_time
        total_frames = self._frames_processed + self._frames_skipped
        fps = (total_frames / elapsed) if elapsed > 0 else 0.0
        return {
            "processed_frames": self._frames_processed,
            "frames_processed": self._frames_processed,
            "skipped_frames": self._frames_skipped,
            "frames_skipped": self._frames_skipped,
            "predicted_frames": self._frames_predicted,
            "ai_processing_fps": round(fps, 2),
            "processing_fps": round(fps, 2),
            "inference_latency_ms": round(self._last_inference_ms, 2),
            "tracking_latency_ms": round(self._last_tracking_ms, 2),
            "prediction_latency_ms": round(self._last_prediction_ms, 2),
            "persistence_latency_ms": round(self._last_persistence_ms, 2),
            "total_pipeline_latency_ms": round(self._last_total_ms, 2),
            "total_latency_ms": round(self._last_total_ms, 2),
            "total_detections": self._total_detections,
            "alerts": self._total_alerts,
            "total_alerts": self._total_alerts,
            "active_tracks": len(self._last_tracks),
            "frame_stride": self.frame_stride,
            "adaptive_stride_enabled": self.adaptive_stride_enabled,
            "device": getattr(self.detector, "device", "cpu"),
        }

    def _record_latency(self, latency_ms: float) -> None:
        """
        Append a latency sample, keeping the buffer bounded.

        This list is appended to on every single frame, so an unbounded list leaks
        steadily during 24/7 operation (~25 fps == ~2M floats/day). Only the most
        recent `sample_window` samples are ever read by the adaptive-stride logic.
        """
        self._recent_latencies.append(latency_ms)
        cap = max(self.sample_window * 4, 64)
        if len(self._recent_latencies) > cap:
            del self._recent_latencies[:-cap]

    def _should_emit_track_event(self, track: TrackedObject, frame_number: int) -> bool:
        """
        Decide whether this track's telemetry is due to be persisted.

        Always emits the first sighting and any lifecycle transition, so a track
        appearing, being lost, or being re-acquired is never missed. Between those
        it samples every `tracking_event_interval_frames`.
        """
        last = self._last_track_event_frame.get(track.track_id)
        if last is None:
            return True
        # "updated" is the steady state; created/recovered/lost/terminated are all
        # transitions worth recording exactly.
        if getattr(track, "lifecycle", "updated") != "updated":
            return True
        return (frame_number - last) >= self.tracking_event_interval_frames

    def _evaluate_adaptive_stride(self) -> None:
        """
        Evaluate processing speed and adaptively adjust frame stride with hysteresis and cooldown.
        Avoids rapid oscillation.
        """
        if not self.adaptive_stride_enabled:
            return

        if self._cooldown_counter > 0:
            self._cooldown_counter -= 1
            return

        if len(self._recent_latencies) < self.sample_window:
            return

        mean_lat_ms = sum(self._recent_latencies[-self.sample_window:]) / self.sample_window

        # `_recent_latencies` holds one sample per *displayed* frame, so it already
        # averages cheap prediction frames in with expensive detection frames.
        # Multiplying by frame_stride here would count the stride saving twice and
        # report a wildly optimistic rate: at stride 2 with 67 ms detections and
        # 0.2 ms predictions the mean is 33.6 ms, which is a true 29.8 fps, but
        # scaling by the stride claimed 59.5 fps. That over-report tripped the
        # "performance recovered" branch, dropped the stride back to 1, measured
        # 14.9 fps, raised it again, and oscillated forever -- pinning real output
        # at roughly half the achievable frame rate.
        #
        # `_frame_overhead_ms` charges each delivered frame its read + annotate +
        # encode cost as well, so the controller targets the rate the operator
        # actually sees rather than inference latency in isolation.
        cycle_ms = mean_lat_ms + self._frame_overhead_ms
        effective_fps = (1000.0 / cycle_ms) if cycle_ms > 0 else 0.0

        if effective_fps < self.target_fps * 0.85 and self.frame_stride < self.max_frame_stride:
            old_stride = self.frame_stride
            self.frame_stride += 1
            self._cooldown_counter = self.cooldown_frames
            logger.info(
                f"Adaptive frame stride increased {old_stride} -> {self.frame_stride}: "
                f"measured effective FPS ({effective_fps:.1f}) is below target ({self.target_fps:.1f})"
            )
        elif effective_fps > self.target_fps * 1.40 and self.frame_stride > self.min_frame_stride:
            old_stride = self.frame_stride
            self.frame_stride -= 1
            self._cooldown_counter = self.cooldown_frames
            logger.info(
                f"Adaptive frame stride decreased {old_stride} -> {self.frame_stride}: "
                f"measured effective FPS ({effective_fps:.1f}) recovered above target ({self.target_fps:.1f})"
            )

    async def _detect_async(self, image) -> List[DetectionResult]:
        """
        Run YOLO inference without stalling the asyncio event loop.

        Inference is compute-bound and costs tens of milliseconds, so it runs in a
        worker thread; blocking the loop here would freeze every MJPEG client and
        WebSocket broadcast for the duration. When multiple cameras share a single
        detector instance, an optional lock serializes access because the
        underlying model is not re-entrant.
        """
        if self.inference_lock is not None:
            async with self.inference_lock:
                return await asyncio.to_thread(self.detector.detect, image)
        return await asyncio.to_thread(self.detector.detect, image)

    def _evaluate_evidence_and_analytics(
        self,
        frame: FrameData,
        tracks: List[TrackedObject],
        alert_events: List[AlertEvent],
    ) -> List[EvidenceEvent]:
        """
        Evaluate and capture real forensic evidence across all required tiers:
        1. RULE VIOLATIONS (Zone, Tripwire, Threat):
           Dedicated full-frame forensic image with RED box ONLY on violating target.
        2. PERSON / FACE:
           Real optical face detection, deduplicated with cooldown.
        3. VEHICLE / ANPR:
           Real plate localization & OCR candidate evaluation, deduplicated with cooldown.
        Computes real cryptographic SHA-256 for all generated evidence files.
        """
        if frame is None or frame.image is None or frame.image.size == 0:
            return []

        from backend.events.snapshots import get_snapshot_manager
        from backend.detection.face_analytics import get_face_analytics_pipeline
        from backend.detection.anpr import get_anpr_processor

        snap_mgr = get_snapshot_manager()
        cooldown_mgr = snap_mgr.cooldown_mgr
        face_pipeline = get_face_analytics_pipeline()
        anpr_processor = get_anpr_processor()

        evidence_events: List[EvidenceEvent] = []
        tracks_by_id = {t.track_id: t for t in tracks}
        tracks_by_id.update({str(t.track_id): t for t in tracks})

        # --- 1. RULE VIOLATION EVIDENCE (CRITICAL) ---
        for alert in alert_events:
            try:
                v_track = tracks_by_id.get(alert.track_id) or tracks_by_id.get(str(alert.track_id))
                v_rule = str(getattr(alert, "rule_id", "") or alert.message or "SECURITY_RULE")
                from backend.zones.security_zone import normalize_severity
                v_sev = normalize_severity(getattr(alert, "severity", "NORMAL"))

                rule_upper = v_rule.upper() + " " + str(alert.message or "").upper()
                if "TRIPWIRE" in rule_upper or "BOUNDARY" in rule_upper or "CROSSED" in rule_upper:
                    ev_type = EvidenceType.TRIPWIRE_VIOLATION
                elif "LOITER" in rule_upper or "DWELL" in rule_upper:
                    ev_type = EvidenceType.LOITERING
                elif "ZONE" in rule_upper or "RESTRICTED" in rule_upper or "PERIMETER" in rule_upper:
                    ev_type = EvidenceType.ZONE_VIOLATION
                else:
                    ev_type = EvidenceType.THREAT

                # Precompute face/plate sub-crops for violating track
                face_b = None
                plate_b = None
                if v_track and v_track.bounding_box and len(v_track.bounding_box) >= 4:
                    bx1, by1, bx2, by2 = v_track.bounding_box[:4]
                    bw, bh = bx2 - bx1, by2 - by1
                    if v_track.object_class == "person":
                        face_b = [bx1, by1, bx2, by1 + bh * 0.35]
                    elif anpr_processor.is_vehicle(v_track.object_class):
                        plate_b = [bx1 + bw * 0.15, by1 + bh * 0.65, bx2 - bw * 0.15, by2]

                if cooldown_mgr.can_capture(frame.camera_id, alert.track_id, ev_type):
                    actual_inc_id = getattr(alert, "incident_id", None) or str(alert.event_id)
                    snap_id = f"VIOLATION_{actual_inc_id}_{frame.frame_number}_{int(datetime.now().timestamp())}"
                    filename = f"{snap_id}.jpg"
                    file_path = str(snap_mgr.snapshot_dir / filename)
                    file_uri = f"/api/evidence/snapshots/file/{filename}"
                    target_fname = f"TARGET_{snap_id}.jpg"
                    target_uri = f"/api/evidence/snapshots/file/{target_fname}"

                    # Offload image rendering, JPEG encoding, and SHA-256 calculation to background thread pool
                    _evidence_pool.submit(
                        snap_mgr.save_violation_evidence_package,
                        incident_id=actual_inc_id,
                        image=frame.image.copy(),
                        all_tracks=list(tracks),
                        violating_track_id=alert.track_id,
                        camera_id=str(frame.camera_id),
                        frame_number=int(frame.frame_number),
                        trigger_reason=str(alert.message or "SECURITY_BREACH"),
                        rule_name=v_rule,
                        severity=v_sev,
                        evidence_type=ev_type,
                        face_bbox=face_b,
                        plate_bbox=plate_b,
                        confidence=float(alert.confidence or 0.9),
                    )
                    cooldown_mgr.record_capture(frame.camera_id, alert.track_id, ev_type)

                    # Update incident evidence stats
                    from backend.incidents.engine import get_incident_engine
                    get_incident_engine().record_evidence_captured(actual_inc_id)

                    # Link metadata directly to AlertEvent
                    alert.evidence_snapshot_uri = file_uri
                    alert.target_crop_uri = target_uri
                    alert.evidence_id = snap_id
                    alert.best_frame_number = int(frame.frame_number)
                    alert.timeline_offset_sec = round(float(frame.frame_number) / float(frame.fps or 30.0), 2)

                    # Dedicated EvidenceEvent for database indexing & audit
                    ev_event = EvidenceEvent(
                        camera_id=str(frame.camera_id),
                        evidence_id=snap_id,
                        evidence_type=ev_type,
                        file_path=file_path,
                        file_uri=file_uri,
                        target_crop_uri=target_uri,
                        bounding_box=v_track.bounding_box if v_track else None,
                        object_class=v_track.object_class if v_track else "target",
                        confidence=float(alert.confidence or 0.9),
                        track_id=str(alert.track_id) if alert.track_id is not None else None,
                        alert_id=str(alert.event_id),
                        incident_id=actual_inc_id,
                        severity=v_sev,
                        zone_id=getattr(alert, "zone_id", None),
                        zone_name=getattr(alert, "zone_name", None),
                        timestamp=frame.timestamp,
                    )
                    evidence_events.append(ev_event)
            except Exception as v_err:
                logger.warning(f"Failed to generate violation evidence package: {v_err}")

        # --- 2. PERSON / FACE EVIDENCE (Cooldown gated, async disk write) ---
        for trk in tracks:
            try:
                if trk.object_class == "person":
                    if cooldown_mgr.can_capture(frame.camera_id, trk.track_id, EvidenceType.PERSON):
                        cooldown_mgr.record_capture(frame.camera_id, trk.track_id, EvidenceType.PERSON)
                        _evidence_pool.submit(
                            snap_mgr.save_crop_evidence,
                            image=frame.image.copy(),
                            bbox=trk.bounding_box,
                            evidence_type=EvidenceType.PERSON,
                            camera_id=str(frame.camera_id),
                            track_id=trk.track_id,
                            frame_number=frame.frame_number,
                            trigger_reason="PERSON_DETECTED",
                        )

                    # Optical face detection — evaluated ONLY when cooldown window permits
                    if cooldown_mgr.can_capture(frame.camera_id, trk.track_id, EvidenceType.FACE):
                        cooldown_mgr.record_capture(frame.camera_id, trk.track_id, EvidenceType.FACE)
                        def _bg_face(f_img, f_bbox, c_id, t_id, f_num):
                            try:
                                face_res = face_pipeline.analyze_face(
                                    image=f_img, person_bbox=f_bbox, camera_id=c_id, track_id=t_id
                                )
                                if face_res is not None and face_res.face_detected and face_res.face_bbox:
                                    snap_mgr.save_crop_evidence(
                                        image=f_img,
                                        bbox=face_res.face_bbox,
                                        evidence_type=EvidenceType.FACE,
                                        camera_id=c_id,
                                        track_id=t_id,
                                        frame_number=f_num,
                                        trigger_reason="FACE_DETECTED",
                                    )
                            except Exception as e:
                                logger.warning(f"Face bg err: {e}")

                        _evidence_pool.submit(
                            _bg_face, frame.image.copy(), trk.bounding_box, str(frame.camera_id), trk.track_id, frame.frame_number
                        )

                # --- 3. VEHICLE / ANPR EVIDENCE (Cooldown gated, async disk write) ---
                elif anpr_processor.is_vehicle(trk.object_class):
                    if cooldown_mgr.can_capture(frame.camera_id, trk.track_id, EvidenceType.VEHICLE):
                        cooldown_mgr.record_capture(frame.camera_id, trk.track_id, EvidenceType.VEHICLE)
                        _evidence_pool.submit(
                            snap_mgr.save_crop_evidence,
                            image=frame.image.copy(),
                            bbox=trk.bounding_box,
                            evidence_type=EvidenceType.VEHICLE,
                            camera_id=str(frame.camera_id),
                            track_id=trk.track_id,
                            frame_number=frame.frame_number,
                            trigger_reason="VEHICLE_DETECTED",
                        )

                    # License plate localization & OCR — evaluated ONLY when cooldown window permits
                    if cooldown_mgr.can_capture(frame.camera_id, trk.track_id, EvidenceType.ANPR):
                        cooldown_mgr.record_capture(frame.camera_id, trk.track_id, EvidenceType.ANPR)
                        def _bg_anpr(f_img, t_bbox, t_cls, c_id, t_id, f_num):
                            try:
                                anpr_res = anpr_processor.process_vehicle(
                                    frame=f_img, bounding_box=t_bbox, object_class=t_cls, camera_id=c_id, vehicle_id=str(t_id)
                                )
                                if anpr_res is not None and anpr_res.plate_bounding_box:
                                    snap_mgr.save_crop_evidence(
                                        image=f_img,
                                        bbox=anpr_res.plate_bounding_box,
                                        evidence_type=EvidenceType.ANPR,
                                        camera_id=c_id,
                                        track_id=t_id,
                                        frame_number=f_num,
                                        trigger_reason="ANPR_PLATE_LOCALIZED",
                                    )
                            except Exception as e:
                                logger.warning(f"ANPR bg err: {e}")

                        _evidence_pool.submit(
                            _bg_anpr, frame.image.copy(), trk.bounding_box, trk.object_class, str(frame.camera_id), trk.track_id, frame.frame_number
                        )
            except Exception as trk_err:
                logger.warning(f"Error evaluating track evidence for track {trk.track_id}: {trk_err}")

        return evidence_events

    async def process_frame(
        self,
        frame: FrameData,
    ) -> FrameProcessingResult:
        """
        Process a single FrameData package through detection, tracking, zone analysis, and persistence.
        """
        if not self._is_initialized:
            self.initialize()

        if frame is None or frame.image is None:
            return FrameProcessingResult(
                frame_number=0 if frame is None else frame.frame_number,
                detections=[],
                tracks=[],
                zone_events=[],
                alert_events=[],
                tracking_events=[],
            )

        # Intermediate frame processing (advance tracker state via Kalman velocity prediction without YOLO)
        if self.frame_stride > 1 and ((frame.frame_number - 1) % self.frame_stride != 0):
            self._frames_skipped += 1
            t0 = time.perf_counter()

            if self.enable_intermediate_predictions and self._last_tracks:
                t_track_start = time.perf_counter()
                predicted_tracks = self.tracker.predict_step(frame)
                t_track_end = time.perf_counter()
                self._last_tracking_ms = (t_track_end - t_track_start) * 1000.0
                self._last_prediction_ms = self._last_tracking_ms
                self._frames_predicted += 1
                if predicted_tracks:
                    self._last_tracks = predicted_tracks

                # Evaluate security zones on predicted positions
                zone_events, alert_events = self.zone_monitor.evaluate_tracks(
                    tracks=self._last_tracks,
                    camera_id=frame.camera_id,
                    source=frame.source,
                )

                if zone_events or alert_events:
                    events_to_persist = list(zone_events) + list(alert_events)
                    asyncio.create_task(self.event_store.record_events_batch(events_to_persist, publish=True))
                    self._total_alerts += len(alert_events)

                t_end = time.perf_counter()
                self._last_total_ms = (t_end - t0) * 1000.0
                self._last_inference_ms = 0.0
                self._last_persistence_ms = 0.0
                self._record_latency(self._last_total_ms)
                self._evaluate_adaptive_stride()

                return FrameProcessingResult(
                    frame_number=frame.frame_number,
                    detections=[],
                    tracks=self._last_tracks,
                    zone_events=zone_events,
                    alert_events=alert_events,
                    tracking_events=[],
                    inference_latency_ms=0.0,
                    tracking_latency_ms=self._last_tracking_ms,
                    persistence_latency_ms=0.0,
                    total_latency_ms=self._last_total_ms,
                )
            else:
                return FrameProcessingResult(
                    frame_number=frame.frame_number,
                    detections=[],
                    tracks=self._last_tracks,
                    zone_events=[],
                    alert_events=[],
                    tracking_events=[],
                )

        t0 = time.perf_counter()

        # 1. Detect objects in frame (offloaded to a thread so the event loop stays responsive)
        t_det_start = time.perf_counter()
        from backend.ingestion.sensor_adapter import SensorFrameAdapter
        norm_image = SensorFrameAdapter.normalize_frame(frame.image, modality=getattr(frame, "modality", "STANDARD"))
        detections = await self._detect_async(norm_image)
        t_det_end = time.perf_counter()
        self._last_inference_ms = (t_det_end - t_det_start) * 1000.0
        self._total_detections += len(detections)

        # Optional: emit detection events
        detection_events: List[DetectionEvent] = []
        if self.emit_detection_events and detections:
            for det in detections:
                det_event = DetectionEvent(
                    camera_id=frame.camera_id,
                    object_class=det.class_name,
                    bounding_box=det.bounding_box,
                    frame_number=frame.frame_number,
                    confidence=det.confidence,
                    source=frame.source,
                    timestamp=frame.timestamp,
                )
                detection_events.append(det_event)

        # 2. Update multi-object tracker
        t_track_start = time.perf_counter()
        tracks = self.tracker.update(detections, frame)
        t_track_end = time.perf_counter()
        self._last_tracking_ms = (t_track_end - t_track_start) * 1000.0
        self._last_tracks = tracks

        # 3. Create tracking events
        tracking_events: List[TrackingEvent] = []
        if self.emit_tracking_events and tracks:
            live_ids = set()
            for track in tracks:
                live_ids.add(track.track_id)
                if not self._should_emit_track_event(track, frame.frame_number):
                    continue
                self._last_track_event_frame[track.track_id] = frame.frame_number
                track_event = TrackingEvent(
                    camera_id=frame.camera_id,
                    track_id=track.track_id,
                    confidence=track.confidence,
                    source=frame.source,
                    timestamp=track.timestamp,
                    lifecycle=track.lifecycle,
                    position=[track.center_x, track.center_y],
                    velocity=[track.velocity[0], track.velocity[1]],
                    object_class=track.object_class,
                    bounding_box=track.bounding_box,
                    frame_number=track.frame_number,
                    speed=track.speed_px_per_frame,
                    direction=track.direction_deg,
                )
                tracking_events.append(track_event)

            # Drop bookkeeping for tracks that no longer exist, so this dict
            # cannot grow without bound across a 24/7 run.
            if len(self._last_track_event_frame) > len(live_ids):
                for stale in [tid for tid in self._last_track_event_frame if tid not in live_ids]:
                    del self._last_track_event_frame[stale]

        # 4. Evaluate security zones and virtual boundaries
        zone_events, alert_events = self.zone_monitor.evaluate_tracks(
            tracks=tracks,
            camera_id=frame.camera_id,
            source=frame.source,
        )

        # 5. Capture forensic evidence and analytics across all tiers
        evidence_events: List[EvidenceEvent] = []
        if frame.image is not None and frame.image.size > 0:
            evidence_events = await asyncio.to_thread(
                self._evaluate_evidence_and_analytics,
                frame,
                tracks,
                alert_events,
            )

        # 6. Persist frame events asynchronously in background task (Non-blocking high-FPS streaming)
        events_to_persist = []
        if detection_events:
            events_to_persist.extend(detection_events)
        if tracking_events:
            events_to_persist.extend(tracking_events)
        events_to_persist.extend(zone_events)
        events_to_persist.extend(alert_events)
        events_to_persist.extend(evidence_events)

        t_db_start = time.perf_counter()
        if events_to_persist:
            await self.event_store.record_events_batch(events_to_persist, publish=True)
            self._total_alerts += len(alert_events)
        t_db_end = time.perf_counter()
        self._last_persistence_ms = (t_db_end - t_db_start) * 1000.0

        t_end = time.perf_counter()
        self._last_total_ms = (t_end - t0) * 1000.0
        self._frames_processed += 1
        self._total_detections += len(detections)

        # Performance Watchdog & Adaptive Stride Evaluation
        self._record_latency(self._last_total_ms)
        self._evaluate_adaptive_stride()

        return FrameProcessingResult(
            frame_number=frame.frame_number,
            detections=detections,
            tracks=tracks,
            zone_events=zone_events,
            alert_events=alert_events,
            tracking_events=tracking_events,
            evidence_events=evidence_events,
            inference_latency_ms=self._last_inference_ms,
            tracking_latency_ms=self._last_tracking_ms,
            persistence_latency_ms=self._last_persistence_ms,
            total_latency_ms=self._last_total_ms,
        )

    def process_frame_sync(self, frame: FrameData) -> FrameProcessingResult:
        """
        Synchronous version of process_frame for use in thread pool workers.
        Runs YOLO detection + tracking directly (no asyncio).
        Skips persistence to avoid DB contention from background threads.
        Returns tracks and detections for the render pipeline.
        """
        if not self._is_initialized:
            self.initialize()

        if frame is None or frame.image is None:
            return FrameProcessingResult(
                frame_number=0 if frame is None else frame.frame_number,
                detections=[], tracks=[], zone_events=[],
                alert_events=[], tracking_events=[], evidence_events=[],
            )

        # --- Multi-Modal Normalization via SensorFrameAdapter ---
        from backend.ingestion.sensor_adapter import SensorFrameAdapter
        modality = getattr(frame, "modality", "STANDARD")
        norm_image = SensorFrameAdapter.normalize_frame(frame.image, modality=modality)

        # --- YOLO Detection (synchronous, runs in worker thread) ---
        t_det_start = time.perf_counter()
        detections = self.detector.detect(norm_image)
        t_det_end = time.perf_counter()
        self._last_inference_ms = (t_det_end - t_det_start) * 1000.0
        self._total_detections += len(detections)

        # --- ByteTrack update ---
        t_track_start = time.perf_counter()
        tracks = self.tracker.update(detections, frame)
        t_track_end = time.perf_counter()
        self._last_tracking_ms = (t_track_end - t_track_start) * 1000.0
        self._last_tracks = tracks

        # --- Zone evaluation (lightweight, sync-safe) ---
        zone_events, alert_events = self.zone_monitor.evaluate_tracks(
            tracks=tracks, camera_id=frame.camera_id, source=frame.source,
        )

        # --- Publish IncidentEvent for each alert so WebSocket clients get real-time INCIDENT updates ---
        incident_events: list = []
        for ae in alert_events:
            inc_id = getattr(ae, "incident_id", None)
            if inc_id:
                incident_events.append(
                    IncidentEvent(
                        camera_id=ae.camera_id,
                        track_id=ae.track_id,
                        incident_id=inc_id,
                        confidence=ae.confidence,
                        source=ae.source,
                        timestamp=ae.timestamp,
                        lifecycle="opened",
                        severity=ae.severity,
                        message=ae.message,
                    )
                )

        # --- Tick incident engine to resolve dormant/grace-expired incidents ---
        from backend.incidents.engine import get_incident_engine
        resolved_recs = get_incident_engine().tick()
        for rec in resolved_recs:
            incident_events.append(
                IncidentEvent(
                    camera_id=rec.camera_id,
                    incident_id=rec.incident_id,
                    timestamp=rec.last_updated,
                    lifecycle="closed",
                    severity=rec.severity,
                    message=f"Incident {rec.incident_id} resolved",
                )
            )

        # --- Capture forensic evidence and analytics across all tiers ---
        evidence_events: List[EvidenceEvent] = []
        if frame.image is not None and frame.image.size > 0:
            evidence_events = self._evaluate_evidence_and_analytics(
                frame=frame,
                tracks=tracks,
                alert_events=alert_events,
            )

        if alert_events:
            self._total_alerts += len(alert_events)

        t_end = time.perf_counter()
        self._last_total_ms = (t_end - t_det_start) * 1000.0
        self._frames_processed += 1

        # Record latency for adaptive stride controller
        self._record_latency(self._last_total_ms)
        self._evaluate_adaptive_stride()

        return FrameProcessingResult(
            frame_number=frame.frame_number,
            detections=detections,
            tracks=tracks,
            zone_events=zone_events,
            alert_events=alert_events + incident_events,
            tracking_events=[],
            evidence_events=evidence_events,
            inference_latency_ms=self._last_inference_ms,
            tracking_latency_ms=self._last_tracking_ms,
            persistence_latency_ms=0.0,
            total_latency_ms=self._last_total_ms,
        )
