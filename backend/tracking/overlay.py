"""
Border Intelligence Frame Overlay Renderer.

Burns real detection/tracking geometry into the frame server-side so the browser
receives pixels that already agree with the model output. This removes any
possibility of client-side coordinate drift or "video plays but boxes are stale".

All coordinates consumed here are pixel coordinates in the source frame:
  - TrackedObject.bounding_box -> [x1, y1, x2, y2]
  - SecurityZone.polygon       -> [(x, y), ...]
  - VirtualBoundary.pt1/pt2    -> (x, y)
"""
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import cv2
import numpy as np

from backend.tracking.tracker import TrackedObject
from backend.zones.security_zone import SecurityZone, VirtualBoundary

# Tactical palette, expressed in OpenCV BGR to match the frontend design tokens.
C2_CYAN = (255, 229, 0)      # #00e5ff
C2_EMERALD = (118, 230, 0)   # #00e676
C2_AMBER = (0, 171, 255)     # #ffab00
C2_ORANGE = (0, 109, 255)    # #ff6d00
C2_CRIMSON = (68, 23, 255)   # #ff1744
C2_BLUE = (255, 121, 41)     # #2979ff
C2_WHITE = (245, 245, 245)

SEVERITY_COLORS: Dict[str, Tuple[int, int, int]] = {
    "info": C2_CYAN,
    "warning": C2_AMBER,
    "restricted": C2_ORANGE,
    "critical": C2_CRIMSON,
}

# Person vs vehicle classes get distinct colors so the demo reads clearly.
_VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle", "train", "boat", "airplane"}

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _severity_color(severity) -> Tuple[int, int, int]:
    value = getattr(severity, "value", severity)
    return SEVERITY_COLORS.get(str(value).lower(), C2_ORANGE)


def _track_color(track: TrackedObject) -> Tuple[int, int, int]:
    if track.object_class in _VEHICLE_CLASSES:
        return C2_BLUE
    return C2_CYAN


def _dim(color: Tuple[int, int, int], factor: float = 0.55) -> Tuple[int, int, int]:
    return tuple(int(c * factor) for c in color)  # type: ignore[return-value]


def _dashed_line(
    img: np.ndarray,
    pt1: Tuple[int, int],
    pt2: Tuple[int, int],
    color: Tuple[int, int, int],
    thickness: int = 1,
    dash: int = 9,
) -> None:
    """Draw a dashed line segment (OpenCV has no native dashed stroke)."""
    x1, y1 = pt1
    x2, y2 = pt2
    length = int(np.hypot(x2 - x1, y2 - y1))
    if length == 0:
        return
    steps = max(1, length // dash)
    for i in range(steps):
        if i % 2:
            continue
        a = i / steps
        b = min(1.0, (i + 1) / steps)
        cv2.line(
            img,
            (int(x1 + (x2 - x1) * a), int(y1 + (y2 - y1) * a)),
            (int(x1 + (x2 - x1) * b), int(y1 + (y2 - y1) * b)),
            color,
            thickness,
            cv2.LINE_AA,
        )


def _dashed_rect(
    img: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: Tuple[int, int, int],
    thickness: int = 1,
) -> None:
    _dashed_line(img, (x1, y1), (x2, y1), color, thickness)
    _dashed_line(img, (x2, y1), (x2, y2), color, thickness)
    _dashed_line(img, (x2, y2), (x1, y2), color, thickness)
    _dashed_line(img, (x1, y2), (x1, y1), color, thickness)


def _label(
    img: np.ndarray,
    text: str,
    x: int,
    y: int,
    color: Tuple[int, int, int],
    scale: float = 0.42,
) -> None:
    """Draw a compact filled label chip with dark text, clamped inside the frame."""
    h, w = img.shape[:2]
    (tw, th), baseline = cv2.getTextSize(text, _FONT, scale, 1)
    pad = 3
    box_h = th + baseline + pad
    top = y - box_h
    if top < 0:  # flip below the box when there is no room above
        top = y
    top = max(0, min(h - box_h, top))
    left = max(0, min(w - (tw + 2 * pad), x))
    cv2.rectangle(img, (left, top), (left + tw + 2 * pad, top + box_h), color, -1)
    cv2.putText(
        img,
        text,
        (left + pad, top + th + pad - 1),
        _FONT,
        scale,
        (12, 12, 12),
        1,
        cv2.LINE_AA,
    )


def draw_zones(
    img: np.ndarray,
    zones: Iterable[SecurityZone],
    boundaries: Iterable[VirtualBoundary],
) -> None:
    """Render configured geofence polygons and directional tripwires."""
    overlay = None
    h_canvas, w_canvas = img.shape[:2]

    for zone in zones:
        if not zone.is_active or not zone.polygon or len(zone.polygon) < 3:
            continue
        color = _severity_color(zone.severity)
        is_normalized = all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in zone.polygon)
        if is_normalized:
            pts = np.array([[int(round(x * w_canvas)), int(round(y * h_canvas))] for x, y in zone.polygon], dtype=np.int32)
        else:
            pts = np.array([[int(round(x)), int(round(y))] for x, y in zone.polygon], dtype=np.int32)

        # Translucent fill, drawn on a scratch layer so alpha stays cheap.
        if overlay is None:
            overlay = img.copy()
        cv2.fillPoly(overlay, [pts], color)
        cv2.polylines(img, [pts], True, color, 2, cv2.LINE_AA)
        _label(img, f"{zone.name} [{getattr(zone.severity, 'value', zone.severity)}]".upper(),
               int(pts[:, 0].min()), int(pts[:, 1].min()), color, 0.40)

    if overlay is not None:
        cv2.addWeighted(overlay, 0.16, img, 0.84, 0, dst=img)

    for boundary in boundaries:
        if not boundary.is_active:
            continue
        color = _severity_color(boundary.severity)
        is_norm = (0.0 <= boundary.pt1[0] <= 1.0 and 0.0 <= boundary.pt1[1] <= 1.0 and
                   0.0 <= boundary.pt2[0] <= 1.0 and 0.0 <= boundary.pt2[1] <= 1.0)
        if is_norm:
            p1 = (int(round(boundary.pt1[0] * w_canvas)), int(round(boundary.pt1[1] * h_canvas)))
            p2 = (int(round(boundary.pt2[0] * w_canvas)), int(round(boundary.pt2[1] * h_canvas)))
        else:
            p1 = (int(round(boundary.pt1[0])), int(round(boundary.pt1[1])))
            p2 = (int(round(boundary.pt2[0])), int(round(boundary.pt2[1])))
        cv2.line(img, p1, p2, color, 2, cv2.LINE_AA)
        # Endpoint pips plus a mid-segment normal arrow showing crossing direction.
        cv2.circle(img, p1, 4, color, -1, cv2.LINE_AA)
        cv2.circle(img, p2, 4, color, -1, cv2.LINE_AA)
        mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
        direction = getattr(boundary, "direction", "BIDIRECTIONAL").upper()
        arrow_len = 26
        if direction == "NORTH":
            target = (mid[0], mid[1] - arrow_len)
            cv2.arrowedLine(img, mid, target, color, 2, cv2.LINE_AA, tipLength=0.35)
        elif direction == "SOUTH":
            target = (mid[0], mid[1] + arrow_len)
            cv2.arrowedLine(img, mid, target, color, 2, cv2.LINE_AA, tipLength=0.35)
        elif direction == "EAST":
            target = (mid[0] + arrow_len, mid[1])
            cv2.arrowedLine(img, mid, target, color, 2, cv2.LINE_AA, tipLength=0.35)
        elif direction == "WEST":
            target = (mid[0] - arrow_len, mid[1])
            cv2.arrowedLine(img, mid, target, color, 2, cv2.LINE_AA, tipLength=0.35)
        else:  # BIDIRECTIONAL
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            norm = float(np.hypot(dx, dy)) or 1.0
            nx, ny = -dy / norm, dx / norm
            t1 = (int(mid[0] + nx * 20), int(mid[1] + ny * 20))
            t2 = (int(mid[0] - nx * 20), int(mid[1] - ny * 20))
            cv2.arrowedLine(img, mid, t1, color, 2, cv2.LINE_AA, tipLength=0.35)
            cv2.arrowedLine(img, mid, t2, color, 2, cv2.LINE_AA, tipLength=0.35)

        _label(img, f"{boundary.name} [{direction}]".upper(), p1[0], p1[1], color, 0.40)


def draw_tracks(
    img: np.ndarray,
    tracks: Sequence[TrackedObject],
    show_trails: bool = True,
) -> None:
    """Render tracked object boxes, direction arrows, cardinal headings, and motion trails."""
    import math
    h_canvas, w_canvas = img.shape[:2]

    for track in tracks:
        norm_box = getattr(track, "normalized_box", None)
        if norm_box and len(norm_box) >= 4 and all(0.0 <= v <= 1.0 for v in norm_box):
            x1 = int(round(norm_box[0] * w_canvas))
            y1 = int(round(norm_box[1] * h_canvas))
            x2 = int(round(norm_box[2] * w_canvas))
            y2 = int(round(norm_box[3] * h_canvas))
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
        else:
            box = track.bounding_box
            if not box or len(box) < 4:
                continue
            x1, y1, x2, y2 = (int(round(v)) for v in box[:4])
            cx, cy = int(round(track.center_x)), int(round(track.center_y))
        predicted = track.provenance == "prediction"
        color = _track_color(track)

        # 1. Bounding box — solid for real YOLO detections, dashed for Kalman predictions
        if predicted:
            _dashed_rect(img, x1, y1, x2, y2, color, 2)
        else:
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

        # Tactical corner brackets for military/C2 look (solid for detections, dimmer for predictions)
        bracket_color = _dim(C2_WHITE, 0.5) if predicted else C2_WHITE
        corner_len = min(12, max(6, (x2 - x1) // 4, (y2 - y1) // 4))
        # Top-left
        cv2.line(img, (x1, y1), (x1 + corner_len, y1), bracket_color, 2, cv2.LINE_AA)
        cv2.line(img, (x1, y1), (x1, y1 + corner_len), bracket_color, 2, cv2.LINE_AA)
        # Top-right
        cv2.line(img, (x2, y1), (x2 - corner_len, y1), bracket_color, 2, cv2.LINE_AA)
        cv2.line(img, (x2, y1), (x2, y1 + corner_len), bracket_color, 2, cv2.LINE_AA)
        # Bottom-left
        cv2.line(img, (x1, y2), (x1 + corner_len, y2), bracket_color, 2, cv2.LINE_AA)
        cv2.line(img, (x1, y2), (x1, y2 - corner_len), bracket_color, 2, cv2.LINE_AA)
        # Bottom-right
        cv2.line(img, (x2, y2), (x2 - corner_len, y2), bracket_color, 2, cv2.LINE_AA)
        cv2.line(img, (x2, y2), (x2, y2 - corner_len), bracket_color, 2, cv2.LINE_AA)

        # 2. Draw Direction Arrow from Centroid when moving
        heading = getattr(track, "cardinal_heading", "STATIONARY")
        dir_deg = getattr(track, "direction_deg", 0.0)
        is_moving = heading != "STATIONARY"

        if is_moving:
            rad = math.radians(dir_deg)
            arrow_len = 24
            target_x = int(cx + math.cos(rad) * arrow_len)
            target_y = int(cy + math.sin(rad) * arrow_len)
            # Centroid anchor dot
            cv2.circle(img, (cx, cy), 3, color, -1, cv2.LINE_AA)
            cv2.arrowedLine(
                img,
                (cx, cy),
                (target_x, target_y),
                C2_WHITE,
                2,
                cv2.LINE_AA,
                tipLength=0.35,
            )

        # 3. Tactical Label Chip
        conf_pct = int(round(track.confidence * 100))
        speed_text = getattr(track, "speed_description", "Stationary")
        pred_tag = " [PRED]" if predicted else ""
        
        if is_moving:
            label_text = f"{track.object_class.upper()} #{track.track_id} -> {heading} ({speed_text}){pred_tag}"
        else:
            label_text = f"{track.object_class.upper()} #{track.track_id} {conf_pct}%{pred_tag}"
            
        _label(img, label_text, x1, y1, color)

        # 4. Motion Trails
        if show_trails and len(track.trajectory) > 1:
            trail_pts = track.trajectory[-24:]
            # If canvas dimensions differ from track coordinates, scale trail points proportionally
            scale_x = (x2 - x1) / float(track.bounding_box[2] - track.bounding_box[0]) if track.bounding_box and (track.bounding_box[2] > track.bounding_box[0]) else 1.0
            scale_y = (y2 - y1) / float(track.bounding_box[3] - track.bounding_box[1]) if track.bounding_box and (track.bounding_box[3] > track.bounding_box[1]) else 1.0
            trail = np.array(
                [[int(round(pt[0] * scale_x)), int(round(pt[1] * scale_y))] for pt in trail_pts],
                dtype=np.int32,
            )
            cv2.polylines(img, [trail], False, _dim(color, 0.75), 1, cv2.LINE_AA)
            # Draw tiny endpoint dot
            if len(trail) > 0:
                cv2.circle(img, (trail[0][0], trail[0][1]), 2, _dim(color, 0.5), -1)


def draw_hud(
    img: np.ndarray,
    camera_id: str,
    display_fps: float,
    track_count: int,
    inference_fps: Optional[float] = None,
    device: str = "cpu",
    stride: int = 1,
    degraded: bool = False,
    modality: str = "STANDARD",
) -> None:
    """Render a compact status strip along the bottom of the frame with modality tag."""
    h, w = img.shape[:2]
    bar_h = 26
    top = h - bar_h
    strip = img[top:h, 0:w]
    cv2.addWeighted(strip, 0.25, np.zeros_like(strip), 0.75, 0, dst=strip)

    live_color = C2_AMBER if degraded else C2_EMERALD
    cv2.circle(img, (14, top + bar_h // 2), 4, live_color, -1, cv2.LINE_AA)

    mod_tag = "OPTICAL"
    if modality == "IR_NIGHT":
        mod_tag = "IR NIGHT"
    elif modality == "THERMAL":
        mod_tag = "THERMAL"

    left_text = f"{camera_id} [{mod_tag}]   {display_fps:4.1f} FPS   TRACKS {track_count}"
    cv2.putText(img, left_text, (26, top + 18), _FONT, 0.46, C2_WHITE, 1, cv2.LINE_AA)

    right_bits: List[str] = [f"YOLOv8n {device.upper()}"]
    if inference_fps is not None:
        right_bits.append(f"{inference_fps:.1f} inf/s")
    right_bits.append(f"stride {stride}")
    right_text = "   ".join(right_bits)
    (tw, _), _ = cv2.getTextSize(right_text, _FONT, 0.42, 1)
    cv2.putText(img, right_text, (max(0, w - tw - 10), top + 18), _FONT, 0.42, C2_CYAN, 1, cv2.LINE_AA)


def draw_offline(img: np.ndarray, camera_id: str, message: str) -> None:
    """Render a clear signal-loss placeholder while a source is reconnecting."""
    h, w = img.shape[:2]
    cv2.putText(img, "SIGNAL LOSS", (int(w * 0.5) - 96, int(h * 0.5) - 8),
                _FONT, 0.9, C2_CRIMSON, 2, cv2.LINE_AA)
    cv2.putText(img, f"{camera_id} — {message}", (int(w * 0.5) - 150, int(h * 0.5) + 22),
                _FONT, 0.48, C2_WHITE, 1, cv2.LINE_AA)


def annotate_frame(
    image: np.ndarray,
    tracks: Sequence[TrackedObject],
    zones: Iterable[SecurityZone] = (),
    boundaries: Iterable[VirtualBoundary] = (),
    camera_id: str = "",
    display_fps: float = 0.0,
    inference_fps: Optional[float] = None,
    device: str = "cpu",
    stride: int = 1,
    show_hud: bool = True,
    degraded: bool = False,
    copy: bool = False,
    modality: str = "STANDARD",
) -> np.ndarray:
    """
    Composite every overlay onto a frame and return the annotated image.

    Draw order matters: zones sit underneath tracks so boxes stay readable, and
    the HUD is painted last so nothing occludes it.
    """
    canvas = image.copy() if copy else image
    draw_zones(canvas, zones, boundaries)
    draw_tracks(canvas, tracks)
    if show_hud:
        draw_hud(
            canvas,
            camera_id=camera_id,
            display_fps=display_fps,
            track_count=len(tracks),
            inference_fps=inference_fps,
            device=device,
            stride=stride,
            degraded=degraded,
            modality=modality,
        )
    return canvas


def encode_jpeg(image: np.ndarray, quality: int = 70) -> Optional[bytes]:
    """Fast JPEG encode a frame once for fan-out to all MJPEG clients."""
    params = [cv2.IMWRITE_JPEG_QUALITY, int(quality), cv2.IMWRITE_JPEG_OPTIMIZE, 0]
    ok, buf = cv2.imencode(".jpg", image, params)
    if not ok:
        return None
    return buf.tobytes()
