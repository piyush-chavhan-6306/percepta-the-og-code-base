"""
Border Intelligence Image Sequence Adapter.
Provides SensorAdapter interface for image sequence datasets (MOT17, VisDrone-MOT).
"""
from datetime import datetime, timezone
import glob
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import cv2
import numpy as np

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData, SensorAdapter

logger = logging.getLogger(__name__)


class ImageSequenceAdapter(SensorAdapter):
    """
    SensorAdapter that ingests sequential image files (e.g. MOT17, VisDrone).
    """

    def __init__(
        self,
        camera_id: str,
        sequence_dir: str | Path,
        fps: float = 30.0,
        loop: bool = False,
        source: SourceType = SourceType.VIDEO_FILE,
    ) -> None:
        super().__init__(camera_id=camera_id, source=source)
        self.sequence_dir = Path(sequence_dir)
        self.fps = fps
        self.loop = loop

        self._image_files: List[Path] = []
        self._current_index = 0
        self._frame_count = 0
        self._width = 0
        self._height = 0

    async def start(self) -> None:
        """Scan sequence directory and sort image files."""
        if not self.sequence_dir.exists() or not self.sequence_dir.is_dir():
            raise FileNotFoundError(f"Sequence directory not found: {self.sequence_dir}")

        # Look for standard image extensions
        extensions = ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.JPG", "*.PNG")
        files: List[Path] = []
        for ext in extensions:
            files.extend(self.sequence_dir.glob(ext))

        # Sort naturally (e.g. 000001.jpg, 000002.jpg)
        self._image_files = sorted(files, key=lambda p: p.name)

        if not self._image_files:
            raise ValueError(f"No image files found in sequence directory: {self.sequence_dir}")

        # Inspect first image for dimensions
        first_img = cv2.imread(str(self._image_files[0]))
        if first_img is None:
            raise ValueError(f"Failed to decode first image in sequence: {self._image_files[0]}")

        self._height, self._width = first_img.shape[:2]
        self._current_index = 0
        self._frame_count = 0
        self._is_running = True
        logger.info(
            f"ImageSequenceAdapter opened {len(self._image_files)} frames from {self.sequence_dir} "
            f"({self._width}x{self._height} @ {self.fps} FPS)"
        )

    async def stop(self) -> None:
        """Close sequence reader."""
        self._is_running = False
        self._image_files.clear()
        self._current_index = 0
        logger.info(f"ImageSequenceAdapter stopped for camera {self.camera_id}")

    async def get_next_frame(self) -> Optional[FrameData]:
        """Read next image in sequence and return FrameData."""
        if not self._is_running or not self._image_files:
            return None

        if self._current_index >= len(self._image_files):
            if self.loop:
                self._current_index = 0
            else:
                return None

        img_path = self._image_files[self._current_index]
        self._current_index += 1
        self._frame_count += 1

        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning(f"Corrupt or unreadable image frame: {img_path}")
            return None

        h, w = img.shape[:2]
        return FrameData(
            camera_id=self.camera_id,
            frame_number=self._frame_count,
            timestamp=datetime.now(timezone.utc),
            image=img,
            width=w,
            height=h,
            fps=self.fps,
            source=self.source,
        )

    def get_stream_info(self) -> Dict[str, Any]:
        """Return sequence metadata."""
        return {
            "camera_id": self.camera_id,
            "adapter_type": "ImageSequenceAdapter",
            "is_running": self._is_running,
            "sequence_dir": str(self.sequence_dir),
            "total_frames": len(self._image_files),
            "current_frame": self._current_index,
            "width": self._width,
            "height": self._height,
            "fps": self.fps,
            "source": self.source.value,
        }
