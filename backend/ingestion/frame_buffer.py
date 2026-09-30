"""
Border Intelligence Bounded Ring FrameBuffer.
Holds a bounded rolling in-memory window of frames per camera for pre/trigger/post evidence capture.
Uses threading.RLock() for thread safety and re-entrant method calls.
"""
from collections import deque
from datetime import datetime
import threading
from typing import Dict, List, Optional
from backend.ingestion.adapter import FrameData


class FrameBuffer:
    """
    Thread-safe bounded in-memory ring buffer holding recent frames for a camera.
    Automatically discards oldest frames when capacity is reached.
    """

    def __init__(self, camera_id: str, max_frames: int = 150) -> None:
        self.camera_id = camera_id
        self.max_frames = max_frames
        self._buffer: deque[FrameData] = deque(maxlen=max_frames)
        self._lock = threading.RLock()

    def push(self, frame: FrameData) -> None:
        """Add a new frame to the rolling buffer. Thread-safe."""
        with self._lock:
            self._buffer.append(frame)

    def get_latest(self) -> Optional[FrameData]:
        """Return the most recent frame in the buffer."""
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def get_frame(self, frame_number: int) -> Optional[FrameData]:
        """Retrieve a specific frame by frame_number if still present in buffer."""
        with self._lock:
            for frame in self._buffer:
                if frame.frame_number == frame_number:
                    return frame
            return None

    def get_window(self, start_frame: int, end_frame: int) -> List[FrameData]:
        """Retrieve a contiguous window of frames [start_frame, end_frame] inclusive."""
        with self._lock:
            return [
                f for f in self._buffer
                if start_frame <= f.frame_number <= end_frame
            ]

    def get_time_window(self, start_time: datetime, end_time: datetime) -> List[FrameData]:
        """Retrieve all frames recorded between start_time and end_time."""
        with self._lock:
            return [
                f for f in self._buffer
                if start_time <= f.timestamp <= end_time
            ]

    def get_pre_event_frames(self, trigger_frame_number: int, count: int = 15) -> List[FrameData]:
        """
        Extract up to `count` frames immediately preceding the trigger_frame_number.
        """
        with self._lock:
            pre_frames = [
                f for f in self._buffer
                if f.frame_number < trigger_frame_number
            ]
            return pre_frames[-count:] if len(pre_frames) > count else pre_frames

    def get_trigger_frame(self, trigger_frame_number: int) -> Optional[FrameData]:
        """Extract the exact trigger frame, or the closest available frame."""
        with self._lock:
            if not self._buffer:
                return None
            exact = self.get_frame(trigger_frame_number)
            if exact is not None:
                return exact
            best_frame = None
            best_diff = float("inf")
            for frame in self._buffer:
                diff = abs(frame.frame_number - trigger_frame_number)
                if diff < best_diff:
                    best_diff = diff
                    best_frame = frame
            return best_frame

    def size(self) -> int:
        """Return the current number of buffered frames."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Clear all buffered frames."""
        with self._lock:
            self._buffer.clear()


class FrameBufferManager:
    """Registry managing bounded FrameBuffers across multiple cameras."""

    def __init__(self, default_max_frames: int = 150) -> None:
        self.default_max_frames = default_max_frames
        self._buffers: Dict[str, FrameBuffer] = {}
        self._lock = threading.RLock()

    def get_buffer(self, camera_id: str, max_frames: Optional[int] = None) -> FrameBuffer:
        """Get or initialize a FrameBuffer for a specific camera."""
        with self._lock:
            if camera_id not in self._buffers:
                capacity = max_frames or self.default_max_frames
                self._buffers[camera_id] = FrameBuffer(camera_id=camera_id, max_frames=capacity)
            return self._buffers[camera_id]

    def remove_buffer(self, camera_id: str) -> None:
        """Remove a camera buffer when camera is decommissioned."""
        with self._lock:
            if camera_id in self._buffers:
                self._buffers[camera_id].clear()
                del self._buffers[camera_id]


# Global singleton
global_frame_buffer_manager = FrameBufferManager()


def get_frame_buffer_manager() -> FrameBufferManager:
    return global_frame_buffer_manager
