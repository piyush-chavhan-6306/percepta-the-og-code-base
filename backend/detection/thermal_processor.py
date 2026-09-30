"""
Border Intelligence Thermal Surveillance Ingestion & Radiometric Processing Module.
Aligned with SIH Problem Statement SIH26187 (Multi-Modal Surveillance Intelligence).
Supports thermal cameras, white-hot/black-hot radiometric mapping, false-color ironbow rendering,
and thermal hotspot detection through the unified AI perception pipeline.
"""
from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from backend.detection.detector import DetectionResult

logger = logging.getLogger(__name__)


class ThermalPalette(str, Enum):
    WHITE_HOT = "WHITE_HOT"
    BLACK_HOT = "BLACK_HOT"
    IRONBOW = "IRONBOW"
    JET = "JET"


@dataclass
class ThermalHotspot:
    """Detected thermal signature candidate in radiometric / thermal stream."""
    centroid: Tuple[float, float]
    bounding_box: List[float]  # [x1, y1, x2, y2]
    mean_intensity: float
    max_intensity: float
    is_high_heat: bool


class ThermalProcessor:
    """
    Modular Thermal Surveillance Processing Pipeline.
    Normalizes 8-bit/16-bit thermal frames, applies false-color ironbow palettes for operator visual clarity,
    and extracts radiometric thermal hotspots for people/vehicle detection in zero-visibility conditions.
    """

    def __init__(self, default_palette: ThermalPalette = ThermalPalette.IRONBOW) -> None:
        self.default_palette = default_palette

    def render_thermal_colormap(
        self,
        image: np.ndarray,
        palette: Optional[ThermalPalette] = None,
    ) -> np.ndarray:
        """
        Convert grayscale/raw thermal input into an enhanced false-color thermal representation.
        """
        if image is None or image.size == 0:
            return image

        pal = palette or self.default_palette

        # Ensure single channel grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Histogram equalization / contrast stretching for thermal range enhancement
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        if pal == ThermalPalette.WHITE_HOT:
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        elif pal == ThermalPalette.BLACK_HOT:
            inv = cv2.bitwise_not(enhanced)
            return cv2.cvtColor(inv, cv2.COLOR_GRAY2BGR)
        elif pal == ThermalPalette.JET:
            return cv2.applyColorMap(enhanced, cv2.COLORMAP_JET)
        else:  # IRONBOW / INFERNO
            return cv2.applyColorMap(enhanced, cv2.COLORMAP_INFERNO)

    def extract_thermal_signatures(
        self,
        image: np.ndarray,
        heat_threshold: float = 160.0,
        min_area: int = 120,
    ) -> List[ThermalHotspot]:
        """
        Detect high-temperature thermal signatures (people, running vehicle engines).
        """
        if image is None or image.size == 0:
            return []

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, int(heat_threshold), 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hotspots: List[ThermalHotspot] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            roi = gray[y : y + h, x : x + w]
            mean_int = float(np.mean(roi)) if roi.size > 0 else 0.0
            max_int = float(np.max(roi)) if roi.size > 0 else 0.0

            cx = float(x + w / 2.0)
            cy = float(y + h / 2.0)

            hotspots.append(
                ThermalHotspot(
                    centroid=(cx, cy),
                    bounding_box=[float(x), float(y), float(x + w), float(y + h)],
                    mean_intensity=round(mean_int, 1),
                    max_intensity=round(max_int, 1),
                    is_high_heat=max_int >= 220.0,
                )
            )

        return hotspots


global_thermal_processor = ThermalProcessor()


def get_thermal_processor() -> ThermalProcessor:
    return global_thermal_processor
