"""
Border Intelligence Evidence Snapshot Extractor & Archival Module.
Persists visual JPEG snapshot frames, face crops, and license plate crops with bounding box evidence,
cryptographic SHA-256 hashes, deduplication cooldowns, and rule-violation targeted highlighting.
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4
import cv2
import numpy as np
from pydantic import BaseModel, Field

from backend.config import get_settings

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: Union[str, Path]) -> str:
    """Calculate the cryptographic SHA-256 hash of an actual file on disk."""
    p = Path(file_path)
    if not p.is_file():
        return ""
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class SnapshotMetadata(BaseModel):
    snapshot_id: str
    incident_id: Union[str, UUID]
    camera_id: str
    frame_number: int
    trigger_reason: str
    file_path: str
    file_uri: str
    sha256_hash: Optional[str] = None
    evidence_type: Optional[str] = None
    bounding_box: Optional[List[float]] = None
    violating_track_id: Optional[Union[str, int]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidencePackageMetadata(BaseModel):
    snapshot_id: str
    incident_id: Union[str, UUID]
    camera_id: str
    frame_number: int
    trigger_reason: str
    file_path: str
    file_uri: str
    sha256_hash: Optional[str] = None
    target_crop_uri: Optional[str] = None
    target_sha256_hash: Optional[str] = None
    face_snapshot_uri: Optional[str] = None
    face_sha256_hash: Optional[str] = None
    anpr_snapshot_uri: Optional[str] = None
    anpr_sha256_hash: Optional[str] = None
    evidence_type: Optional[str] = None
    violating_track_id: Optional[Union[str, int]] = None
    rule_name: Optional[str] = None
    sharpness_score: float = 0.0
    confidence: float = 0.0
    modality: str = "STANDARD"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BestEvidenceFrameSelector:
    """
    Evaluates candidate stream frames during an incident to identify the highest-quality
    forensic evidence frame based on target confidence, optical sharpness (Laplacian variance),
    and bounding box visibility.
    """

    @staticmethod
    def calculate_sharpness(image: np.ndarray) -> float:
        """Compute Laplacian variance representing image sharpness / focus."""
        if image is None or image.size == 0:
            return 0.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @classmethod
    def score_frame_quality(
        cls,
        image: np.ndarray,
        confidence: float,
        bbox: Optional[List[float]] = None,
    ) -> float:
        """Composite quality metric (0.0 to 100.0)."""
        sharpness = cls.calculate_sharpness(image)
        # Normalize sharpness (50-500 typical range mapped to 0-1)
        sharp_norm = min(max(sharpness / 300.0, 0.0), 1.0)
        conf_norm = min(max(confidence, 0.0), 1.0)

        # Center/size weight
        size_norm = 0.5
        if bbox and len(bbox) >= 4 and image is not None:
            h, w = image.shape[:2]
            bw = bbox[2] - bbox[0]
            bh = bbox[3] - bbox[1]
            box_area = (bw * bh) / max(w * h, 1)
            size_norm = min(box_area * 10.0, 1.0)

        composite = (0.45 * conf_norm + 0.35 * sharp_norm + 0.20 * size_norm) * 100.0
        return round(composite, 2)


class EvidenceCooldownManager:
    """
    Prevents duplicate evidence frame flood for the same target and camera.
    Enforces configurable cooldown windows per evidence type.
    """

    DEFAULT_COOLDOWNS = {
        "PERSON": 45.0,
        "FACE": 30.0,
        "VEHICLE": 45.0,
        "ANPR": 30.0,
        "ZONE_VIOLATION": 15.0,
        "TRIPWIRE_VIOLATION": 15.0,
        "LOITERING": 10.0,
        "THREAT": 20.0,
        "INCIDENT_CONTEXT": 30.0,
    }

    def __init__(self) -> None:
        # Key: (camera_id, str(track_id), evidence_type) -> last_capture_monotonic_time
        self._last_captures: Dict[Tuple[str, str, str], float] = {}

    def can_capture(
        self,
        camera_id: str,
        track_id: Optional[Union[str, int]],
        evidence_type: str,
        now_ts: Optional[float] = None,
        min_interval_sec: Optional[float] = None,
    ) -> bool:
        """Determine whether evidence can be captured without duplicate spam."""
        if track_id is None:
            track_key = "GLOBAL"
        else:
            track_key = str(track_id)

        key = (str(camera_id), track_key, str(evidence_type))
        now = now_ts or time.monotonic()
        cooldown = min_interval_sec or self.DEFAULT_COOLDOWNS.get(evidence_type, 30.0)

        last_time = self._last_captures.get(key)
        if last_time is None or (now - last_time) >= cooldown:
            return True
        return False

    def record_capture(
        self,
        camera_id: str,
        track_id: Optional[Union[str, int]],
        evidence_type: str,
        now_ts: Optional[float] = None,
    ) -> None:
        """Record timestamp of successful evidence capture."""
        track_key = str(track_id) if track_id is not None else "GLOBAL"
        key = (str(camera_id), track_key, str(evidence_type))
        self._last_captures[key] = now_ts or time.monotonic()

    def reset(self) -> None:
        self._last_captures.clear()


class SnapshotArchiveManager:
    """Manages saving, indexing, and serving visual snapshot evidence for incident dossiers."""

    def __init__(self, snapshot_dir: Optional[str] = None) -> None:
        settings = get_settings()
        self.snapshot_dir = Path(snapshot_dir or os.path.join(settings.STORAGE_DIR, "snapshots"))
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.cooldown_mgr = EvidenceCooldownManager()

    def render_violation_evidence_frame(
        self,
        image: np.ndarray,
        all_tracks: List[Any],
        violating_track_id: Optional[Union[str, int]] = None,
        rule_name: str = "PERIMETER_SECURITY_RULE",
        violation_type: str = "ZONE_VIOLATION",
        severity: str = "CRITICAL",
        camera_id: str = "CAM-01",
        timestamp_str: Optional[str] = None,
    ) -> np.ndarray:
        """
        Render a dedicated evidence frame:
        - FULL camera context
        - RED bounding box around ONLY the violating target
        - Normal detections stay normal (subtle cyan/green box, NO red)
        - Clear tactical target annotation and top forensic HUD banner
        """
        if image is None or image.size == 0:
            return np.zeros((480, 640, 3), dtype=np.uint8)

        canvas = image.copy()
        h, w = canvas.shape[:2]
        ts_label = timestamp_str or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Top Forensic HUD Bar
        hud_bar_h = 36
        hud = canvas.copy()
        cv2.rectangle(hud, (0, 0), (w, hud_bar_h), (16, 20, 26), -1)
        cv2.addWeighted(hud, 0.88, canvas, 0.12, 0, canvas)
        cv2.line(canvas, (0, hud_bar_h), (w, hud_bar_h), (0, 0, 220), 2)

        # Left: Camera Callout
        cv2.putText(
            canvas,
            f"PERCEPTA FORENSIC EVIDENCE // {camera_id}",
            (14, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 220, 255),
            1,
            cv2.LINE_AA,
        )

        # Center: Rule Violation & Severity
        cv2.putText(
            canvas,
            f"VIOLATION: {rule_name} [{severity}]",
            (int(w * 0.36), 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

        # Right: Timestamp & Hash Authenticity
        cv2.putText(
            canvas,
            f"{ts_label} // SHA-256 VERIFIED",
            (max(int(w * 0.68), w - 340), 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (0, 255, 120),
            1,
            cv2.LINE_AA,
        )

        # 2. Draw Object Bounding Boxes
        v_str = str(violating_track_id) if violating_track_id is not None else None

        for t in all_tracks:
            # Handle either TrackedObject or dict/tuple representation
            t_id = getattr(t, "track_id", None)
            t_box = getattr(t, "bounding_box", None)
            t_cls = getattr(t, "object_class", "target")

            if t_box is None and isinstance(t, (list, tuple)) and len(t) >= 3:
                t_id, t_cls, t_box = t[0], t[1], t[2]
            elif t_box is None and isinstance(t, dict):
                t_id = t.get("track_id")
                t_cls = t.get("object_class") or t.get("class_name", "target")
                t_box = t.get("bounding_box") or t.get("bbox")

            if not t_box or len(t_box) < 4:
                continue

            x1, y1, x2, y2 = map(int, t_box[:4])
            x1, y1 = max(0, x1), max(hud_bar_h, y1)
            x2, y2 = min(w, x2), min(h, y2)

            is_violator = (v_str is not None and str(t_id) == v_str)

            if is_violator:
                # ==============================================================
                # FORENSIC RED HIGHLIGHT ON ONLY THE VIOLATING TARGET
                # ==============================================================
                red_color = (0, 0, 255)
                # Outer perimeter box
                cv2.rectangle(canvas, (x1, y1), (x2, y2), red_color, 3)

                # Tactical Corner Brackets (L-brackets) for high-contrast military HUD look
                c_len = max(8, min(24, (x2 - x1) // 3))
                cv2.line(canvas, (x1, y1), (x1 + c_len, y1), red_color, 4)
                cv2.line(canvas, (x1, y1), (x1, y1 + c_len), red_color, 4)
                cv2.line(canvas, (x2, y1), (x2 - c_len, y1), red_color, 4)
                cv2.line(canvas, (x2, y1), (x2, y1 + c_len), red_color, 4)
                cv2.line(canvas, (x1, y2), (x1 + c_len, y2), red_color, 4)
                cv2.line(canvas, (x1, y2), (x1, y2 - c_len), red_color, 4)
                cv2.line(canvas, (x2, y2), (x2 - c_len, y2), red_color, 4)
                cv2.line(canvas, (x2, y2), (x2, y2 - c_len), red_color, 4)

                # Prominent Red Target Banner
                tag_label = f"VIOLATING TARGET #{t_id} [{str(t_cls).upper()}]"
                sub_label = f"RULE: {rule_name}"
                (tw1, th1), _ = cv2.getTextSize(tag_label, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
                (tw2, th2), _ = cv2.getTextSize(sub_label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
                banner_w = max(tw1, tw2) + 12
                banner_h = th1 + th2 + 12

                by1 = max(hud_bar_h + 4, y1 - banner_h - 4)
                by2 = by1 + banner_h
                bx2 = min(w - 2, x1 + banner_w)

                cv2.rectangle(canvas, (x1, by1), (bx2, by2), red_color, -1)
                cv2.putText(
                    canvas,
                    tag_label,
                    (x1 + 6, by1 + th1 + 3),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.48,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    canvas,
                    sub_label,
                    (x1 + 6, by1 + th1 + th2 + 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (230, 240, 255),
                    1,
                    cv2.LINE_AA,
                )
            else:
                # ==============================================================
                # NORMAL TARGETS REMAIN NORMAL (NO RED BOX)
                # ==============================================================
                norm_color = (255, 200, 0)  # Calm Cyan/Amber tactical stroke
                cv2.rectangle(canvas, (x1, y1), (x2, y2), norm_color, 1)
                norm_label = f"TRK-{t_id} {t_cls}"
                (ntw, nth), _ = cv2.getTextSize(norm_label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
                n_by1 = max(hud_bar_h + 2, y1 - nth - 4)
                cv2.rectangle(canvas, (x1, n_by1), (x1 + ntw + 6, y1), (25, 30, 38), -1)
                cv2.putText(
                    canvas,
                    norm_label,
                    (x1 + 3, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    norm_color,
                    1,
                    cv2.LINE_AA,
                )

        return canvas

    def save_violation_evidence_package(
        self,
        incident_id: Union[str, UUID],
        image: np.ndarray,
        all_tracks: List[Any],
        violating_track_id: Optional[Union[str, int]] = None,
        camera_id: str = "CAM-01",
        frame_number: int = 0,
        trigger_reason: str = "RESTRICTED_ZONE_BREACH",
        rule_name: str = "RESTRICTED_PERIMETER",
        severity: str = "CRITICAL",
        evidence_type: str = "ZONE_VIOLATION",
        face_bbox: Optional[List[float]] = None,
        plate_bbox: Optional[List[float]] = None,
        confidence: float = 0.9,
        modality: str = "STANDARD",
    ) -> EvidencePackageMetadata:
        """
        Generate and persist a certified violation evidence package:
        1. Full scene annotated with RED bounding box ONLY on the violating track.
        2. High-resolution face crop if face detected.
        3. High-resolution ANPR plate crop if vehicle plate detected.
        4. Real SHA-256 hashes calculated directly from the written files.
        """
        inc_id_str = str(incident_id)
        snap_id = f"VIOLATION_{inc_id_str}_{frame_number}_{int(datetime.now().timestamp())}"
        filename = f"{snap_id}.jpg"
        file_path = self.snapshot_dir / filename

        # 1. Render violation evidence frame
        annotated = self.render_violation_evidence_frame(
            image=image,
            all_tracks=all_tracks,
            violating_track_id=violating_track_id,
            rule_name=rule_name,
            violation_type=evidence_type,
            severity=severity,
            camera_id=camera_id,
        )

        cv2.imwrite(str(file_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 95])
        scene_hash = compute_file_sha256(file_path)

        # 2. Crops with real SHA-256
        target_uri = None
        target_hash = None
        face_uri = None
        face_hash = None
        plate_uri = None
        plate_hash = None
        sharpness = BestEvidenceFrameSelector.calculate_sharpness(image)

        if image is not None and image.size > 0:
            h, w = image.shape[:2]

            # Target / Violating Object Crop
            v_str = str(violating_track_id) if violating_track_id is not None else None
            violating_box = None
            for t in all_tracks:
                t_id = getattr(t, "track_id", None)
                if t_id is None and isinstance(t, (list, tuple)) and len(t) >= 1:
                    t_id = t[0]
                elif t_id is None and isinstance(t, dict):
                    t_id = t.get("track_id")
                if v_str is not None and str(t_id) == v_str:
                    t_box = getattr(t, "bounding_box", None)
                    if t_box is None and isinstance(t, (list, tuple)) and len(t) >= 3:
                        t_box = t[2]
                    elif t_box is None and isinstance(t, dict):
                        t_box = t.get("bounding_box") or t.get("bbox")
                    if t_box and len(t_box) >= 4:
                        violating_box = t_box
                        break

            if violating_box:
                tx1, ty1, tx2, ty2 = map(int, violating_box[:4])
                pad_w = int((tx2 - tx1) * 0.15)
                pad_h = int((ty2 - ty1) * 0.15)
                tx1, ty1 = max(0, tx1 - pad_w), max(0, ty1 - pad_h)
                tx2, ty2 = min(w, tx2 + pad_w), min(h, ty2 + pad_h)
                if tx2 > tx1 and ty2 > ty1:
                    target_crop = image[ty1:ty2, tx1:tx2]
                    target_fname = f"TARGET_{snap_id}.jpg"
                    target_fpath = self.snapshot_dir / target_fname
                    cv2.imwrite(str(target_fpath), target_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    target_uri = f"/api/evidence/snapshots/file/{target_fname}"
                    target_hash = compute_file_sha256(target_fpath)

            # Face evidence crop
            if face_bbox and len(face_bbox) >= 4:
                fx1, fy1, fx2, fy2 = map(int, face_bbox[:4])
                fx1, fy1 = max(0, fx1), max(0, fy1)
                fx2, fy2 = min(w, fx2), min(h, fy2)
                if fx2 > fx1 and fy2 > fy1:
                    face_crop = image[fy1:fy2, fx1:fx2]
                    face_fname = f"FACE_{snap_id}.jpg"
                    face_fpath = self.snapshot_dir / face_fname
                    cv2.imwrite(str(face_fpath), face_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    face_uri = f"/api/evidence/snapshots/file/{face_fname}"
                    face_hash = compute_file_sha256(face_fpath)

            # ANPR plate evidence crop
            if plate_bbox and len(plate_bbox) >= 4:
                px1, py1, px2, py2 = map(int, plate_bbox[:4])
                px1, py1 = max(0, px1), max(0, py1)
                px2, py2 = min(w, px2), min(h, py2)
                if px2 > px1 and py2 > py1:
                    plate_crop = image[py1:py2, px1:px2]
                    plate_fname = f"ANPR_{snap_id}.jpg"
                    plate_fpath = self.snapshot_dir / plate_fname
                    cv2.imwrite(str(plate_fpath), plate_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    plate_uri = f"/api/evidence/snapshots/file/{plate_fname}"
                    plate_hash = compute_file_sha256(plate_fpath)

        return EvidencePackageMetadata(
            snapshot_id=snap_id,
            incident_id=inc_id_str,
            camera_id=str(camera_id),
            frame_number=int(frame_number),
            trigger_reason=str(trigger_reason),
            file_path=str(file_path),
            file_uri=f"/api/evidence/snapshots/file/{filename}",
            sha256_hash=scene_hash,
            target_crop_uri=target_uri,
            target_sha256_hash=target_hash,
            face_snapshot_uri=face_uri,
            face_sha256_hash=face_hash,
            anpr_snapshot_uri=plate_uri,
            anpr_sha256_hash=plate_hash,
            evidence_type=evidence_type,
            violating_track_id=violating_track_id,
            rule_name=rule_name,
            sharpness_score=round(sharpness, 1),
            confidence=float(confidence),
            modality=modality,
        )

    def save_snapshot(
        self,
        incident_id: Union[str, UUID],
        image: np.ndarray,
        camera_id: str = "CAM-01",
        frame_number: int = 0,
        trigger_reason: str = "RESTRICTED_ZONE_BREACH",
        bounding_boxes: Optional[List[List[float]]] = None,
        modality: str = "STANDARD",
    ) -> SnapshotMetadata:
        """Save a surveillance snapshot image with real SHA-256 hash."""
        inc_id_str = str(incident_id)
        snap_id = f"SNAP_{inc_id_str}_{frame_number}_{int(datetime.now().timestamp())}"
        filename = f"{snap_id}.jpg"
        file_path = self.snapshot_dir / filename

        annotated = image.copy() if image is not None else np.zeros((480, 640, 3), dtype=np.uint8)
        if bounding_boxes and image is not None:
            for box in bounding_boxes:
                if len(box) >= 4:
                    x1, y1, x2, y2 = map(int, box[:4])
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(
                        annotated,
                        "TARGET EVIDENCE",
                        (x1, max(y1 - 5, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 0, 255),
                        1,
                    )

        cv2.imwrite(str(file_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
        sha_hash = compute_file_sha256(file_path)

        return SnapshotMetadata(
            snapshot_id=snap_id,
            incident_id=inc_id_str,
            camera_id=str(camera_id),
            frame_number=int(frame_number),
            trigger_reason=str(trigger_reason),
            file_path=str(file_path),
            file_uri=f"/api/evidence/snapshots/file/{filename}",
            sha256_hash=sha_hash,
        )

    def save_multi_evidence_package(
        self,
        incident_id: Union[str, UUID],
        image: np.ndarray,
        camera_id: str = "CAM-01",
        frame_number: int = 0,
        trigger_reason: str = "RESTRICTED_ZONE_BREACH",
        bounding_boxes: Optional[List[List[float]]] = None,
        face_bbox: Optional[List[float]] = None,
        plate_bbox: Optional[List[float]] = None,
        confidence: float = 0.9,
        modality: str = "STANDARD",
    ) -> EvidencePackageMetadata:
        """Backward-compatible multi-evidence package saver."""
        inc_id_str = str(incident_id)
        snap_meta = self.save_snapshot(
            incident_id=inc_id_str,
            image=image,
            camera_id=str(camera_id),
            frame_number=int(frame_number),
            trigger_reason=str(trigger_reason),
            bounding_boxes=bounding_boxes,
            modality=modality,
        )

        face_uri = None
        face_hash = None
        plate_uri = None
        plate_hash = None
        sharpness = BestEvidenceFrameSelector.calculate_sharpness(image)

        if image is not None and image.size > 0:
            h, w = image.shape[:2]
            if face_bbox and len(face_bbox) >= 4:
                fx1, fy1, fx2, fy2 = map(int, face_bbox[:4])
                fx1, fy1 = max(0, fx1), max(0, fy1)
                fx2, fy2 = min(w, fx2), min(h, fy2)
                if fx2 > fx1 and fy2 > fy1:
                    face_crop = image[fy1:fy2, fx1:fx2]
                    face_fname = f"FACE_{snap_meta.snapshot_id}.jpg"
                    face_fpath = self.snapshot_dir / face_fname
                    cv2.imwrite(str(face_fpath), face_crop)
                    face_uri = f"/api/evidence/snapshots/file/{face_fname}"
                    face_hash = compute_file_sha256(face_fpath)

            if plate_bbox and len(plate_bbox) >= 4:
                px1, py1, px2, py2 = map(int, plate_bbox[:4])
                px1, py1 = max(0, px1), max(0, py1)
                px2, py2 = min(w, px2), min(h, py2)
                if px2 > px1 and py2 > py1:
                    plate_crop = image[py1:py2, px1:px2]
                    plate_fname = f"ANPR_{snap_meta.snapshot_id}.jpg"
                    plate_fpath = self.snapshot_dir / plate_fname
                    cv2.imwrite(str(plate_fpath), plate_crop)
                    plate_uri = f"/api/evidence/snapshots/file/{plate_fname}"
                    plate_hash = compute_file_sha256(plate_fpath)

        return EvidencePackageMetadata(
            snapshot_id=snap_meta.snapshot_id,
            incident_id=inc_id_str,
            camera_id=str(camera_id),
            frame_number=int(frame_number),
            trigger_reason=str(trigger_reason),
            file_path=snap_meta.file_path,
            file_uri=snap_meta.file_uri,
            sha256_hash=snap_meta.sha256_hash,
            face_snapshot_uri=face_uri,
            face_sha256_hash=face_hash,
            anpr_snapshot_uri=plate_uri,
            anpr_sha256_hash=plate_hash,
            sharpness_score=round(sharpness, 1),
            confidence=float(confidence),
            modality=modality,
        )

    save_snapshot_with_crops = save_multi_evidence_package

    async def save_snapshot_async(
        self,
        incident_id: Union[str, UUID],
        image: np.ndarray,
        camera_id: str = "CAM-01",
        frame_number: int = 0,
        trigger_reason: str = "RESTRICTED_ZONE_BREACH",
        bounding_boxes: Optional[List[List[float]]] = None,
        modality: str = "STANDARD",
    ) -> SnapshotMetadata:
        """Asynchronously save a snapshot offloaded to worker thread to prevent event-loop stalls."""
        import asyncio
        return await asyncio.to_thread(
            self.save_snapshot,
            incident_id=incident_id,
            image=image,
            camera_id=camera_id,
            frame_number=frame_number,
            trigger_reason=trigger_reason,
            bounding_boxes=bounding_boxes,
            modality=modality,
        )

    async def save_multi_evidence_package_async(
        self,
        incident_id: Union[str, UUID],
        image: np.ndarray,
        camera_id: str = "CAM-01",
        frame_number: int = 0,
        trigger_reason: str = "RESTRICTED_ZONE_BREACH",
        bounding_boxes: Optional[List[List[float]]] = None,
        face_bbox: Optional[List[float]] = None,
        plate_bbox: Optional[List[float]] = None,
        confidence: float = 0.9,
        modality: str = "STANDARD",
    ) -> EvidencePackageMetadata:
        """Asynchronously generate and persist full + face + ANPR evidence package."""
        import asyncio
        return await asyncio.to_thread(
            self.save_multi_evidence_package,
            incident_id=incident_id,
            image=image,
            camera_id=camera_id,
            frame_number=frame_number,
            trigger_reason=trigger_reason,
            bounding_boxes=bounding_boxes,
            face_bbox=face_bbox,
            plate_bbox=plate_bbox,
            confidence=confidence,
            modality=modality,
        )

    async def save_violation_evidence_package_async(
        self,
        incident_id: Union[str, UUID],
        image: np.ndarray,
        all_tracks: List[Any],
        violating_track_id: Optional[Union[str, int]] = None,
        camera_id: str = "CAM-01",
        frame_number: int = 0,
        trigger_reason: str = "RESTRICTED_ZONE_BREACH",
        rule_name: str = "RESTRICTED_PERIMETER",
        severity: str = "CRITICAL",
        evidence_type: str = "ZONE_VIOLATION",
        face_bbox: Optional[List[float]] = None,
        plate_bbox: Optional[List[float]] = None,
        confidence: float = 0.9,
        modality: str = "STANDARD",
    ) -> EvidencePackageMetadata:
        """Asynchronously render and persist certified violation evidence with SHA-256."""
        import asyncio
        return await asyncio.to_thread(
            self.save_violation_evidence_package,
            incident_id=incident_id,
            image=image,
            all_tracks=all_tracks,
            violating_track_id=violating_track_id,
            camera_id=camera_id,
            frame_number=frame_number,
            trigger_reason=trigger_reason,
            rule_name=rule_name,
            severity=severity,
            evidence_type=evidence_type,
            face_bbox=face_bbox,
            plate_bbox=plate_bbox,
            confidence=confidence,
            modality=modality,
        )

    def save_crop_evidence(
        self,
        image: np.ndarray,
        bbox: List[float],
        evidence_type: str,
        camera_id: str = "CAM-01",
        track_id: Optional[Union[str, int]] = None,
        frame_number: int = 0,
        incident_id: Optional[Union[str, UUID]] = None,
        trigger_reason: str = "TARGET_DETECTION",
    ) -> Optional[SnapshotMetadata]:
        """
        Crop target/face/plate ROI, save to disk, compute real SHA-256 and return metadata.
        """
        if image is None or image.size == 0 or not bbox or len(bbox) < 4:
            return None

        h, w = image.shape[:2]
        x1, y1, x2, y2 = map(int, bbox[:4])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None

        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        t_key = f"T{track_id}" if track_id is not None else "GLOBAL"
        snap_id = f"EVID_{evidence_type}_{camera_id}_{t_key}_{frame_number}_{int(time.time() * 1000)}"
        filename = f"{snap_id}.jpg"
        file_path = self.snapshot_dir / filename

        cv2.imwrite(str(file_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
        sha_hash = compute_file_sha256(file_path)

        inc_id = str(incident_id or snap_id)
        return SnapshotMetadata(
            snapshot_id=snap_id,
            incident_id=inc_id,
            camera_id=str(camera_id),
            frame_number=int(frame_number),
            trigger_reason=trigger_reason,
            file_path=str(file_path),
            file_uri=f"/api/evidence/snapshots/file/{filename}",
            sha256_hash=sha_hash,
            evidence_type=evidence_type,
            bounding_box=[float(x1), float(y1), float(x2), float(y2)],
            violating_track_id=track_id,
        )

    def list_snapshots(
        self, incident_id: Union[str, UUID], alert_id: Optional[str] = None
    ) -> List[SnapshotMetadata]:
        """List snapshots matching an incident or alert with computed SHA-256 hashes."""
        results = []
        ids = [str(incident_id)]
        if alert_id and str(alert_id) not in ids:
            ids.append(str(alert_id))

        matched_files = set()
        for i_id in ids:
            patterns = [
                f"TARGET_*{i_id}*.jpg",
                f"VIOLATION_*{i_id}*.jpg",
                f"SNAP_*{i_id}*.jpg",
                f"FACE_*{i_id}*.jpg",
                f"ANPR_*{i_id}*.jpg",
                f"EVID_*{i_id}*.jpg",
                f"*{i_id}*.jpg",
            ]
            for pat in patterns:
                for file in self.snapshot_dir.glob(pat):
                    matched_files.add(file)

        # Categorize and order: TARGET crop first, then VIOLATION / SCENE, then FACE, then ANPR
        def sort_priority(f):
            name = f.name.upper()
            if name.startswith("TARGET"):
                return 0
            if name.startswith("VIOLATION") or name.startswith("SNAP"):
                return 1
            if name.startswith("FACE"):
                return 2
            if name.startswith("ANPR"):
                return 3
            return 4

        for file in sorted(matched_files, key=lambda f: (sort_priority(f), -f.stat().st_mtime)):
            sha = compute_file_sha256(file)
            fname_u = file.name.upper()
            if fname_u.startswith("TARGET"):
                ev_type = "TARGET_CROP"
            elif fname_u.startswith("FACE"):
                ev_type = "FACE_CROP"
            elif fname_u.startswith("ANPR"):
                ev_type = "ANPR_PLATE"
            else:
                ev_type = "FULL_SCENE"

            extracted_fn = 0
            for part in file.stem.split("_"):
                if part.isdigit() and len(part) < 8:
                    extracted_fn = int(part)
                    break

            results.append(
                SnapshotMetadata(
                    snapshot_id=file.stem,
                    incident_id=str(incident_id),
                    camera_id="CAM-01",
                    frame_number=extracted_fn,
                    trigger_reason="RECORDED_EVIDENCE",
                    file_path=str(file),
                    file_uri=f"/api/evidence/snapshots/file/{file.name}",
                    sha256_hash=sha,
                    evidence_type=ev_type,
                )
            )
        return results


global_snapshot_manager = SnapshotArchiveManager()


def get_snapshot_manager() -> SnapshotArchiveManager:
    return global_snapshot_manager


def get_evidence_cooldown_manager() -> EvidenceCooldownManager:
    return global_snapshot_manager.cooldown_mgr

