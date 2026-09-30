"""
Border Intelligence SensorAdapter Base Interface.
Defines abstract contracts for camera and sensor ingestion adapters.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import numpy as np

from backend.events.schema import SourceType


@dataclass(eq=False)
class FrameData:
    """Normalized frame data package yielded by all adapters."""
    camera_id: str
    frame_number: int
    timestamp: datetime
    image: np.ndarray = field(repr=False)  # BGR uint8 image array, excluded from repr
    width: int = 640
    height: int = 480
    fps: float = 30.0
    source: SourceType = SourceType.VIDEO_FILE
    modality: str = "STANDARD"  # "STANDARD", "IR_NIGHT", "THERMAL"

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.image.shape


class SensorAdapter(ABC):
    """Abstract interface for all video and sensor adapters."""

    def __init__(
        self,
        camera_id: str,
        source: SourceType = SourceType.VIDEO_FILE,
        modality: str = "STANDARD",
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.modality = modality  # "STANDARD", "IR_NIGHT", "THERMAL"
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @abstractmethod
    async def start(self) -> None:
        """Initialize and open the sensor/video stream."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully release and close the stream."""
        pass

    @abstractmethod
    async def get_next_frame(self) -> Optional[FrameData]:
        """
        Fetch the next frame from the stream.
        Returns None when the stream finishes or is unavailable.
        """
        pass

    @abstractmethod
    def get_stream_info(self) -> Dict[str, Any]:
        """Return stream metadata (resolution, FPS, status)."""
        pass
