"""
Border Intelligence Simulation Adapter.
Generates synthetic surveillance frames with dynamic entities for simulation and testing.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import cv2
import numpy as np

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData, SensorAdapter
from backend.ingestion.frame_buffer import FrameBuffer, get_frame_buffer_manager


class SimulationAdapter(SensorAdapter):
    """
    Synthetic surveillance frame generator for tests and multi-sensor simulations.
    """

    def __init__(
        self,
        camera_id: str,
        width: int = 640,
        height: int = 480,
        fps: float = 15.0,
        max_frames: int = 100,
        source: SourceType = SourceType.SIMULATION,
        frame_buffer: Optional[FrameBuffer] = None,
    ) -> None:
        super().__init__(camera_id=camera_id, source=source)
        self.width = width
        self.height = height
        self.fps = fps
        self.max_frames = max_frames
        self._buffer = frame_buffer or get_frame_buffer_manager().get_buffer(camera_id)
        self._frame_count = 0

    async def start(self) -> None:
        """Initialize synthetic stream."""
        self._frame_count = 0
        self._is_running = True

    async def get_next_frame(self) -> Optional[FrameData]:
        """Generate the next synthetic frame."""
        if not self._is_running or self._frame_count >= self.max_frames:
            self._is_running = False
            return None

        self._frame_count += 1
        now = datetime.now(timezone.utc)

        # Create dark perimeter surveillance background
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        # Background gradient
        frame[:, :] = (30, 35, 30)

        # Draw a simulated fence line
        cv2.line(frame, (0, int(self.height * 0.7)), (self.width, int(self.height * 0.7)), (60, 60, 60), 2)

        # Draw a moving simulated target entity (simulating person moving across frame)
        cx = int((self._frame_count * 5) % self.width)
        cy = int(self.height * 0.6)
        cv2.rectangle(frame, (cx - 15, cy - 40), (cx + 15, cy + 20), (200, 200, 200), -1)

        # Timestamp watermark
        cv2.putText(
            frame,
            f"SIM CAM: {self.camera_id} | F: {self._frame_count:04d}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            1,
        )

        frame_data = FrameData(
            camera_id=self.camera_id,
            frame_number=self._frame_count,
            timestamp=now,
            image=frame,
            width=self.width,
            height=self.height,
            fps=self.fps,
            source=self.source,
        )

        self._buffer.push(frame_data)
        return frame_data

    async def stop(self) -> None:
        """Stop simulation."""
        self._is_running = False

    def get_stream_info(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "source_type": self.source.value,
            "is_running": self._is_running,
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps,
            "current_frame": self._frame_count,
            "total_frames": self.max_frames,
        }
