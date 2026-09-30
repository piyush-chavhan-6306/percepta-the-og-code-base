"""
Border Intelligence ByteTrack Wrapper Module.
Wraps ByteTrack multi-object tracking behind the platform's BaseTracker contract,
managing bounded trajectories, velocity vectors, and track lifecycle state.
"""
from collections import deque
from datetime import datetime, timezone
import logging
from types import SimpleNamespace
from typing import Any, Deque, Dict, List, Optional, Set, Tuple
import numpy as np
import torch
from ultralytics.trackers.byte_tracker import BYTETracker

from backend.detection.detector import DetectionResult
from backend.ingestion.adapter import FrameData
from backend.tracking.movement import calculate_movement_vector
from backend.tracking.tracker import BaseTracker, TrackedObject

logger = logging.getLogger(__name__)


class _DetectionBoxAdapter:
    """Internal adapter to feed standard DetectionResults into BYTETracker."""

    def __init__(
        self,
        xyxy: Any,
        conf: Any,
        cls: Any,
    ) -> None:
        if len(xyxy) == 0:
            self.xyxy = torch.zeros((0, 4), dtype=torch.float32)
            self.xywh = torch.zeros((0, 4), dtype=torch.float32)
            self.conf = torch.zeros((0,), dtype=torch.float32)
            self.cls = torch.zeros((0,), dtype=torch.float32)
        else:
            if isinstance(xyxy, torch.Tensor):
                self.xyxy = xyxy.float()
            else:
                self.xyxy = torch.tensor(xyxy, dtype=torch.float32)

            x1, y1, x2, y2 = self.xyxy[:, 0], self.xyxy[:, 1], self.xyxy[:, 2], self.xyxy[:, 3]
            self.xywh = torch.stack([(x1 + x2) / 2.0, (y1 + y2) / 2.0, x2 - x1, y2 - y1], dim=1)

            if isinstance(conf, torch.Tensor):
                self.conf = conf.float()
            else:
                self.conf = torch.tensor(conf, dtype=torch.float32)

            if isinstance(cls, torch.Tensor):
                self.cls = cls.float()
            else:
                self.cls = torch.tensor(cls, dtype=torch.float32)

    def __getitem__(self, idx: Any) -> "_DetectionBoxAdapter":
        return _DetectionBoxAdapter(self.xyxy[idx], self.conf[idx], self.cls[idx])

    def __len__(self) -> int:
        return len(self.conf)


class ByteTrackTracker(BaseTracker):
    """
    ByteTrack implementation providing persistent multi-object tracking,
    bounded trajectory histories, and motion vectors.
    """

    def __init__(
        self,
        track_high_thresh: float = 0.20,
        track_low_thresh: float = 0.10,
        new_track_thresh: float = 0.20,
        track_buffer: int = 90,
        match_thresh: float = 0.80,
        max_trajectory_history: int = 60,
        fps: float = 30.0,
        min_hits: int = 1,
    ) -> None:
        self.track_high_thresh = track_high_thresh
        self.track_low_thresh = track_low_thresh
        self.new_track_thresh = new_track_thresh
        self.track_buffer = track_buffer
        self.match_thresh = match_thresh
        self.max_trajectory_history = max_trajectory_history
        self.fps = fps
        self.min_hits = min_hits

        self._tracker: Optional[BYTETracker] = None
        self._trajectories: Dict[str, Deque[Tuple[float, float]]] = {}
        self._active_tracks: Dict[str, TrackedObject] = {}
        self._track_classes: Dict[str, str] = {}
        self._is_initialized = False

    def initialize(self) -> None:
        """Initialize the underlying BYTETracker instance."""
        args = SimpleNamespace(
            track_high_thresh=self.track_high_thresh,
            track_low_thresh=self.track_low_thresh,
            new_track_thresh=self.new_track_thresh,
            track_buffer=self.track_buffer,
            match_thresh=self.match_thresh,
            fuse_score=True,
        )
        self._tracker = BYTETracker(args)
        self._trajectories.clear()
        self._active_tracks.clear()
        self._track_classes.clear()
        self._is_initialized = True
        logger.info("ByteTrackTracker initialized successfully.")

    def reset(self) -> None:
        """Reset tracker state and clear active trajectories."""
        self.initialize()

    def update(
        self,
        detections: Optional[List[DetectionResult]],
        frame: FrameData,
    ) -> List[TrackedObject]:
        """
        Update the tracker with new detections for the given frame.
        Maintains persistent track IDs, updates bounded trajectory history,
        and computes movement vectors.
        """
        if not self._is_initialized or self._tracker is None:
            self.initialize()

        if frame is None or frame.image is None or frame.width <= 0 or frame.height <= 0:
            return []

        w = float(frame.width)
        h = float(frame.height)
        fps = frame.fps if frame.fps > 0 else self.fps
        timestamp = frame.timestamp if frame.timestamp is not None else datetime.now(timezone.utc)
        frame_number = frame.frame_number

        valid_detections: List[DetectionResult] = []
        if detections:
            for det in detections:
                if det is None:
                    continue
                # Validate bounding box
                box = det.bounding_box
                if len(box) == 4 and box[2] > box[0] and box[3] > box[1]:
                    valid_detections.append(det)

        if not valid_detections:
            det_adapter = _DetectionBoxAdapter([], [], [])
        else:
            xyxy_list = [d.bounding_box for d in valid_detections]
            conf_list = [d.confidence for d in valid_detections]
            cls_list = [d.class_id for d in valid_detections]
            det_adapter = _DetectionBoxAdapter(xyxy_list, conf_list, cls_list)

        # Run ByteTrack update
        try:
            track_outputs = self._tracker.update(det_adapter, img=frame.image)
        except Exception as e:
            logger.error(f"BYTETracker update error: {e}")
            return []

        current_active_ids: Set[str] = set()
        updated_tracks: List[TrackedObject] = []

        if track_outputs is not None and len(track_outputs) > 0:
            for row in track_outputs:
                if len(row) < 7:
                    continue

                x1, y1, x2, y2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                track_id_int = int(row[4])
                track_id_str = str(track_id_int)
                conf = float(row[5])
                cls_id = int(row[6])

        # Match class name from detections if available
                class_name = "object"
                for d in valid_detections:
                    if d.class_id == cls_id:
                        class_name = d.class_name
                        break

                # Temporal class voting across rolling history window to eliminate label oscillation
                if not hasattr(self, "_track_class_votes"):
                    self._track_class_votes = {}
                if track_id_str not in self._track_class_votes:
                    self._track_class_votes[track_id_str] = deque(maxlen=20)
                if class_name != "object":
                    self._track_class_votes[track_id_str].append(class_name)

                if self._track_class_votes[track_id_str]:
                    from collections import Counter
                    stable_class = Counter(self._track_class_votes[track_id_str]).most_common(1)[0][0]
                else:
                    stable_class = self._track_classes.get(track_id_str, "object")
                self._track_classes[track_id_str] = stable_class

                # Center calculations
                cx = round((x1 + x2) / 2.0, 2)
                cy = round((y1 + y2) / 2.0, 2)

                # Normalized coordinates
                nx1 = max(0.0, min(1.0, round(x1 / w, 4)))
                ny1 = max(0.0, min(1.0, round(y1 / h, 4)))
                nx2 = max(0.0, min(1.0, round(x2 / w, 4)))
                ny2 = max(0.0, min(1.0, round(y2 / h, 4)))

                # Trajectory management with bounded history
                prev_track = self._active_tracks.get(track_id_str)
                if track_id_str not in self._trajectories:
                    self._trajectories[track_id_str] = deque(maxlen=self.max_trajectory_history)
                    lifecycle = "created"
                    age = 1
                    hits = 1
                    prev_cx = cx
                    prev_cy = cy
                else:
                    lifecycle = "updated"
                    age = (prev_track.age + 1) if prev_track else len(self._trajectories[track_id_str]) + 1
                    hits = (prev_track.hits + 1) if prev_track else 1
                    prev_cx = prev_track.center_x if prev_track else cx
                    prev_cy = prev_track.center_y if prev_track else cy

                # Calculate movement vector, heading and honest speed label
                trajectory_history = list(self._trajectories[track_id_str]) + [(cx, cy)]
                from backend.tracking.movement import format_speed_label
                mv = calculate_movement_vector(trajectory_history, fps=fps)
                speed_desc = format_speed_label(mv.speed_px_per_sec, not mv.is_moving)

                # Adaptive temporal bounding-box smoothing with stationary deadband
                if prev_track and prev_track.bounding_box and len(prev_track.bounding_box) >= 4 and not mv.is_moving:
                    # Stationary object deadband: strongly damp subpixel detector jitter
                    prev_b = prev_track.bounding_box
                    alpha = 0.85
                    x1 = alpha * prev_b[0] + (1.0 - alpha) * x1
                    y1 = alpha * prev_b[1] + (1.0 - alpha) * y1
                    x2 = alpha * prev_b[2] + (1.0 - alpha) * x2
                    y2 = alpha * prev_b[3] + (1.0 - alpha) * y2
                    cx = round((x1 + x2) / 2.0, 2)
                    cy = round((y1 + y2) / 2.0, 2)
                    nx1 = max(0.0, min(1.0, round(x1 / w, 4)))
                    ny1 = max(0.0, min(1.0, round(y1 / h, 4)))
                    nx2 = max(0.0, min(1.0, round(x2 / w, 4)))
                    ny2 = max(0.0, min(1.0, round(y2 / h, 4)))

                self._trajectories[track_id_str].append((cx, cy))
                trajectory_list = list(self._trajectories[track_id_str])

                tracked_obj = TrackedObject(
                    track_id=track_id_str,
                    object_class=stable_class,
                    confidence=round(conf, 4),
                    bounding_box=[round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                    normalized_box=[nx1, ny1, nx2, ny2],
                    frame_number=frame_number,
                    timestamp=timestamp,
                    center_x=cx,
                    center_y=cy,
                    prev_center_x=prev_cx,
                    prev_center_y=prev_cy,
                    velocity=(mv.dx, mv.dy),
                    speed_px_per_frame=mv.speed_px_per_frame,
                    direction_deg=mv.direction_deg,
                    cardinal_heading=mv.cardinal_heading,
                    speed_description=speed_desc,
                    lifecycle=lifecycle,
                    trajectory=trajectory_list,
                    current_zone=prev_track.current_zone if prev_track else None,
                    previous_zone=prev_track.previous_zone if prev_track else None,
                    zone_entry_time=prev_track.zone_entry_time if prev_track else None,
                    zone_dwell_seconds=prev_track.zone_dwell_seconds if prev_track else 0.0,
                    movement_state="MOVING" if mv.is_moving else "STATIONARY",
                    hits=hits,
                    age=age,
                    time_since_update=0,
                    provenance="detection",
                    global_id=prev_track.global_id if prev_track else None,
                    global_confidence=prev_track.global_confidence if prev_track else None,
                )

                self._active_tracks[track_id_str] = tracked_obj
                current_active_ids.add(track_id_str)

                # Track confirmation threshold (configurable via min_hits)
                if hits >= self.min_hits:
                    updated_tracks.append(tracked_obj)

        # Handle lost tracks: provide temporal grace persistence (up to 3 frames)
        # Prevents flickering off and on when a detector momentarily misses a frame
        stale_ids = [tid for tid in list(self._active_tracks.keys()) if tid not in current_active_ids]
        for tid in stale_ids:
            if tid in self._active_tracks:
                obj = self._active_tracks[tid]
                obj.time_since_update += 1
                if obj.time_since_update <= 3 and obj.hits >= self.min_hits:
                    # Extrapolate position using velocity during brief dropout
                    dx, dy = obj.velocity
                    new_b = [
                        max(0.0, min(w, obj.bounding_box[0] + dx)),
                        max(0.0, min(h, obj.bounding_box[1] + dy)),
                        max(0.0, min(w, obj.bounding_box[2] + dx)),
                        max(0.0, min(h, obj.bounding_box[3] + dy)),
                    ]
                    obj.bounding_box = [round(v, 2) for v in new_b]
                    obj.provenance = "prediction"
                    updated_tracks.append(obj)
                elif obj.time_since_update > self.track_buffer:
                    del self._active_tracks[tid]
                    if tid in self._trajectories:
                        del self._trajectories[tid]
                    if tid in self._track_classes:
                        del self._track_classes[tid]
                    if hasattr(self, "_track_class_votes") and tid in self._track_class_votes:
                        del self._track_class_votes[tid]

        return updated_tracks

    def get_active_tracks(self) -> List[TrackedObject]:
        """Return the current active tracked objects."""
        return list(self._active_tracks.values())

    def predict_step(self, frame: FrameData) -> List[TrackedObject]:
        """
        Advance tracker motion state on intermediate frames without fresh YOLO detections.
        Applies velocity displacement to active bounding boxes and trajectories.
        Returns predicted tracks explicitly tagged with provenance='prediction'.
        """
        if not self._is_initialized or frame is None:
            return []

        w = float(frame.width) if frame.width > 0 else 640.0
        h = float(frame.height) if frame.height > 0 else 480.0
        fps = frame.fps if frame.fps > 0 else self.fps
        timestamp = frame.timestamp if frame.timestamp is not None else datetime.now(timezone.utc)
        frame_number = frame.frame_number

        predicted_tracks: List[TrackedObject] = []

        for track_id_str, prev in list(self._active_tracks.items()):
            if prev.time_since_update > 2:
                continue

            dx, dy = prev.velocity
            # Clamp displacement to avoid wild projections if velocity had sudden jitter
            dx_clamped = max(-50.0, min(50.0, dx))
            dy_clamped = max(-50.0, min(50.0, dy))

            new_x1 = max(0.0, min(w, prev.bounding_box[0] + dx_clamped))
            new_y1 = max(0.0, min(h, prev.bounding_box[1] + dy_clamped))
            new_x2 = max(0.0, min(w, prev.bounding_box[2] + dx_clamped))
            new_y2 = max(0.0, min(h, prev.bounding_box[3] + dy_clamped))

            cx = round((new_x1 + new_x2) / 2.0, 2)
            cy = round((new_y1 + new_y2) / 2.0, 2)

            nx1 = max(0.0, min(1.0, round(new_x1 / w, 4)))
            ny1 = max(0.0, min(1.0, round(new_y1 / h, 4)))
            nx2 = max(0.0, min(1.0, round(new_x2 / w, 4)))
            ny2 = max(0.0, min(1.0, round(new_y2 / h, 4)))

            if track_id_str in self._trajectories:
                self._trajectories[track_id_str].append((cx, cy))
                trajectory_list = list(self._trajectories[track_id_str])
            else:
                trajectory_list = [(cx, cy)]

            from backend.tracking.movement import format_speed_label
            mv = calculate_movement_vector(trajectory_list, fps=fps)
            speed_desc = format_speed_label(mv.speed_px_per_sec, not mv.is_moving)

            predicted_obj = TrackedObject(
                track_id=track_id_str,
                object_class=prev.object_class,
                confidence=prev.confidence,
                bounding_box=[round(new_x1, 2), round(new_y1, 2), round(new_x2, 2), round(new_y2, 2)],
                normalized_box=[nx1, ny1, nx2, ny2],
                frame_number=frame_number,
                timestamp=timestamp,
                center_x=cx,
                center_y=cy,
                prev_center_x=prev.center_x,
                prev_center_y=prev.center_y,
                velocity=(mv.dx, mv.dy),
                speed_px_per_frame=mv.speed_px_per_frame,
                direction_deg=mv.direction_deg,
                cardinal_heading=mv.cardinal_heading,
                speed_description=speed_desc,
                lifecycle="updated",
                trajectory=trajectory_list,
                current_zone=prev.current_zone,
                previous_zone=prev.previous_zone,
                zone_entry_time=prev.zone_entry_time,
                zone_dwell_seconds=prev.zone_dwell_seconds,
                movement_state="MOVING" if mv.is_moving else "STATIONARY",
                hits=prev.hits,
                age=prev.age + 1,
                time_since_update=prev.time_since_update,
                provenance="prediction",
            )
            self._active_tracks[track_id_str] = predicted_obj
            predicted_tracks.append(predicted_obj)

        return predicted_tracks
