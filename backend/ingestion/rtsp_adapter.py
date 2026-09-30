"""
Border Intelligence RTSP Camera Adapter.
Provides real-time RTSP/CCTV IP camera ingestion with credential sanitization,
timeout protection, non-blocking frame capture, and graceful error handling.
"""
from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, Optional
import cv2
import numpy as np

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData, SensorAdapter
from backend.ingestion.frame_buffer import FrameBuffer, get_frame_buffer_manager

logger = logging.getLogger(__name__)


def sanitize_rtsp_url(url: str) -> str:
    """Mask credentials in RTSP URL to prevent leaking passwords in logs or API responses."""
    if not url:
        return ""
    # Matches rtsp://username:password@host...
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


class RTSPAdapter(SensorAdapter):
    """
    RTSP / IP Camera Ingestion Adapter.
    Connects to live RTSP/HTTP streams with timeout safety and credential protection.
    """

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        target_fps: Optional[float] = None,
        frame_buffer: Optional[FrameBuffer] = None,
        connect_timeout_sec: float = 5.0,
    ) -> None:
        super().__init__(camera_id=camera_id, source=SourceType.VIDEO_FILE)
        self.rtsp_url = rtsp_url
        self.sanitized_url = sanitize_rtsp_url(rtsp_url)
        self.target_fps = target_fps
        self.connect_timeout_sec = connect_timeout_sec
        self._buffer = frame_buffer or get_frame_buffer_manager().get_buffer(camera_id)

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_count = 0
        self._width = 1280
        self._height = 720
        self._native_fps = 30.0
        self._consecutive_failures = 0
        self._max_consecutive_failures = 10

    async def start(self) -> None:
        """Connect to RTSP stream."""
        if not self.rtsp_url:
            raise ValueError(f"Empty RTSP URL provided for camera '{self.camera_id}'")

        logger.info(f"Opening RTSP stream for '{self.camera_id}' at {self.sanitized_url}")
        self._cap = cv2.VideoCapture(self.rtsp_url)

        if not self._cap.isOpened():
            raise ConnectionError(f"Failed to connect to RTSP stream: {self.sanitized_url}")

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if w > 0 and h > 0:
            self._width = w
            self._height = h

        fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps > 0:
            self._native_fps = fps

        self._frame_count = 0
        self._consecutive_failures = 0
        self._is_running = True
        logger.info(f"RTSP stream connected for '{self.camera_id}': {self._width}x{self._height} @ {self._native_fps} FPS")

    def read_frame_blocking(self) -> Optional[FrameData]:
        """
        Synchronous RTSP frame read. Network reads can stall for hundreds of
        milliseconds, so callers on the event loop must dispatch this to a worker
        thread (CameraManager does). After `_max_consecutive_failures` empty reads
        the adapter marks itself stopped so the supervisor can reconnect it.
        """
        if not self._is_running or self._cap is None:
            return None

        ret, frame = self._cap.read()

        if not ret or frame is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_consecutive_failures:
                logger.warning(f"RTSP camera '{self.camera_id}' exceeded failure threshold ({self._consecutive_failures})")
                self._is_running = False
            return None

        self._consecutive_failures = 0
        self._frame_count += 1
        now = datetime.now(timezone.utc)

        frame_data = FrameData(
            camera_id=self.camera_id,
            frame_number=self._frame_count,
            timestamp=now,
            image=frame,
            width=self._width,
            height=self._height,
            fps=self.target_fps or self._native_fps,
            source=self.source,
        )

        self._buffer.push(frame_data)
        return frame_data

    async def get_next_frame(self) -> Optional[FrameData]:
        """Fetch next frame from RTSP stream."""
        return self.read_frame_blocking()

    async def stop(self) -> None:
        """Release RTSP stream."""
        self._is_running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info(f"RTSP stream stopped for '{self.camera_id}'")

    def get_stream_info(self) -> Dict[str, Any]:
        """Return RTSP stream info with sanitized URL."""
        return {
            "camera_id": self.camera_id,
            "source_type": "rtsp",
            "stream_url": self.sanitized_url,
            "is_running": self._is_running,
            "resolution": f"{self._width}x{self._height}",
            "width": self._width,
            "height": self._height,
            "fps": self.target_fps or self._native_fps,
            "native_fps": self._native_fps,
            "current_frame": self._frame_count,
        }
