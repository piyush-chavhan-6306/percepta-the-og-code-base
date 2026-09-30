"""
Border Intelligence Webcam / USB Capture Adapter.

Reads from a locally attached capture device (`cv2.VideoCapture(<index>)`) for
continuous 24/7 operation. Unlike the video-file adapter there is no end of
stream: a failed read means the device hiccuped, so the adapter reports failure
and lets the supervising worker decide when to reconnect.
"""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import cv2

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData, SensorAdapter
from backend.ingestion.frame_buffer import FrameBuffer, get_frame_buffer_manager

logger = logging.getLogger(__name__)


class WebcamAdapter(SensorAdapter):
    """OpenCV capture-device adapter for locally attached cameras."""

    def __init__(
        self,
        camera_id: str,
        device_index: int = 0,
        target_fps: Optional[float] = None,
        frame_buffer: Optional[FrameBuffer] = None,
        request_width: Optional[int] = 1280,
        request_height: Optional[int] = 720,
        max_consecutive_failures: int = 30,
    ) -> None:
        super().__init__(camera_id=camera_id, source=SourceType.VIDEO_FILE)
        self.device_index = int(device_index)
        self.target_fps = target_fps
        self.request_width = request_width
        self.request_height = request_height
        self._buffer = frame_buffer or get_frame_buffer_manager().get_buffer(camera_id)

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_count = 0
        self._width = 0
        self._height = 0
        self._native_fps = 30.0
        self._consecutive_failures = 0
        self._max_consecutive_failures = max_consecutive_failures

    async def start(self) -> None:
        """Open the capture device and negotiate resolution."""
        # CAP_DSHOW avoids the multi-second MSMF initialization stall on Windows.
        backend_flag = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0
        cap = cv2.VideoCapture(self.device_index, backend_flag)
        if not cap.isOpened():  # fall back to the platform default backend
            cap.release()
            cap = cv2.VideoCapture(self.device_index)

        if not cap.isOpened():
            cap.release()
            raise ConnectionError(
                f"Failed to open capture device index {self.device_index} for camera "
                f"'{self.camera_id}'. Check the device is attached and not in use by another app."
            )

        if self.request_width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.request_width)
        if self.request_height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request_height)
        # Keep the driver queue shallow so we always read a near-live frame.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._cap = cap
        self._width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        self._height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self._native_fps = fps if fps > 1.0 else 30.0
        self._frame_count = 0
        self._consecutive_failures = 0
        self._is_running = True
        logger.info(
            f"WebcamAdapter started for '{self.camera_id}' on device {self.device_index}: "
            f"{self._width}x{self._height} @ {self._native_fps} FPS"
        )

    def read_frame_blocking(self) -> Optional[FrameData]:
        """
        Synchronous capture read; dispatch from a worker thread on the event loop.
        A live device never legitimately "ends", so repeated failures mark the
        adapter stopped and let the supervisor reconnect it.
        """
        if not self._is_running or self._cap is None:
            return None

        ret, frame = self._cap.read()

        if not ret or frame is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_consecutive_failures:
                logger.warning(
                    f"Webcam '{self.camera_id}' exceeded failure threshold "
                    f"({self._consecutive_failures}); marking offline for reconnect"
                )
                self._is_running = False
            return None

        self._consecutive_failures = 0
        self._frame_count += 1

        frame_data = FrameData(
            camera_id=self.camera_id,
            frame_number=self._frame_count,
            timestamp=datetime.now(timezone.utc),
            image=frame,
            width=self._width,
            height=self._height,
            fps=self.target_fps or self._native_fps,
            source=self.source,
        )
        self._buffer.push(frame_data)
        return frame_data

    async def get_next_frame(self) -> Optional[FrameData]:
        """Fetch the next frame from the capture device."""
        return self.read_frame_blocking()

    async def stop(self) -> None:
        """Release the capture device handle."""
        self._is_running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info(f"WebcamAdapter stopped for '{self.camera_id}' (device {self.device_index})")

    def get_stream_info(self) -> Dict[str, Any]:
        """Return capture device metadata."""
        return {
            "camera_id": self.camera_id,
            "source_type": "webcam",
            "device_index": self.device_index,
            "is_running": self._is_running,
            "resolution": f"{self._width}x{self._height}",
            "width": self._width,
            "height": self._height,
            "fps": self.target_fps or self._native_fps,
            "native_fps": self._native_fps,
            "current_frame": self._frame_count,
            "consecutive_failures": self._consecutive_failures,
        }
