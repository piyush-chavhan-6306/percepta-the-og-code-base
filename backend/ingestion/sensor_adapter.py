"""
Sensor Frame Adapter & Multi-Modal Normalization Module.
Provides modular normalization for RGB, IR, Night-Vision IR, and Radiometric Thermal streams
before feeding them into YOLO inference and multi-object tracking.
"""
from enum import Enum
import logging
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SensorModality(str, Enum):
    STANDARD = "STANDARD"
    RGB = "RGB"
    IR = "IR"
    IR_NIGHT = "IR_NIGHT"
    THERMAL = "THERMAL"


class SensorFrameAdapter:
    """
    Normalizes multi-modal frames across RGB, IR, IR_NIGHT, and THERMAL sensor types.
    Ensures that YOLO and ByteTrack receive consistent, normalized 3-channel BGR tensors
    regardless of input sensor modality.
    """

    @staticmethod
    def normalize_frame(
        image: np.ndarray,
        modality: str = "STANDARD",
    ) -> np.ndarray:
        """
        Normalize input image according to sensor modality.
        
        - RGB / STANDARD: Ensures 3-channel BGR.
        - IR: Grayscale normalization with adaptive contrast stretching.
        - IR_NIGHT: CLAHE contrast amplification for low-light night-vision footage.
        - THERMAL: Radiometric mapping / false-color ironbow colormap for zero-visibility thermal cameras.
        """
        if image is None or image.size == 0:
            return image

        mod = (modality or "STANDARD").upper()

        # 1. Standard Visible / RGB
        if mod in (SensorModality.STANDARD.value, SensorModality.RGB.value):
            if len(image.shape) == 2:
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            return image

        # 2. Thermal Camera Normalization
        if mod == SensorModality.THERMAL.value:
            from backend.detection.thermal_processor import get_thermal_processor, ThermalPalette
            proc = get_thermal_processor()
            # Returns false-color Ironbow 3-channel representation suitable for detection
            return proc.render_thermal_colormap(image, palette=ThermalPalette.IRONBOW)

        # 3. Night-Vision IR / Low Light Camera
        if mod in (SensorModality.IR_NIGHT.value, SensorModality.IR.value):
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image

            # Apply CLAHE to amplify subtle low-light IR signatures
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        # Fallback
        if len(image.shape) == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image
