"""
Border Intelligence Movement Analysis Module.
Calculates displacement vectors, directions, and pixel-space speeds from bounded trajectory histories.
"""
from dataclasses import dataclass
import math
from typing import List, Optional, Tuple


@dataclass
class MovementVector:
    """
    Structured movement calculation for a tracked entity.
    Explicitly operates in pixel-coordinate space unless calibrated with real-world scale.
    """
    dx: float  # Horizontal displacement in pixels
    dy: float  # Vertical displacement in pixels
    distance_px: float  # Euclidean pixel distance moved
    direction_deg: float  # Heading angle in degrees [0, 360) where 0 = East, 90 = South
    cardinal_heading: str  # e.g., 'N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'STATIONARY'
    speed_px_per_frame: float  # Pixel speed per video frame
    speed_px_per_sec: float  # Estimated pixel speed per second (based on FPS)

    @property
    def is_moving(self) -> bool:
        return self.distance_px > 1.0


def calculate_cardinal_heading(direction_deg: float, is_stationary: bool = False) -> str:
    """
    Convert image-space degrees (0=East, 90=South, 180=West, 270=North) to cardinal compass notation.
    """
    if is_stationary:
        return "STATIONARY"

    deg = direction_deg % 360.0
    # In image coordinate space:
    # 0 -> East
    # 45 -> South-East
    # 90 -> South
    # 135 -> South-West
    # 180 -> West
    # 225 -> North-West
    # 270 -> North
    # 315 -> North-East
    if 22.5 <= deg < 67.5:
        return "SE"
    elif 67.5 <= deg < 112.5:
        return "S"
    elif 112.5 <= deg < 157.5:
        return "SW"
    elif 157.5 <= deg < 202.5:
        return "W"
    elif 202.5 <= deg < 247.5:
        return "NW"
    elif 247.5 <= deg < 292.5:
        return "N"
    elif 292.5 <= deg < 337.5:
        return "NE"
    else:
        return "E"


def calculate_movement_vector(
    trajectory: List[Tuple[float, float]],
    fps: float = 30.0,
    window_size: int = 5,
    min_movement_threshold: float = 1.0,
) -> MovementVector:
    """
    Calculate movement vector from recent trajectory points.
    
    Args:
        trajectory: List of (cx, cy) coordinate tuples in chronological order.
        fps: Frames per second of the video source (default 30.0).
        window_size: Number of recent points to use for smooth vector calculation.
        min_movement_threshold: Pixel displacement below which object is considered stationary.
        
    Returns:
        MovementVector with displacement, speed, and heading.
    """
    if not trajectory or len(trajectory) < 2:
        return MovementVector(
            dx=0.0,
            dy=0.0,
            distance_px=0.0,
            direction_deg=0.0,
            cardinal_heading="STATIONARY",
            speed_px_per_frame=0.0,
            speed_px_per_sec=0.0,
        )

    # Use window of recent points for smoother velocity estimation
    pts = trajectory[-window_size:]
    p_start = pts[0]
    p_end = pts[-1]
    frames_elapsed = max(1, len(pts) - 1)

    total_dx = p_end[0] - p_start[0]
    total_dy = p_end[1] - p_start[1]
    total_dist = math.hypot(total_dx, total_dy)

    # Instantaneous/average per frame
    dx = round(total_dx / frames_elapsed, 2)
    dy = round(total_dy / frames_elapsed, 2)
    dist_per_frame = round(total_dist / frames_elapsed, 2)

    is_stationary = total_dist < (min_movement_threshold * frames_elapsed)

    if is_stationary or total_dist == 0:
        direction_deg = 0.0
        cardinal = "STATIONARY"
    else:
        # atan2(y, x) -> in image coordinates (y down, x right)
        angle_rad = math.atan2(total_dy, total_dx)
        angle_deg = math.degrees(angle_rad)
        if angle_deg < 0:
            angle_deg += 360.0
        direction_deg = round(angle_deg, 1)
        cardinal = calculate_cardinal_heading(direction_deg, is_stationary=False)

    speed_px_frame = dist_per_frame
    speed_px_sec = round(dist_per_frame * fps, 2)

    return MovementVector(
        dx=dx,
        dy=dy,
        distance_px=round(total_dist, 2),
        direction_deg=direction_deg,
        cardinal_heading=cardinal,
        speed_px_per_frame=speed_px_frame,
        speed_px_per_sec=speed_px_sec,
    )


def format_speed_label(
    speed_px_sec: float,
    is_stationary: bool,
    calibrated_meters_per_pixel: Optional[float] = None,
) -> str:
    """
    Format a scientifically honest speed label for operators.
    If camera metric calibration is provided, displays calibrated m/s.
    Otherwise, explicitly states relative/estimated speed to avoid faking physical metrics.
    """
    if is_stationary or speed_px_sec < 2.0:
        return "Stationary"

    if calibrated_meters_per_pixel is not None and calibrated_meters_per_pixel > 0:
        mps = round(speed_px_sec * calibrated_meters_per_pixel, 1)
        return f"~{mps} m/s (calibrated)"

    # Relative speed category based on pixel velocity
    if speed_px_sec > 120.0:
        return "Fast Moving (Rel)"
    elif speed_px_sec > 40.0:
        return "Moderate (Rel)"
    else:
        return "Slow Moving (Rel)"


def is_moving_towards(
    curr_pos: Tuple[float, float],
    heading_deg: float,
    target_pos: Tuple[float, float],
    tolerance_deg: float = 50.0,
) -> bool:
    """
    Check if an object at curr_pos moving along heading_deg is heading towards target_pos.
    Returns True if the angular difference between current heading and vector to target <= tolerance_deg.
    """
    dx = target_pos[0] - curr_pos[0]
    dy = target_pos[1] - curr_pos[1]
    dist = math.hypot(dx, dy)
    if dist < 5.0:
        return True  # Already at target

    target_angle_rad = math.atan2(dy, dx)
    target_angle_deg = math.degrees(target_angle_rad)
    if target_angle_deg < 0:
        target_angle_deg += 360.0

    diff = abs((heading_deg - target_angle_deg + 180) % 360 - 180)
    return diff <= tolerance_deg


def detect_abnormal_direction_change(
    trajectory: List[Tuple[float, float]],
    window: int = 4,
    min_angle_change_deg: float = 90.0,
) -> bool:
    """
    Detect sharp, erratic direction reversals or sharp turns in recent trajectory.
    """
    if not trajectory or len(trajectory) < (window * 2):
        return False

    first_segment = trajectory[-window*2 : -window]
    second_segment = trajectory[-window:]

    v1 = calculate_movement_vector(first_segment, min_movement_threshold=2.0)
    v2 = calculate_movement_vector(second_segment, min_movement_threshold=2.0)

    if not v1.is_moving or not v2.is_moving:
        return False

    diff = abs((v2.direction_deg - v1.direction_deg + 180) % 360 - 180)
    return diff >= min_angle_change_deg


def detect_oscillating_movement(
    trajectory: List[Tuple[float, float]],
    sample_stride: int = 4,
    min_reversals: int = 2,
) -> bool:
    """
    Detect back-and-forth pacing or circling in the same area.
    """
    if not trajectory or len(trajectory) < 16:
        return False

    sampled = trajectory[::sample_stride]
    if len(sampled) < 4:
        return False

    headings = []
    for i in range(len(sampled) - 1):
        p1, p2 = sampled[i], sampled[i + 1]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        if math.hypot(dx, dy) > 2.0:
            ang = math.degrees(math.atan2(dy, dx)) % 360.0
            headings.append(ang)

    if len(headings) < 3:
        return False

    reversals = 0
    for i in range(len(headings) - 1):
        diff = abs((headings[i + 1] - headings[i] + 180) % 360 - 180)
        if diff > 110.0:
            reversals += 1

    return reversals >= min_reversals
