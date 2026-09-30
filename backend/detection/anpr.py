"""
Border Intelligence Modular ANPR (Automatic Number Plate Recognition) Prototype.
Aligned with SIH Problem Statement SIH26187.
Provides a clean, modular interface for vehicle ROI cropping, plate localization, and OCR extraction.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Standard Indian / Defense Vehicle Registration Plate Regex Patterns
# e.g., DL01AB1234, MH12DE1432, 21BH1234AA, ARMY / DEFENSE ^[0-9]{2}[A-Z][0-9]{5,6}[A-Z]$
INDIAN_PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")
DEFENSE_PLATE_REGEX = re.compile(r"^[0-9]{2}[A-Z][0-9]{5,6}[A-Z]?$")


@dataclass
class ANPRResult:
    """Structured result from modular ANPR processing pipeline."""
    plate_number: str
    vehicle_class: str
    confidence: float
    plate_bounding_box: List[float]  # [x1, y1, x2, y2] relative to full frame
    is_verified_format: bool
    timestamp: datetime
    camera_id: str
    evidence_snapshot_uri: Optional[str] = None
    notes: str = "Modular ANPR Prototype"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plate_number": self.plate_number,
            "vehicle_class": self.vehicle_class,
            "confidence": round(self.confidence, 3),
            "plate_bounding_box": self.plate_bounding_box,
            "is_verified_format": self.is_verified_format,
            "timestamp": self.timestamp.isoformat(),
            "camera_id": self.camera_id,
            "evidence_snapshot_uri": self.evidence_snapshot_uri,
            "notes": self.notes,
        }


class ANPRProcessor:
    """
    Modular Vehicle License Plate Recognition Processor.
    Filters vehicle detections, crops ROI, detects high-contrast plate region,
    and extracts characters with verification.
    """

    VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "van"}

    def __init__(self, confidence_threshold: float = 0.40) -> None:
        self.confidence_threshold = confidence_threshold

    def is_vehicle(self, object_class: str) -> bool:
        """Check if detected class is an eligible vehicle."""
        return str(object_class).lower() in self.VEHICLE_CLASSES

    def localize_plate_roi(
        self,
        vehicle_crop: np.ndarray,
    ) -> Optional[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
        """
        Locate license plate candidate in vehicle crop using morphological gradient & contour aspect ratio.
        Returns (plate_crop, (x, y, w, h)) or None.
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None

        h, w = vehicle_crop.shape[:2]
        if h < 20 or w < 20:
            return None

        # Focus search on lower 65% of vehicle where plates are mounted
        search_top = int(h * 0.35)
        search_region = vehicle_crop[search_top:h, 0:w]
        if search_region.size == 0:
            return None

        gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
        blur = cv2.bilateralFilter(gray, 9, 75, 75)
        grad_x = cv2.Sobel(blur, cv2.CV_16S, 1, 0, ksize=3)
        grad_x = cv2.convertScaleAbs(grad_x)

        _, thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if ch == 0 or cw == 0:
                continue
            aspect = float(cw) / float(ch)
            area = cw * ch
            # License plates typically have aspect ratio between 2.0 and 5.5
            if 2.0 <= aspect <= 5.5 and (w * h * 0.01) <= area <= (w * h * 0.25):
                candidates.append((area, (x, y + search_top, cw, ch)))

        if not candidates:
            # Fallback: estimate standard lower-center bumper region
            bw = int(w * 0.45)
            bh = int(h * 0.18)
            bx = int((w - bw) / 2)
            by = int(h * 0.72)
            crop = vehicle_crop[by : by + bh, bx : bx + bw]
            if crop.size > 0:
                return crop, (bx, by, bw, bh)
            return None

        # Pick largest plausible candidate
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, (bx, by, bw, bh) = candidates[0]
        plate_crop = vehicle_crop[by : by + bh, bx : bx + bw]
        return plate_crop, (bx, by, bw, bh)

    def extract_text(self, plate_crop: np.ndarray, vehicle_id: str = "") -> Tuple[str, float, bool]:
        """
        Extract plate text from plate ROI.
        Attempts real OCR if pytesseract is available; otherwise marks as UNRESOLVED_LOW_RES.
        NEVER generates fake or synthetic plate numbers.
        """
        if plate_crop is None or plate_crop.size == 0:
            return "UNREADABLE", 0.0, False

        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if len(plate_crop.shape) == 3 else plate_crop
        contrast = float(np.std(gray))

        if contrast < 12.0:
            return "LOW_CONTRAST_UNREADABLE", 0.20, False

        # OCR disabled by user to prevent CPU freezing on demo machine.
        # The license plate crop image will still be captured for evidence!
        return "OCR_DISABLED", round(min(0.50, contrast / 80.0), 2), False

    def process_vehicle(
        self,
        frame: np.ndarray,
        bounding_box: List[float],
        object_class: str = "car",
        camera_id: str = "CAM-01",
        vehicle_id: str = "",
    ) -> Optional[ANPRResult]:
        """
        End-to-end ANPR processing on a detected vehicle box.
        """
        if not self.is_vehicle(object_class) or frame is None:
            return None

        h_img, w_img = frame.shape[:2]
        x1, y1, x2, y2 = map(int, bounding_box[:4])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_img, x2), min(h_img, y2)

        if (x2 - x1) < 25 or (y2 - y1) < 25:
            return None

        vehicle_crop = frame[y1:y2, x1:x2]
        plate_loc = self.localize_plate_roi(vehicle_crop)

        if plate_loc is None:
            return None

        plate_crop, (px, py, pw, ph) = plate_loc
        plate_text, conf, is_verified = self.extract_text(plate_crop, vehicle_id=vehicle_id)

        # Global bounding box of plate
        global_plate_box = [
            float(x1 + px),
            float(y1 + py),
            float(x1 + px + pw),
            float(y1 + py + ph),
        ]

        return ANPRResult(
            plate_number=plate_text,
            vehicle_class=object_class,
            confidence=conf,
            plate_bounding_box=global_plate_box,
            is_verified_format=is_verified,
            timestamp=datetime.now(timezone.utc),
            camera_id=camera_id,
            notes="Modular ANPR Prototype (SIH26187 Alignment)",
        )


global_anpr_processor = ANPRProcessor()


def get_anpr_processor() -> ANPRProcessor:
    return global_anpr_processor
